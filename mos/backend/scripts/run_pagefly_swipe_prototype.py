from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from io import BytesIO
from math import gcd
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import unquote, urlparse

import google.generativeai as genai
import httpx
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services.creative_service_client import (
    CreativeServiceClient,
    CreativeServiceConfigError,
)
from app.services.pagefly_swipe_planner import (
    PageFlyImageSlot,
    PageFlySlotPlanningResult,
    extract_pagefly_image_slots,
    plan_pagefly_product_references,
)
from app.services.swipe_prompt import (
    build_swipe_context_block,
    extract_new_image_prompt_from_markdown,
    inline_swipe_render_placeholders,
    load_swipe_to_image_ad_prompt,
)


HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}
SAFE_FILE_CHARS_RE = re.compile(r"[^a-zA-Z0-9._-]+")
DEFAULT_RESEARCH_KEYWORDS = (
    "contraindication",
    "contraindications",
    "interaction",
    "interactions",
    "screen",
    "screening",
    "workflow",
    "safety",
    "safe",
    "medication",
    "pharmacist",
    "doctor",
    "drug",
    "blood thinner",
)


@dataclass
class DownloadedImage:
    url: str
    json_paths: list[str] = field(default_factory=list)
    local_path: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    pil_format: str | None = None
    pil_mode: str | None = None
    is_animated: bool = False
    analysis_error: str | None = None
    download_error: str | None = None
    selection_score: float | None = None
    selected_as_sample: bool = False


def _extract_gemini_text(result: Any) -> str | None:
    try:
        text = getattr(result, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(result, "candidates", None)
    if not candidates:
        return None
    first = candidates[0]
    if not first:
        return None
    content = getattr(first, "content", None)
    parts = getattr(content, "parts", None) if content else None
    if not parts:
        return None

    texts: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text:
            texts.append(part_text)
    joined = "\n".join(texts).strip()
    return joined or None


def _poll_image_job(
    client: CreativeServiceClient,
    job_id: str,
    *,
    timeout_seconds: float = 300.0,
    interval_seconds: float = 2.0,
):
    start = time.monotonic()
    while True:
        job = client.get_image_ads_job(job_id=job_id)
        if job.status in ("succeeded", "failed"):
            return job
        if (time.monotonic() - start) > timeout_seconds:
            raise RuntimeError(f"Timed out waiting for image job completion (job_id={job_id})")
        time.sleep(interval_seconds)


def _slugify(value: str) -> str:
    stripped = SAFE_FILE_CHARS_RE.sub("-", value.strip())
    return stripped.strip("-") or "file"


def _iter_json_strings(node: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            yield from _iter_json_strings(value, child_path)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            child_path = f"{path}[{index}]"
            yield from _iter_json_strings(value, child_path)
        return
    if isinstance(node, str):
        yield path, node


def _load_pagefly_json(pagefly_path: Path) -> tuple[str, dict[str, Any]]:
    if not pagefly_path.exists() or not pagefly_path.is_file():
        raise RuntimeError(f"PageFly export not found: {pagefly_path}")

    if pagefly_path.suffix.lower() == ".json":
        data = json.loads(pagefly_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError(f"PageFly JSON must be an object: {pagefly_path}")
        return pagefly_path.name, data

    with zipfile.ZipFile(pagefly_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise RuntimeError(
                "Expected PageFly export zip to contain exactly one JSON file. "
                f"Found {len(names)} files."
            )
        entry_name = names[0]
        data = json.loads(archive.read(entry_name))
        if not isinstance(data, dict):
            raise RuntimeError(f"PageFly export payload must be a JSON object: {entry_name}")
        return entry_name, data


def _collect_remote_image_urls(page_data: dict[str, Any]) -> dict[str, list[str]]:
    url_paths: dict[str, list[str]] = defaultdict(list)
    for json_path, raw_string in _iter_json_strings(page_data):
        for match in HTTP_URL_RE.findall(raw_string):
            parsed = urlparse(match)
            suffix = Path(unquote(parsed.path)).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS:
                continue
            url_paths[match].append(json_path)
    if not url_paths:
        raise RuntimeError("No remote image URLs were found in the PageFly export.")
    return dict(url_paths)


def _analyze_image_bytes(payload: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(payload)) as image:
            return {
                "width": int(image.width),
                "height": int(image.height),
                "pil_format": image.format,
                "pil_mode": image.mode,
                "is_animated": bool(getattr(image, "is_animated", False)),
            }
    except (UnidentifiedImageError, OSError) as exc:
        return {"analysis_error": str(exc)}


def _download_remote_images(
    url_paths: dict[str, list[str]],
    *,
    output_dir: Path,
) -> list[DownloadedImage]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[DownloadedImage] = []
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for index, url in enumerate(sorted(url_paths.keys()), start=1):
            parsed = urlparse(url)
            base_name = Path(unquote(parsed.path)).name or f"image-{index}"
            base_name = _slugify(base_name)
            suffix = Path(base_name).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS:
                suffix = ".img"
            local_path = output_dir / f"{index:02d}_{base_name}"
            record = DownloadedImage(url=url, json_paths=sorted(set(url_paths[url])))
            try:
                response = client.get(url)
                response.raise_for_status()
                payload = response.content
                if not payload:
                    raise RuntimeError("Downloaded image payload is empty.")
                local_path.write_bytes(payload)
                record.local_path = str(local_path)
                record.content_type = response.headers.get("content-type", "").split(";")[0].strip() or None
                record.file_size_bytes = len(payload)
                record.sha256 = hashlib.sha256(payload).hexdigest()
                record_analysis = _analyze_image_bytes(payload)
                for key, value in record_analysis.items():
                    setattr(record, key, value)
            except Exception as exc:  # noqa: BLE001
                record.download_error = str(exc)
            downloaded.append(record)
    return downloaded


def _selection_score(record: DownloadedImage) -> float:
    if record.download_error:
        return -1000.0
    if record.analysis_error:
        return -500.0
    name = Path(record.local_path or record.url).name.lower()
    score = 0.0
    if record.content_type in {"image/gif", "image/svg+xml"}:
        score -= 200.0
    if record.is_animated:
        score -= 150.0
    if any(token in name for token in ("logo", "icon", "refund", "delivery", "chat", "secure-payment", "badge")):
        score -= 60.0
    if record.width and record.height:
        score += min(record.width, 2048) / 128.0
        score += min(record.height, 2048) / 128.0
        aspect_ratio = record.width / record.height
        score -= abs(aspect_ratio - 1.0) * 12.0
        if min(record.width, record.height) >= 512:
            score += 15.0
    if record.content_type in {"image/png", "image/jpeg", "image/webp"}:
        score += 8.0
    if any("items" in json_path for json_path in record.json_paths):
        score += 4.0
    return score


def _select_sample_image(downloaded_images: list[DownloadedImage]) -> DownloadedImage:
    best: DownloadedImage | None = None
    for record in downloaded_images:
        record.selection_score = _selection_score(record)
        if best is None or (record.selection_score or -1000.0) > (best.selection_score or -1000.0):
            best = record
    if best is None or best.download_error or not best.local_path:
        raise RuntimeError("Unable to select a usable sample image from the downloaded PageFly assets.")
    best.selected_as_sample = True
    return best


def _prepare_image_part(image_path: Path, *, output_dir: Path) -> tuple[Path, str]:
    suffix = image_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        return image_path, mime

    output_dir.mkdir(parents=True, exist_ok=True)
    converted_path = output_dir / f"{image_path.stem}.png"
    with Image.open(image_path) as image:
        converted = image.convert("RGBA")
        converted.save(converted_path, format="PNG")
    return converted_path, "image/png"


def _normalize_prompt_value(value: str | None) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "[UNKNOWN]"


def _build_swipe_stage1_prompt_input_verbatim(
    *,
    prompt_template: str,
    brand_name: str,
    angle: str | None,
) -> str:
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        raise ValueError("swipe stage-1 prompt template is required and must be non-empty.")
    clean_brand = _normalize_prompt_value(brand_name)
    clean_angle = _normalize_prompt_value(angle)
    return (
        f"{prompt_template.strip()}\n\n"
        "RUNTIME INPUTS (INJECTED)\n"
        f"Brand: {clean_brand}\n"
        f"Angle: {clean_angle}\n"
        "Competitor swipe image is attached as image input."
    )


def _stage1_reference_slots(
    *,
    planning_result: PageFlySlotPlanningResult,
    selected_slot: PageFlyImageSlot,
) -> list[PageFlyImageSlot]:
    selected_decision = selected_slot.decision
    if selected_decision is None:
        raise RuntimeError(f"Selected slot is missing reconciliation decision: {selected_slot.slot_id}")
    if selected_decision.render_mode != "requires_reference":
        return []

    reference_slots = [
        slot for slot in planning_result.reference_slots if slot.slot_id != selected_slot.slot_id
    ]
    if reference_slots:
        return reference_slots

    if any(slot.slot_id == selected_slot.slot_id for slot in planning_result.reference_slots):
        return [selected_slot]

    raise RuntimeError(
        "Selected PageFly slot requires product reference imagery, but the planner did not "
        f"produce any usable reference slots (selected_slot_id={selected_slot.slot_id})."
    )


def _select_sample_slot(
    *,
    planning_result: PageFlySlotPlanningResult,
    downloaded_images: list[DownloadedImage],
    sample_render_mode: Literal["auto", "context_only", "requires_reference"],
) -> PageFlyImageSlot:
    download_by_url = {record.url: record for record in downloaded_images}
    ready_slots = [
        slot for slot in planning_result.slots if slot.decision is not None and slot.decision.status == "ready"
    ]
    if not ready_slots:
        raise RuntimeError(
            "PageFly slot planning marked every slot as needs_review. "
            "Inspect the planner artifacts before generating a prototype image."
        )

    if sample_render_mode == "context_only":
        candidate_slots = [
            slot
            for slot in ready_slots
            if slot.decision is not None and slot.decision.render_mode == "context_only"
        ]
    elif sample_render_mode == "requires_reference":
        candidate_slots = [
            slot
            for slot in ready_slots
            if slot.decision is not None and slot.decision.render_mode == "requires_reference"
        ]
    else:
        candidate_slots = ready_slots
    if not candidate_slots:
        raise RuntimeError(
            "No ready PageFly slots matched the requested sample render mode. "
            f"requested_mode={sample_render_mode}"
        )
    reference_slot_ids = {slot.slot_id for slot in planning_result.reference_slots}

    def looks_like_step_icon(slot: PageFlyImageSlot) -> bool:
        name = Path(slot.local_path).name.lower()
        if re.match(r"^\d+_[123](?:[_-]|$)", name):
            return True
        nearby = [str(item).strip().lower() for item in slot.nearby_text]
        if any(re.match(r"^step\s+\d+", item) for item in nearby):
            return True
        if any(re.fullmatch(r"[123]\.png__pid:.*", item) for item in nearby):
            return True
        return False

    best_slot: PageFlyImageSlot | None = None
    best_score = float("-inf")
    for slot in candidate_slots:
        downloaded = download_by_url.get(slot.url)
        if downloaded is None:
            raise RuntimeError(f"Missing downloaded image metadata for planned slot URL: {slot.url}")
        base_score = downloaded.selection_score
        if base_score is None:
            base_score = _selection_score(downloaded)
            downloaded.selection_score = base_score

        score = float(base_score)
        decision = slot.decision
        analysis = slot.analysis
        if decision is not None and decision.render_mode == "requires_reference":
            score += 35.0
            if decision.reference_prominence == "primary":
                score += 8.0
            elif decision.reference_prominence == "secondary":
                score += 5.0
        elif decision is not None and decision.render_mode == "context_only":
            score += 8.0
        if analysis is not None and analysis.is_product_reference_candidate:
            score += 12.0
        if analysis is not None and analysis.image_intent == "logo":
            score -= 90.0
        if analysis is not None and analysis.image_intent == "badge":
            score -= 40.0
        if analysis is not None and analysis.section_purpose in {"feature", "comparison", "infographic", "gallery"}:
            score += 6.0
        if analysis is not None and analysis.image_intent in {"education", "product_support", "decorative"}:
            score += 8.0
        if slot.slot_id in reference_slot_ids:
            score -= 8.0
        if slot.item_type in {"MediaMain2", "ProductMedia2"}:
            score += 10.0
        if looks_like_step_icon(slot):
            score -= 60.0
        if sample_render_mode == "context_only":
            if decision is not None and decision.render_mode != "context_only":
                score -= 120.0
            if slot.width and slot.height and min(slot.width, slot.height) < 256:
                score -= 80.0
            if analysis is not None and analysis.is_product_reference_candidate:
                score -= 120.0
        if sample_render_mode == "requires_reference" and decision is not None and decision.render_mode != "requires_reference":
            score -= 120.0
        slot.selection_score = score
        if best_slot is None or score > best_score:
            best_slot = slot
            best_score = score

    if best_slot is None:
        raise RuntimeError("Unable to choose a sample PageFly slot for the prototype run.")
    best_slot.selected_as_sample = True
    return best_slot


def _build_pagefly_stage1_prompt_input(
    *,
    prompt_template: str,
    brand_name: str,
    angle: str | None,
    selected_slot: PageFlyImageSlot,
    planning_result: PageFlySlotPlanningResult,
    reference_slots: list[PageFlyImageSlot],
) -> str:
    selected_decision = selected_slot.decision
    if selected_decision is None:
        raise RuntimeError(f"Selected slot is missing a planner decision: {selected_slot.slot_id}")
    if not isinstance(selected_slot.width, int) or selected_slot.width <= 0:
        raise RuntimeError(f"Selected slot is missing a valid source width: {selected_slot.slot_id}")
    if not isinstance(selected_slot.height, int) or selected_slot.height <= 0:
        raise RuntimeError(f"Selected slot is missing a valid source height: {selected_slot.slot_id}")

    base_prompt = _build_swipe_stage1_prompt_input_verbatim(
        prompt_template=prompt_template,
        brand_name=brand_name,
        angle=angle,
    )
    source_aspect_ratio = _aspect_ratio_from_dimensions(width=selected_slot.width, height=selected_slot.height)
    if selected_decision.render_mode == "requires_reference":
        reference_line = (
            "Product reference image inputs are attached below and must be used to preserve product identity."
        )
        mode_guidance = (
            "Render mode is requires_reference. Use the selected slot image for composition cues, "
            "but preserve the actual product identity from the attached canonical references. "
            "The final output must match the original source asset dimensions."
        )
    else:
        reference_line = (
            "No product reference image inputs are attached for this selected slot."
        )
        mode_guidance = (
            "Render mode is context_only. Use the selected slot image for composition and layout cues only. "
            "Generate a new image from the selected section's copy and visualGoal instead of preserving the "
            "sampled asset's product identity. The final output must match the original source asset dimensions."
        )
    planning_payload = {
        "selectedSlot": selected_slot.llm_summary(),
        "selectedSourceAsset": {
            "width": selected_slot.width,
            "height": selected_slot.height,
            "aspectRatio": source_aspect_ratio,
        },
        "selectedSlotDecision": selected_decision.model_dump(mode="json", by_alias=True),
        "selectedSlotAnalysis": (
            selected_slot.analysis.model_dump(mode="json", by_alias=True) if selected_slot.analysis else None
        ),
        "referenceSlots": [slot.llm_summary() for slot in reference_slots],
        "pageReferenceSlotIds": [slot.slot_id for slot in planning_result.reference_slots],
        "pagePlannerNotes": list(planning_result.reconciliation.notes),
    }
    return (
        f"{base_prompt}\n\n"
        "PAGEFLY SLOT PLANNING INPUTS (ADDITIONAL)\n"
        "Use this as extra grounding for the stage-1 analysis. Keep the original swipe prompt instructions above intact.\n"
        f"{mode_guidance}\n"
        f"{reference_line}\n"
        f"{json.dumps(planning_payload, ensure_ascii=False, indent=2)}"
    )


def _tokenize_keywords(*values: str) -> list[str]:
    keywords: list[str] = []
    for value in values:
        lower = value.strip().lower()
        if not lower:
            continue
        keywords.append(lower)
        for piece in re.split(r"[^a-z0-9]+", lower):
            if len(piece) >= 4:
                keywords.append(piece)
    for keyword in DEFAULT_RESEARCH_KEYWORDS:
        keywords.append(keyword)
    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        if keyword in seen:
            continue
        seen.add(keyword)
        deduped.append(keyword)
    return deduped


def _select_research_excerpt(
    research_path: Path,
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    max_chars: int,
) -> str:
    if not research_path.exists() or not research_path.is_file():
        raise RuntimeError(f"Research file not found: {research_path}")

    raw_text = research_path.read_text(encoding="utf-8")
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", raw_text) if chunk.strip()]
    keywords = _tokenize_keywords(brand_name, product_name, angle, hook or "")

    selected: list[str] = []
    seen: set[str] = set()
    total_chars = 0
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        if paragraph in seen:
            continue
        projected = total_chars + len(paragraph) + 2
        if projected > max_chars:
            break
        selected.append(paragraph)
        seen.add(paragraph)
        total_chars = projected

    if not selected:
        raise RuntimeError(
            "No research excerpts matched the brand/product/angle keywords. "
            "Provide a research file that actually covers the requested angle."
        )

    return "\n\n".join(selected)


def _ensure_gemini_configured() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    genai.configure(api_key=api_key)


def _build_prompt_context(
    *,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    selected_slot: PageFlyImageSlot,
    planning_result: PageFlySlotPlanningResult,
    stage1_reference_slots: list[PageFlyImageSlot],
    downloaded_images: list[DownloadedImage],
    research_excerpt: str,
    pagefly_entry_name: str,
) -> list[Any]:
    selected_decision = selected_slot.decision
    if selected_decision is None:
        raise RuntimeError(f"Selected slot is missing a planner decision: {selected_slot.slot_id}")
    if not isinstance(selected_slot.width, int) or selected_slot.width <= 0:
        raise RuntimeError(f"Selected slot is missing a valid source width: {selected_slot.slot_id}")
    if not isinstance(selected_slot.height, int) or selected_slot.height <= 0:
        raise RuntimeError(f"Selected slot is missing a valid source height: {selected_slot.slot_id}")
    source_aspect_ratio = _aspect_ratio_from_dimensions(width=selected_slot.width, height=selected_slot.height)

    mode_specific_constraints = [
        "Use the selected page image as the swipe reference.",
    ]
    mode_specific_visual_guidelines = [
        "Respect the original swipe composition and layout energy.",
        "Keep the output suitable for a high-CTR paid social style creative.",
    ]
    mode_specific_constraints.append(
        f"Match the original source asset dimensions ({selected_slot.width}x{selected_slot.height}) and "
        f"aspect ratio ({source_aspect_ratio})."
    )
    if selected_decision.render_mode == "requires_reference":
        mode_specific_constraints.append(
            "Preserve the actual product identity using the attached canonical product reference images."
        )
    else:
        mode_specific_constraints.append(
            "For context_only slots, treat the selected page image as a composition reference only and derive the "
            "new visual subject from the section copy and visualGoal."
        )
        mode_specific_visual_guidelines.append(
            "Generate a fresh visual subject that matches the selected section's message instead of copying the "
            "sampled asset's identity."
        )

    context_block = build_swipe_context_block(
        brand_name=brand_name,
        product_name=product_name,
        creative_concept="PageFly image adaptation prototype",
        channel="sales-page-image-refresh",
        angle=angle,
        hook=hook,
        constraints=[
            "Do not invent medical claims beyond what the provided research supports.",
            "Output a render-ready prompt that can be sent directly to the image renderer.",
            *mode_specific_constraints,
        ],
        tone_guidelines=[
            "Direct, clear, benefit-led.",
            "Preserve the strongest visual composition cues from the swipe reference.",
            "Stay aligned to the supplied research angle instead of generic herbal claims.",
        ],
        visual_guidelines=mode_specific_visual_guidelines,
    )

    sample_summary = {
        "pageflyEntry": pagefly_entry_name,
        "remoteImageCount": len(downloaded_images),
        "slotCount": len(planning_result.slots),
        "selectedSlot": selected_slot.manifest_summary(),
        "selectedSourceAsset": {
            "width": selected_slot.width,
            "height": selected_slot.height,
            "aspectRatio": source_aspect_ratio,
        },
        "selectedRenderMode": selected_decision.render_mode,
        "selectedVisualGoal": selected_decision.visual_goal,
        "referenceSlotIds": [slot.slot_id for slot in planning_result.reference_slots],
        "stage1ReferenceSlotIds": [slot.slot_id for slot in stage1_reference_slots],
        "pagePlannerNotes": list(planning_result.reconciliation.notes),
    }

    return [
        context_block,
        "## PAGE EXPORT SLOT ANALYSIS\n" + json.dumps(sample_summary, ensure_ascii=False, indent=2),
        "## RESEARCH EXCERPT\n" + research_excerpt,
    ]


def _write_pagefly_planning_artifacts(
    *,
    planning_result: PageFlySlotPlanningResult,
    run_dir: Path,
) -> tuple[Path, Path]:
    slots_path = run_dir / "pagefly_slots.json"
    slots_path.write_text(
        json.dumps(
            [slot.manifest_summary() for slot in planning_result.slots],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    plan_payload = {
        "referenceSlotIds": list(planning_result.reconciliation.reference_slot_ids),
        "requiresReferenceSlotIds": [
            slot.slot_id
            for slot in planning_result.slots
            if slot.decision is not None and slot.decision.render_mode == "requires_reference"
        ],
        "contextOnlySlotIds": [
            slot.slot_id
            for slot in planning_result.slots
            if slot.decision is not None and slot.decision.render_mode == "context_only"
        ],
        "notes": list(planning_result.reconciliation.notes),
        "slotDecisions": [
            decision.model_dump(mode="json", by_alias=True)
            for decision in planning_result.reconciliation.slot_decisions
        ],
        "referenceSlots": [slot.manifest_summary() for slot in planning_result.reference_slots],
    }
    plan_path = run_dir / "pagefly_reference_plan.json"
    plan_path.write_text(
        json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return slots_path, plan_path


def _create_preview_sheet(reference_path: Path, output_path: Path, preview_path: Path) -> None:
    canvas = Image.new("RGB", (1600, 900), color="#f4efe6")
    draw = ImageDraw.Draw(canvas)
    draw.text((60, 30), "Swipe Reference", fill="#1f1f1f")
    draw.text((860, 30), "Generated Output", fill="#1f1f1f")

    with Image.open(reference_path) as reference_image:
        reference_rgb = reference_image.convert("RGB")
        reference_fit = ImageOps.contain(reference_rgb, (640, 760))
    with Image.open(output_path) as output_image:
        output_rgb = output_image.convert("RGB")
        output_fit = ImageOps.contain(output_rgb, (640, 760))

    canvas.paste(reference_fit, (60, 90))
    canvas.paste(output_fit, (860, 90))
    canvas.save(preview_path, format="PNG")


def _aspect_ratio_from_dimensions(*, width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive to derive an aspect ratio.")
    divisor = gcd(width, height)
    normalized_width = width // divisor
    normalized_height = height // divisor
    return f"{normalized_width}:{normalized_height}"


def _resolve_render_aspect_ratio(
    *,
    selected_slot: PageFlyImageSlot,
    requested_aspect_ratio: str,
) -> str:
    decision = selected_slot.decision
    if decision is None:
        raise RuntimeError(f"Selected slot is missing a planner decision: {selected_slot.slot_id}")
    if not isinstance(selected_slot.width, int) or selected_slot.width <= 0:
        return requested_aspect_ratio
    if not isinstance(selected_slot.height, int) or selected_slot.height <= 0:
        return requested_aspect_ratio
    return _aspect_ratio_from_dimensions(width=selected_slot.width, height=selected_slot.height)


def _resize_output_to_match_source_dimensions(
    *,
    output_path: Path,
    selected_slot: PageFlyImageSlot,
) -> None:
    if not isinstance(selected_slot.width, int) or selected_slot.width <= 0:
        return
    if not isinstance(selected_slot.height, int) or selected_slot.height <= 0:
        return
    with Image.open(output_path) as output_image:
        resized = output_image.convert("RGBA").resize(
            (selected_slot.width, selected_slot.height),
            resample=Image.Resampling.LANCZOS,
        )
        resized.save(output_path, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse a PageFly export, download its remote images, and run a sample image through the swipe-image pipeline."
    )
    parser.add_argument("--pagefly", required=True, help="Path to a .pagefly export or raw JSON file.")
    parser.add_argument("--brand-name", required=True, help="Brand name for swipe adaptation.")
    parser.add_argument("--product-name", required=True, help="Product name for swipe adaptation.")
    parser.add_argument("--angle", required=True, help="Angle to use for the prototype.")
    parser.add_argument("--hook", default=None, help="Optional hook/headline guidance for the prototype.")
    parser.add_argument(
        "--research-file",
        required=True,
        help="Grounding document to use for the prototype. This must cover the supplied angle.",
    )
    parser.add_argument("--aspect-ratio", default="1:1", help="Creative service aspect ratio (default: 1:1).")
    parser.add_argument("--count", type=int, default=1, help="Number of output images to save (default: 1).")
    parser.add_argument(
        "--prompt-model",
        default=None,
        help="Stage-one Gemini prompt model. Defaults to SWIPE_PROMPT_MODEL from the backend .env.",
    )
    parser.add_argument(
        "--render-model-id",
        default=None,
        help="Stage-two creative service render model id. Defaults to SWIPE_IMAGE_RENDER_MODEL from the backend .env.",
    )
    parser.add_argument(
        "--research-max-chars",
        type=int,
        default=12000,
        help="Max characters to include from the research file after excerpt selection.",
    )
    parser.add_argument(
        "--sample-render-mode",
        choices=("auto", "context_only", "requires_reference"),
        default="auto",
        help="Which kind of PageFly slot to sample for the prototype run.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT_DIR / "tmp" / "pagefly-swipe-prototype"),
        help="Base output directory for prototype artifacts.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT_DIR / ".env", override=False)

    pagefly_path = Path(args.pagefly).expanduser().resolve()
    research_path = Path(args.research_file).expanduser().resolve()
    out_root = Path(args.out_dir).expanduser().resolve()
    run_dir = out_root / f"{_slugify(pagefly_path.stem)}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    pagefly_entry_name, page_data = _load_pagefly_json(pagefly_path)
    url_paths = _collect_remote_image_urls(page_data)
    downloaded_images = _download_remote_images(url_paths, output_dir=run_dir / "downloaded_images")

    research_excerpt = _select_research_excerpt(
        research_path,
        brand_name=args.brand_name,
        product_name=args.product_name,
        angle=args.angle,
        hook=args.hook,
        max_chars=args.research_max_chars,
    )

    prompt_model = args.prompt_model or os.getenv("SWIPE_PROMPT_MODEL")
    if not prompt_model or not str(prompt_model).strip():
        raise RuntimeError("No prompt model configured. Pass --prompt-model or set SWIPE_PROMPT_MODEL.")

    render_model_id = args.render_model_id or os.getenv("SWIPE_IMAGE_RENDER_MODEL")
    if not render_model_id or not str(render_model_id).strip():
        raise RuntimeError(
            "No render model configured. Pass --render-model-id or set SWIPE_IMAGE_RENDER_MODEL."
        )
    render_model_id = str(render_model_id).strip()
    if render_model_id.startswith("gemini-"):
        render_model_id = f"models/{render_model_id}"

    pagefly_slots = extract_pagefly_image_slots(page_data=page_data, downloaded_images=downloaded_images)
    planning_result = plan_pagefly_product_references(
        model=str(prompt_model).strip(),
        brand_name=args.brand_name,
        product_name=args.product_name,
        angle=args.angle,
        hook=args.hook,
        slots=pagefly_slots,
    )
    selected_slot = _select_sample_slot(
        planning_result=planning_result,
        downloaded_images=downloaded_images,
        sample_render_mode=args.sample_render_mode,
    )
    if not selected_slot.local_path:
        raise RuntimeError(f"Selected PageFly slot is missing a local_path: {selected_slot.slot_id}")
    stage1_reference_slots = _stage1_reference_slots(
        planning_result=planning_result,
        selected_slot=selected_slot,
    )
    render_aspect_ratio = _resolve_render_aspect_ratio(
        selected_slot=selected_slot,
        requested_aspect_ratio=str(args.aspect_ratio),
    )

    sample_reference_path, sample_mime = _prepare_image_part(
        Path(selected_slot.local_path),
        output_dir=run_dir / "sample",
    )
    stage1_reference_parts: list[tuple[PageFlyImageSlot, Path, str]] = []
    for reference_slot in stage1_reference_slots:
        if not reference_slot.local_path:
            raise RuntimeError(f"Reference slot is missing local_path: {reference_slot.slot_id}")
        reference_path, reference_mime = _prepare_image_part(
            Path(reference_slot.local_path),
            output_dir=run_dir / "sample",
        )
        stage1_reference_parts.append((reference_slot, reference_path, reference_mime))

    slots_artifact_path, reference_plan_path = _write_pagefly_planning_artifacts(
        planning_result=planning_result,
        run_dir=run_dir,
    )

    prompt_template, prompt_sha = load_swipe_to_image_ad_prompt()
    stage1_prompt_input = _build_pagefly_stage1_prompt_input(
        prompt_template=prompt_template,
        brand_name=args.brand_name,
        angle=args.angle,
        selected_slot=selected_slot,
        planning_result=planning_result,
        reference_slots=stage1_reference_slots,
    )
    prompt_context_parts = _build_prompt_context(
        brand_name=args.brand_name,
        product_name=args.product_name,
        angle=args.angle,
        hook=args.hook,
        selected_slot=selected_slot,
        planning_result=planning_result,
        stage1_reference_slots=stage1_reference_slots,
        downloaded_images=downloaded_images,
        research_excerpt=research_excerpt,
        pagefly_entry_name=pagefly_entry_name,
    )

    _ensure_gemini_configured()
    model_name = prompt_model if prompt_model.startswith("models/") else f"models/{prompt_model}"
    sample_bytes = sample_reference_path.read_bytes()
    model_client = genai.GenerativeModel(
        model_name=model_name,
        generation_config={"temperature": 0.2, "max_output_tokens": 8000},
    )
    stage1_contents: list[Any] = [stage1_prompt_input, *prompt_context_parts]
    stage1_contents.append({"mime_type": sample_mime, "data": sample_bytes})
    for reference_slot, reference_path, reference_mime in stage1_reference_parts:
        stage1_contents.append(
            f"Canonical product reference image for PageFly slot {reference_slot.slot_id} is attached below."
        )
        stage1_contents.append({"mime_type": reference_mime, "data": reference_path.read_bytes()})
    raw_output = _extract_gemini_text(
        model_client.generate_content(
            stage1_contents,
            request_options={"timeout": 180},
        )
    )
    if not raw_output:
        raise RuntimeError("Gemini returned no text for the swipe prompt output.")

    stage1_prompt_input_path = run_dir / "stage1_prompt_input.txt"
    stage1_prompt_input_path.write_text(stage1_prompt_input, encoding="utf-8")
    prompt_markdown_path = run_dir / "stage1_prompt_output.md"
    prompt_markdown_path.write_text(raw_output, encoding="utf-8")

    raw_image_prompt = extract_new_image_prompt_from_markdown(raw_output)
    image_prompt, placeholder_map = inline_swipe_render_placeholders(raw_image_prompt)

    image_prompt_path = run_dir / "stage1_image_prompt.txt"
    image_prompt_path.write_text(image_prompt, encoding="utf-8")
    placeholder_map_path = run_dir / "stage1_placeholder_map.json"
    placeholder_map_path.write_text(json.dumps(placeholder_map, indent=2, sort_keys=True), encoding="utf-8")

    try:
        creative_client = CreativeServiceClient()
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    request_id = f"pagefly-swipe-prototype-{run_dir.name}"

    created_job = creative_client.create_image_ads(
        payload=CreativeServiceImageAdsCreateIn(
            prompt=image_prompt,
            count=int(args.count),
            aspect_ratio=render_aspect_ratio,
            model_id=str(render_model_id),
            client_request_id=request_id,
        ),
        idempotency_key=request_id,
    )
    completed_job = _poll_image_job(client=creative_client, job_id=created_job.id)
    if completed_job.status != "succeeded":
        raise RuntimeError(
            f"Image generation failed (job_id={completed_job.id}): {completed_job.error_detail or 'unknown error'}"
        )

    output_dir = run_dir / "generated_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[str] = []
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        for index, output in enumerate(completed_job.outputs[: int(args.count)]):
            if not output.primary_url:
                raise RuntimeError(f"Missing primary_url for generated output index {index}.")
            payload = client.get(output.primary_url).content
            if not payload:
                raise RuntimeError(f"Downloaded output payload is empty for generated output index {index}.")
            output_path = output_dir / f"generated_{index:02d}.png"
            output_path.write_bytes(payload)
            _resize_output_to_match_source_dimensions(
                output_path=output_path,
                selected_slot=selected_slot,
            )
            output_paths.append(str(output_path))

    output_dimensions: list[dict[str, int | None]] = []
    for output_path in output_paths:
        with Image.open(output_path) as generated_image:
            output_dimensions.append(
                {
                    "width": int(generated_image.width),
                    "height": int(generated_image.height),
                }
            )

    preview_path = run_dir / "reference_vs_output.png"
    _create_preview_sheet(sample_reference_path, Path(output_paths[0]), preview_path)

    manifest = {
        "pagefly_export": str(pagefly_path),
        "pagefly_entry_name": pagefly_entry_name,
        "brand_name": args.brand_name,
        "product_name": args.product_name,
        "angle": args.angle,
        "hook": args.hook,
        "planner_model": str(prompt_model).strip(),
        "prompt_model": prompt_model,
        "render_model_id": render_model_id,
        "requested_aspect_ratio": args.aspect_ratio,
        "resolved_render_aspect_ratio": render_aspect_ratio,
        "research_file": str(research_path),
        "prompt_template_sha256": prompt_sha,
        "downloaded_image_count": len(downloaded_images),
        "selected_sample_slot_id": selected_slot.slot_id,
        "selected_sample_url": selected_slot.url,
        "selected_sample_local_path": str(sample_reference_path),
        "selected_sample_source_dimensions": {
            "width": selected_slot.width,
            "height": selected_slot.height,
        },
        "requested_sample_render_mode": args.sample_render_mode,
        "selected_sample_render_mode": (
            selected_slot.decision.render_mode if selected_slot.decision else None
        ),
        "selected_sample_visual_goal": (
            selected_slot.decision.visual_goal if selected_slot.decision else None
        ),
        "selected_sample_requires_product_reference": (
            selected_slot.decision.should_use_product_reference if selected_slot.decision else None
        ),
        "selected_sample_reference_prominence": (
            selected_slot.decision.reference_prominence if selected_slot.decision else None
        ),
        "stage1_reference_slot_ids": [slot.slot_id for slot in stage1_reference_slots],
        "stage1_reference_image_paths": [str(path) for _slot, path, _mime in stage1_reference_parts],
        "generated_image_paths": output_paths,
        "generated_image_dimensions": output_dimensions,
        "comparison_preview_path": str(preview_path),
        "stage1_prompt_input_path": str(stage1_prompt_input_path),
        "stage1_prompt_output_path": str(prompt_markdown_path),
        "stage1_image_prompt_path": str(image_prompt_path),
        "stage1_placeholder_map_path": str(placeholder_map_path),
        "pagefly_slots_path": str(slots_artifact_path),
        "pagefly_reference_plan_path": str(reference_plan_path),
        "pagefly_reference_slot_ids": [slot.slot_id for slot in planning_result.reference_slots],
        "downloaded_images": [asdict(record) for record in downloaded_images],
        "pagefly_slots": [slot.manifest_summary() for slot in planning_result.slots],
    }
    manifest_path = run_dir / "prototype_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Prototype run directory: {run_dir}")
    print(f"Downloaded remote images: {len(downloaded_images)}")
    print(f"Extracted PageFly slots: {len(planning_result.slots)}")
    print(f"Selected sample slot: {selected_slot.slot_id} ({sample_reference_path})")
    print(f"PageFly slot plan: {reference_plan_path}")
    print(f"Rendered output image: {output_paths[0]}")
    print(f"Comparison preview: {preview_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
