from __future__ import annotations

import base64
import mimetypes
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.testimonial_renderer.validate import TestimonialRenderError, validate_payload


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _template_paths() -> dict[str, Path]:
    base = _package_dir() / "templates"
    return {
        "review_card": base / "review_card.html",
        "social_comment": base / "social_comment.html",
        "social_comment_no_header": base / "social_comment_no_header.html",
        "social_comment_instagram": base / "social_comment_instagram.html",
        "testimonial_media": base / "testimonial_media.html",
        "pdp_ugc_standard": base / "pdp_ugc_standard.html",
        "pdp_qa_ugc": base / "pdp_qa_ugc.html",
        "pdp_bold_claim": base / "pdp_bold_claim.html",
        "pdp_personal_highlight": base / "pdp_personal_highlight.html",
    }


def _resolve_template_url(template: str) -> str:
    path = _template_paths().get(template)
    if not path:
        raise TestimonialRenderError(f"No template found for {template}.")
    if not path.exists():
        raise TestimonialRenderError(f"Template file does not exist: {path}")
    return path.resolve().as_uri()


def _to_data_url(buffer: bytes, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(buffer).decode('ascii')}"


def _extract_first_inline_image(response_json: dict[str, Any]) -> tuple[bytes, str]:
    candidates = response_json.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") if isinstance(cand, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            data = inline.get("data")
            mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            if isinstance(data, str) and data:
                return base64.b64decode(data), str(mime_type)
    raise TestimonialRenderError("Nano Banana did not return an image.")


def _summarize_gemini_response_for_debug(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        return f"type={type(response_json).__name__}"
    try:
        top_keys = sorted(list(response_json.keys()))[:20]
        candidates = response_json.get("candidates") or []
        candidate_count = len(candidates) if isinstance(candidates, list) else 0

        finish_reasons: list[str] = []
        part_kinds: list[str] = []
        if isinstance(candidates, list):
            for cand in candidates[:2]:
                if not isinstance(cand, dict):
                    continue
                finish = cand.get("finishReason") or cand.get("finish_reason")
                if isinstance(finish, str):
                    finish_reasons.append(finish)
                content = cand.get("content") if isinstance(cand.get("content"), dict) else None
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list):
                    for part in parts[:6]:
                        if not isinstance(part, dict):
                            continue
                        if "inlineData" in part or "inline_data" in part:
                            part_kinds.append("inlineData")
                        elif "text" in part:
                            part_kinds.append("text")
                        else:
                            part_kinds.append(",".join(sorted(part.keys()))[:60])

        bits = [
            f"topKeys={top_keys}",
            f"candidateCount={candidate_count}",
            f"finishReasons={finish_reasons[:2]}",
            f"partKinds={part_kinds[:12]}",
        ]
        return " ".join(bits)
    except Exception as exc:  # noqa: BLE001
        return f"failed_to_summarize_response error={type(exc).__name__}"


def _resolve_reference_image_source(value: str, *, base_dir: Path) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise TestimonialRenderError("reference image source must not be empty.")
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed
    if trimmed.startswith("data:"):
        return trimmed
    if trimmed.startswith("file://"):
        return trimmed
    resolved = Path(trimmed)
    if not resolved.is_absolute():
        resolved = (base_dir / resolved).resolve()
    return resolved.as_uri()


def _read_reference_image_bytes(source: str) -> tuple[bytes, str]:
    if source.startswith("data:"):
        match = re.match(r"^data:([^;]+);base64,(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            raise TestimonialRenderError("Invalid data URL in referenceImages.")
        mime_type = match.group(1).strip().lower()
        data_raw = match.group(2).strip()
        try:
            data = base64.b64decode(data_raw)
        except Exception as exc:  # noqa: BLE001
            raise TestimonialRenderError("Invalid base64 data in referenceImages data URL.") from exc
        if not data:
            raise TestimonialRenderError("Reference image data URL is empty.")
        return data, mime_type

    if source.startswith("http://") or source.startswith("https://"):
        resp = httpx.get(source, timeout=30.0)
        resp.raise_for_status()
        data = resp.content
        if not data:
            raise TestimonialRenderError("Reference image URL returned empty content.")
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not content_type:
            parsed = urlparse(source)
            guessed, _ = mimetypes.guess_type(parsed.path)
            content_type = (guessed or "image/png").lower()
        return data, content_type

    file_path = source.replace("file://", "", 1) if source.startswith("file://") else source
    path = Path(file_path)
    if not path.exists():
        raise TestimonialRenderError(f"Reference image file does not exist: {path}")
    data = path.read_bytes()
    if not data:
        raise TestimonialRenderError(f"Reference image file is empty: {path}")
    guessed, _ = mimetypes.guess_type(str(path))
    return data, (guessed or "image/png").lower()


def _build_reference_parts(
    *,
    reference_images: list[str] | None,
    base_dir: Path,
) -> list[dict[str, Any]]:
    if not reference_images:
        return []

    parts: list[dict[str, Any]] = []
    for raw in reference_images:
        if not isinstance(raw, str):
            raise TestimonialRenderError("referenceImages entries must be strings.")
        resolved_source = _resolve_reference_image_source(raw, base_dir=base_dir)
        data, mime_type = _read_reference_image_bytes(resolved_source)
        parts.append(
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            }
        )
    return parts


def _generate_nano_image_bytes(
    *,
    model: str,
    prompt: str,
    image_config: Any = None,
    reference_images: list[str] | None = None,
    reference_first: bool = False,
    base_dir: Path | None = None,
) -> tuple[bytes, str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise TestimonialRenderError("GEMINI_API_KEY is required to use Nano Banana.")

    if image_config is not None:
        if not isinstance(image_config, dict):
            raise TestimonialRenderError("imageConfig must be an object when provided.")
        if "imageSize" in image_config and model != "gemini-3-pro-image-preview":
            raise TestimonialRenderError(
                "imageConfig.imageSize is only supported for gemini-3-pro-image-preview."
            )

    resolved_base = base_dir or Path.cwd()
    reference_parts = _build_reference_parts(reference_images=reference_images, base_dir=resolved_base)
    text_part = {"text": prompt}
    ordered_parts = [*reference_parts, text_part] if reference_first else [text_part, *reference_parts]

    payload: dict[str, Any] = {"contents": [{"parts": ordered_parts}]}
    if image_config:
        payload["generationConfig"] = {"imageConfig": image_config}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    retries = 2
    last_summary: str | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 429 and attempt < retries:
                retry_after_raw = exc.response.headers.get("Retry-After") if exc.response is not None else None
                try:
                    retry_after = float(retry_after_raw) if retry_after_raw else 5.0 * (attempt + 1)
                except ValueError:
                    retry_after = 5.0 * (attempt + 1)
                time.sleep(max(retry_after, 1.0))
                continue
            body = exc.response.text if exc.response is not None else ""
            raise TestimonialRenderError(f"Nano Banana request failed (status={status}): {body}") from exc
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries:
                raise TestimonialRenderError(f"Nano Banana request failed: {exc}") from exc
            time.sleep(0.6 * (attempt + 1))
            continue
        data = resp.json()
        try:
            image_bytes, mime_type = _extract_first_inline_image(data)
            return image_bytes, mime_type
        except Exception as exc:  # noqa: BLE001
            last_summary = _summarize_gemini_response_for_debug(data)
            if attempt >= retries:
                raise TestimonialRenderError(
                    "Nano Banana did not return an image "
                    f"(attempts={retries + 1}). {last_summary}"
                ) from exc
            time.sleep(0.6 * (attempt + 1))
    raise TestimonialRenderError("Unreachable: Nano Banana retry loop exhausted.")


def maybe_generate_review_card_assets(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload or payload.get("template") != "review_card":
        return payload

    needs_avatar = bool(payload.get("avatarPrompt")) and not payload.get("avatarUrl")
    needs_hero = bool(payload.get("heroImagePrompt")) and not payload.get("heroImageUrl")
    if not needs_avatar and not needs_hero:
        return payload

    model = payload.get("imageModel") or os.getenv("NANO_BANANA_MODEL")
    if not isinstance(model, str) or not model.strip():
        raise TestimonialRenderError(
            "imageModel is required to generate testimonial images (set NANO_BANANA_MODEL or pass imageModel)."
        )

    output = dict(payload)
    if needs_avatar:
        avatar_prompt = payload.get("avatarPrompt")
        if not isinstance(avatar_prompt, str):
            raise TestimonialRenderError("avatarPrompt is required to generate the reviewer avatar.")
        avatar_buffer, mime_type = _generate_nano_image_bytes(
            model=model.strip(),
            prompt=avatar_prompt,
            image_config=payload.get("avatarImageConfig"),
        )
        output["avatarUrl"] = _to_data_url(avatar_buffer, mime_type)

    if needs_hero:
        hero_prompt = payload.get("heroImagePrompt")
        if not isinstance(hero_prompt, str):
            raise TestimonialRenderError("heroImagePrompt is required to generate the testimonial hero image.")
        hero_buffer, mime_type = _generate_nano_image_bytes(
            model=model.strip(),
            prompt=hero_prompt,
            image_config=payload.get("heroImageConfig"),
        )
        output["heroImageUrl"] = _to_data_url(hero_buffer, mime_type)

    return output


_PDP_TEMPLATES = {"pdp_ugc_standard", "pdp_qa_ugc", "pdp_bold_claim", "pdp_personal_highlight"}


def _resolve_pdp_preset(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, dict):
        return "tiktok"
    preset = output.get("preset")
    if preset is None:
        return "tiktok"
    if preset in {"tiktok", "feed", "square"}:
        return str(preset)
    raise TestimonialRenderError("output.preset must be one of: tiktok, feed, square")


def _aspect_ratio_for_preset(preset: str) -> str:
    if preset == "feed":
        return "4:5"
    if preset == "square":
        return "1:1"
    if preset == "tiktok":
        return "9:16"
    raise TestimonialRenderError(f"Unsupported output preset: {preset}")


def _bubble_space_hint_for_template(template: str) -> str:
    if template == "pdp_ugc_standard":
        return (
            "Leave clean negative space in the lower-left area for a small comment bubble overlay. "
            "Keep the product and hands on the right side of the frame and do not place the product in the lower-left."
        )
    if template == "pdp_qa_ugc":
        return (
            "Leave clean negative space in the top-right and lower-left for two small QA bubbles. "
            "Keep the product and hands around center-right and avoid placing key details in those bubble zones."
        )
    if template == "pdp_bold_claim":
        return (
            "Leave clean negative space in the top-right area for a small comment bubble overlay. "
            "Keep the product in the lower-middle or lower-left of the frame and do not place the product in the top-right."
        )
    if template == "pdp_personal_highlight":
        return (
            "Leave clean negative space in the top-left area for a small comment bubble overlay. "
            "Keep the product held lower-right or lower-middle, not in the top-left."
        )
    raise TestimonialRenderError(f"Unsupported PDP template: {template}")


def _base_ugc_style_block(aspect_ratio: str) -> str:
    return " ".join(
        [
            "Slightly off-center framing, a tiny bit of motion blur, natural skin texture with small imperfections, "
            "hair slightly messy, clothes lightly wrinkled.",
            "Mixed indoor lighting (warm lamp + daylight spill), auto white balance, auto exposure, mild digital noise "
            "and JPEG compression, soft focus (not razor sharp), realistic colors.",
            "Ordinary home background with a little clutter. No studio setup. No seamless backdrop. No dramatic lighting. No flash.",
            "No on-image text overlays, no captions, no watermarks, no UI elements.",
            f"{aspect_ratio} aspect ratio.",
        ]
    )


def _stringify_avoid(avoid: Any) -> str | None:
    if not isinstance(avoid, list) or len(avoid) == 0:
        return None
    cleaned = [str(item).strip() for item in avoid if isinstance(item, str) and str(item).strip()]
    if not cleaned:
        return None
    return f"Avoid: {'; '.join(cleaned)}."


def _build_pdp_background_prompt(*, template: str, preset: str, vars_payload: dict[str, Any]) -> str:
    if not isinstance(template, str) or not template.strip():
        raise TestimonialRenderError("template is required to build PDP background prompt.")
    if not isinstance(preset, str) or not preset.strip():
        raise TestimonialRenderError("preset is required to build PDP background prompt.")
    if not isinstance(vars_payload, dict):
        raise TestimonialRenderError("vars is required to build PDP background prompt.")

    aspect_ratio = _aspect_ratio_for_preset(preset)
    bubble_hint = _bubble_space_hint_for_template(template)
    product = vars_payload.get("product")
    if not isinstance(product, str) or not product.strip():
        raise TestimonialRenderError("background.promptVars.product is required to build PDP background prompt.")
    product = product.strip()
    subject = vars_payload.get("subject").strip() if isinstance(vars_payload.get("subject"), str) else ""
    scene = vars_payload.get("scene").strip() if isinstance(vars_payload.get("scene"), str) else ""
    extra = vars_payload.get("extra").strip() if isinstance(vars_payload.get("extra"), str) else ""
    avoid_line = _stringify_avoid(vars_payload.get("avoid"))

    lines: list[str] = []
    if template == "pdp_bold_claim":
        lines.append(
            f"A casual smartphone photo of {product} on a simple surface at home (not studio), photographed quickly by hand."
        )
        if scene:
            lines.append(f"Scene: {scene}.")
    else:
        who = subject if subject else "a real customer"
        lines.append(f"A casual, unposed smartphone photo of {who} holding {product}.")
        if scene:
            lines.append(f"Scene: {scene}.")

    lines.append(bubble_hint)
    lines.append(_base_ugc_style_block(aspect_ratio))
    if extra:
        lines.append(extra if extra.endswith(".") else f"{extra}.")
    if avoid_line:
        lines.append(avoid_line)
    return " ".join(lines)


def _dedupe_string_array(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        output.append(trimmed)
    return output


def _build_brand_prompt_guidance(brand: Any) -> str:
    if not isinstance(brand, dict):
        return ""
    clauses: list[str] = []
    if isinstance(brand.get("name"), str) and brand["name"].strip():
        clauses.append(f"Brand name: {brand['name'].strip()}.")
    if isinstance(brand.get("logoText"), str) and brand["logoText"].strip():
        clauses.append(f"Logo text: {brand['logoText'].strip()}.")
    if isinstance(brand.get("stripBgColor"), str) and brand["stripBgColor"].strip():
        clauses.append(f"Primary brand color: {brand['stripBgColor'].strip()}.")
    if isinstance(brand.get("stripTextColor"), str) and brand["stripTextColor"].strip():
        clauses.append(f"Contrast text color: {brand['stripTextColor'].strip()}.")

    assets = brand.get("assets")
    if isinstance(assets, dict):
        palette = assets.get("palette")
        if isinstance(palette, dict):
            palette_parts: list[str] = []
            if isinstance(palette.get("primary"), str) and palette["primary"].strip():
                palette_parts.append(f"primary {palette['primary'].strip()}")
            if isinstance(palette.get("secondary"), str) and palette["secondary"].strip():
                palette_parts.append(f"secondary {palette['secondary'].strip()}")
            if isinstance(palette.get("accent"), str) and palette["accent"].strip():
                palette_parts.append(f"accent {palette['accent'].strip()}")
            if palette_parts:
                clauses.append(f"Brand palette: {', '.join(palette_parts)}.")
        if isinstance(assets.get("notes"), str) and assets["notes"].strip():
            clauses.append(f"Brand styling notes: {assets['notes'].strip()}.")
        if isinstance(assets.get("logoUrl"), str) and assets["logoUrl"].strip():
            clauses.append("If any logo appears in frame, match the provided brand logo exactly.")
    return " ".join(clauses)


def _collect_brand_reference_images(brand: Any) -> list[str]:
    if not isinstance(brand, dict):
        return []
    assets = brand.get("assets")
    if not isinstance(assets, dict):
        return []
    refs: list[Any] = []
    if isinstance(assets.get("logoUrl"), str):
        refs.append(assets.get("logoUrl"))
    if isinstance(assets.get("referenceImages"), list):
        refs.extend(assets.get("referenceImages"))
    return _dedupe_string_array(refs)


def maybe_generate_pdp_background(payload: dict[str, Any]) -> dict[str, Any]:
    template = payload.get("template")
    if not isinstance(template, str) or template not in _PDP_TEMPLATES:
        return payload

    background = payload.get("background")
    if not isinstance(background, dict):
        return payload
    if background.get("imageUrl"):
        return payload

    has_prompt = isinstance(background.get("prompt"), str) and background.get("prompt").strip()
    has_vars = isinstance(background.get("promptVars"), dict)
    if not has_prompt and not has_vars:
        return payload

    model = background.get("imageModel") or payload.get("imageModel") or os.getenv("NANO_BANANA_MODEL")
    if not isinstance(model, str) or not model.strip():
        raise TestimonialRenderError(
            "imageModel is required to generate PDP images (set NANO_BANANA_MODEL or pass imageModel/background.imageModel)."
        )

    preset = _resolve_pdp_preset(payload)
    if has_prompt:
        base_prompt = str(background.get("prompt")).strip()
    else:
        base_prompt = _build_pdp_background_prompt(
            template=template,
            preset=preset,
            vars_payload=background.get("promptVars"),
        )
    brand_prompt_guidance = _build_brand_prompt_guidance(payload.get("brand"))
    prompt = f"{base_prompt} {brand_prompt_guidance}".strip() if brand_prompt_guidance else base_prompt

    image_config = background.get("imageConfig")
    if image_config is not None:
        if not isinstance(image_config, dict):
            raise TestimonialRenderError("background.imageConfig must be an object when provided.")
        if "aspectRatio" not in image_config:
            image_config = {**image_config, "aspectRatio": _aspect_ratio_for_preset(preset)}
    else:
        image_config = {"aspectRatio": _aspect_ratio_for_preset(preset)}

    background_reference_images = (
        background.get("referenceImages") if isinstance(background.get("referenceImages"), list) else []
    )
    brand_reference_images = _collect_brand_reference_images(payload.get("brand"))
    reference_images = _dedupe_string_array([*background_reference_images, *brand_reference_images])

    buffer, mime_type = _generate_nano_image_bytes(
        model=model.strip(),
        prompt=prompt,
        image_config=image_config,
        reference_images=reference_images,
        reference_first=bool(background.get("referenceFirst")),
        base_dir=Path.cwd(),
    )
    background_output: dict[str, Any] = {"imageUrl": _to_data_url(buffer, mime_type)}
    if isinstance(background.get("alt"), str) and background["alt"].strip():
        background_output["alt"] = background["alt"].strip()

    output = dict(payload)
    output["background"] = background_output
    return output


@dataclass
class RenderConfig:
    viewport_width: int = 1400
    viewport_height: int = 2000
    device_scale_factor: int = 2
    timeout_ms: int = 30_000


class TestimonialRenderer:
    def __init__(self, *, config: Optional[RenderConfig] = None):
        self._config = config or RenderConfig()
        self._playwright = None
        self._browser = None

    def __enter__(self) -> "TestimonialRenderer":
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError as exc:  # noqa: BLE001
            raise TestimonialRenderError(
                "playwright is required to render testimonials (pip install playwright; playwright install chromium)."
            ) from exc

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            raise TestimonialRenderError(f"Failed to launch chromium for testimonial rendering: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if self._browser is not None:
            try:
                self._browser.close()
            finally:
                self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            finally:
                self._playwright = None

    def render_png(self, payload: dict[str, Any]) -> bytes:
        if self._browser is None:
            raise TestimonialRenderError("Renderer is not started. Use TestimonialRenderer as a context manager.")

        validated_input = validate_payload(payload, base_dir=Path.cwd())
        hydrated = maybe_generate_pdp_background(maybe_generate_review_card_assets(validated_input))
        validated = validate_payload(hydrated, base_dir=Path.cwd())
        template_url = _resolve_template_url(validated["template"])

        page = self._browser.new_page(
            viewport={"width": self._config.viewport_width, "height": self._config.viewport_height},
            device_scale_factor=self._config.device_scale_factor,
        )
        page.set_default_timeout(self._config.timeout_ms)
        try:
            page.goto(template_url, wait_until="load")
            page.evaluate("(data) => window.setCardData(data)", validated)
            page.evaluate("() => document.fonts.ready")
            page.wait_for_load_state("networkidle")

            card = page.locator("#card")
            buffer = card.screenshot(type="png")
            if not buffer:
                raise TestimonialRenderError("Renderer returned empty image data.")
            return buffer
        finally:
            page.close()


@dataclass
class _RenderRequest:
    payload: dict[str, Any]
    response: "queue.Queue[tuple[bool, Any]]"


class ThreadedTestimonialRenderer:
    """
    Run the synchronous Playwright renderer inside a dedicated thread.

    Playwright's sync API raises if used inside an active asyncio event loop. Temporal workers and
    other async runtimes can end up invoking this renderer in such a context. By isolating the
    Playwright sync API to a background thread, we avoid that constraint while keeping the public
    API synchronous.
    """

    def __init__(
        self,
        *,
        config: Optional[RenderConfig] = None,
        worker_count: int = 1,
        response_timeout_ms: Optional[int] = None,
    ):
        self._config = config or RenderConfig()
        if worker_count <= 0:
            raise TestimonialRenderError("ThreadedTestimonialRenderer.worker_count must be >= 1.")
        self._worker_count = worker_count
        self._response_timeout_ms = response_timeout_ms or max(self._config.timeout_ms + 15_000, 45_000)
        if self._response_timeout_ms <= 0:
            raise TestimonialRenderError("ThreadedTestimonialRenderer.response_timeout_ms must be > 0.")
        self._requests: "queue.Queue[_RenderRequest | None]" = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._startup: "queue.Queue[tuple[bool, Exception | None]]" = queue.Queue()
        self._start_error: Exception | None = None

    def __enter__(self) -> "ThreadedTestimonialRenderer":
        def worker() -> None:
            try:
                with TestimonialRenderer(config=self._config) as renderer:
                    self._startup.put((True, None))
                    while True:
                        item = self._requests.get()
                        if item is None:
                            return
                        try:
                            result = renderer.render_png(item.payload)
                        except Exception as exc:  # noqa: BLE001
                            item.response.put((False, exc))
                        else:
                            item.response.put((True, result))
            except Exception as exc:  # noqa: BLE001
                self._start_error = exc
                self._startup.put((False, exc))
                while True:
                    try:
                        item = self._requests.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        continue
                    item.response.put((False, exc))

        self._threads = [
            threading.Thread(
                target=worker,
                name=f"testimonial-renderer-{idx + 1}",
                daemon=True,
            )
            for idx in range(self._worker_count)
        ]
        for thread in self._threads:
            thread.start()

        started_workers = 0
        while started_workers < self._worker_count:
            ok, error = self._startup.get()
            if not ok:
                self._start_error = error or RuntimeError("unknown testimonial renderer startup error")
                break
            started_workers += 1

        if self._start_error is not None:
            for _ in self._threads:
                self._requests.put(None)
            for thread in self._threads:
                thread.join(timeout=1.0)
            raise self._start_error
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if not self._threads:
            return
        for _ in self._threads:
            self._requests.put(None)
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []

    def render_png(self, payload: dict[str, Any], *, timeout_ms: Optional[int] = None) -> bytes:
        if not self._threads:
            raise TestimonialRenderError(
                "ThreadedTestimonialRenderer is not started. Use it as a context manager."
            )

        response: "queue.Queue[tuple[bool, Any]]" = queue.Queue(maxsize=1)
        self._requests.put(_RenderRequest(payload=payload, response=response))
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self._response_timeout_ms
        if effective_timeout_ms <= 0:
            raise TestimonialRenderError("render timeout must be > 0ms.")
        timeout_seconds = effective_timeout_ms / 1000.0
        try:
            ok, value = response.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            alive = sum(1 for thread in self._threads if thread.is_alive())
            raise TestimonialRenderError(
                "Timed out waiting for testimonial renderer output "
                f"(timeout={timeout_seconds:.1f}s, alive_workers={alive}/{len(self._threads)})."
            ) from exc
        if ok:
            return value
        raise value
