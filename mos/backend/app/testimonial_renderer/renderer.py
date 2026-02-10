from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from app.testimonial_renderer.validate import TestimonialRenderError, validate_payload


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _template_paths() -> dict[str, Path]:
    base = _package_dir() / "templates"
    return {
        "review_card": base / "review_card.html",
        "social_comment": base / "social_comment.html",
        "testimonial_media": base / "testimonial_media.html",
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


def _generate_nano_image_bytes(
    *,
    model: str,
    prompt: str,
    image_config: Any = None,
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

    payload: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
    if image_config:
        payload["generationConfig"] = {"imageConfig": image_config}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = httpx.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    image_bytes, mime_type = _extract_first_inline_image(data)
    return image_bytes, mime_type


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
            # Playwright typically throws a descriptive error if browsers are missing.
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

        hydrated = maybe_generate_review_card_assets(payload)
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
