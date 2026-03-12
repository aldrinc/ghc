from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import google.generativeai as genai
import httpx
from dotenv import load_dotenv
from PIL import Image

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
    PageFlyReconciliation,
    PageFlySlotAnalysis,
    PageFlySlotDecision,
    PageFlySlotPlanningResult,
    extract_pagefly_image_slots,
    plan_pagefly_product_references,
)
from app.services.swipe_prompt import (
    extract_new_image_prompt_from_markdown,
    inline_swipe_render_placeholders,
    load_swipe_to_image_ad_prompt,
)
from scripts.publish_pagefly_generated_slots import (
    PublishedReplacement,
    _build_s3_client,
    _default_public_base_url,
    _normalize_endpoint,
    _set_json_path_value,
    _upload_public_file,
    _write_pagefly_outputs,
)
from scripts.run_pagefly_swipe_prototype import (
    _build_pagefly_stage1_prompt_input,
    _build_prompt_context,
    _collect_remote_image_urls,
    _download_remote_images,
    _ensure_gemini_configured,
    _extract_gemini_text,
    _load_pagefly_json,
    _poll_image_job,
    _prepare_image_part,
    _resize_output_to_match_source_dimensions,
    _resolve_render_aspect_ratio,
    _select_research_excerpt,
    _slugify,
    _stage1_reference_slots,
    _write_pagefly_planning_artifacts,
)


@dataclass(frozen=True)
class GeneratedItemArtifact:
    slot_id: str
    item_id: str
    render_mode: str
    visual_goal: str
    original_url: str
    output_path: str
    width: int | None
    height: int | None
    target_json_paths: list[str]
    stage1_prompt_input_path: str
    stage1_prompt_output_path: str
    stage1_image_prompt_path: str
    stage1_placeholder_map_path: str


def _slot_artifact_paths(*, run_dir: Path, slot_id: str) -> dict[str, Path]:
    slot_dir = run_dir / "slots" / slot_id
    return {
        "slot_dir": slot_dir,
        "output_path": slot_dir / "generated_images" / "generated_00.png",
        "stage1_prompt_input_path": slot_dir / "stage1_prompt_input.txt",
        "stage1_prompt_output_path": slot_dir / "stage1_prompt_output.md",
        "stage1_image_prompt_path": slot_dir / "stage1_image_prompt.txt",
        "stage1_placeholder_map_path": slot_dir / "stage1_placeholder_map.json",
    }


def _restore_slot_from_manifest(slot_payload: dict[str, Any]) -> PageFlyImageSlot:
    dimensions = slot_payload.get("dimensions")
    if not isinstance(dimensions, dict):
        dimensions = {}
    analysis_payload = slot_payload.get("analysis")
    decision_payload = slot_payload.get("decision")
    selection_score = slot_payload.get("selectionScore")
    return PageFlyImageSlot(
        slot_id=str(slot_payload.get("slotId") or "").strip(),
        item_id=str(slot_payload.get("itemId") or "").strip(),
        item_type=str(slot_payload.get("itemType") or "").strip() or "unknown",
        root_order=int(slot_payload.get("rootOrder") or 0),
        json_path=str(slot_payload.get("jsonPath") or "").strip(),
        url=str(slot_payload.get("imageUrl") or "").strip(),
        local_path=str(slot_payload.get("localPath") or "").strip(),
        content_type=(
            str(slot_payload.get("contentType")).strip()
            if isinstance(slot_payload.get("contentType"), str)
            else None
        ),
        width=int(dimensions["width"]) if isinstance(dimensions.get("width"), int) else None,
        height=int(dimensions["height"]) if isinstance(dimensions.get("height"), int) else None,
        alt_text=str(slot_payload.get("altText")).strip()
        if isinstance(slot_payload.get("altText"), str) and str(slot_payload.get("altText")).strip()
        else None,
        ancestor_types=[
            str(value).strip()
            for value in slot_payload.get("ancestorTypes", [])
            if isinstance(value, str) and value.strip()
        ],
        ancestor_ids=[],
        nearby_text=[
            str(value).strip()
            for value in slot_payload.get("nearbyText", [])
            if isinstance(value, str) and value.strip()
        ],
        section_text=[
            str(value).strip()
            for value in slot_payload.get("sectionText", [])
            if isinstance(value, str) and value.strip()
        ],
        section_root_id=str(slot_payload.get("sectionRootId")).strip()
        if isinstance(slot_payload.get("sectionRootId"), str) and str(slot_payload.get("sectionRootId")).strip()
        else None,
        section_root_type=str(slot_payload.get("sectionRootType")).strip()
        if isinstance(slot_payload.get("sectionRootType"), str) and str(slot_payload.get("sectionRootType")).strip()
        else None,
        analysis=PageFlySlotAnalysis.model_validate(analysis_payload)
        if isinstance(analysis_payload, dict)
        else None,
        decision=PageFlySlotDecision.model_validate(decision_payload)
        if isinstance(decision_payload, dict)
        else None,
        selection_score=float(selection_score) if isinstance(selection_score, (int, float)) else None,
        selected_as_sample=bool(slot_payload.get("selectedAsSample")),
    )


def _restore_planning_result(*, run_dir: Path) -> tuple[PageFlySlotPlanningResult, Path, Path]:
    slots_path = run_dir / "pagefly_slots.json"
    reference_plan_path = run_dir / "pagefly_reference_plan.json"
    if not slots_path.exists() or not reference_plan_path.exists():
        raise RuntimeError(
            "Resume run directory is missing PageFly planning artifacts. "
            f"Expected both {slots_path} and {reference_plan_path}."
        )

    raw_slots = json.loads(slots_path.read_text(encoding="utf-8"))
    if not isinstance(raw_slots, list) or not raw_slots:
        raise RuntimeError(f"Invalid or empty PageFly slots artifact: {slots_path}")
    slots = [_restore_slot_from_manifest(slot_payload) for slot_payload in raw_slots if isinstance(slot_payload, dict)]
    if not slots:
        raise RuntimeError(f"No restorable slots found in PageFly slots artifact: {slots_path}")

    reference_plan_payload = json.loads(reference_plan_path.read_text(encoding="utf-8"))
    if not isinstance(reference_plan_payload, dict):
        raise RuntimeError(f"Invalid PageFly reference plan artifact: {reference_plan_path}")
    reconciliation = PageFlyReconciliation.model_validate(
        {
            "referenceSlotIds": reference_plan_payload.get("referenceSlotIds", []),
            "slotDecisions": reference_plan_payload.get("slotDecisions", []),
            "notes": reference_plan_payload.get("notes", []),
        }
    )
    decisions_by_slot_id = {
        decision.slot_id: decision for decision in reconciliation.slot_decisions
    }
    for slot in slots:
        if slot.slot_id in decisions_by_slot_id:
            slot.decision = decisions_by_slot_id[slot.slot_id]

    reference_slot_ids = set(reconciliation.reference_slot_ids)
    reference_slots = [slot for slot in slots if slot.slot_id in reference_slot_ids]
    return (
        PageFlySlotPlanningResult(
            slots=slots,
            reconciliation=reconciliation,
            reference_slots=reference_slots,
        ),
        slots_path,
        reference_plan_path,
    )


def _load_existing_generated_item(
    *,
    slot: PageFlyImageSlot,
    planning_result: PageFlySlotPlanningResult,
    run_dir: Path,
) -> GeneratedItemArtifact | None:
    decision = slot.decision
    if decision is None:
        raise RuntimeError(f"Representative slot is missing a planner decision: {slot.slot_id}")

    paths = _slot_artifact_paths(run_dir=run_dir, slot_id=slot.slot_id)
    output_path = paths["output_path"]
    if not output_path.exists():
        return None

    required_paths = [
        paths["stage1_prompt_input_path"],
        paths["stage1_prompt_output_path"],
        paths["stage1_image_prompt_path"],
        paths["stage1_placeholder_map_path"],
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise RuntimeError(
            "Resume detected a partially written slot artifact set. "
            f"slot_id={slot.slot_id} missing={missing}"
        )

    with Image.open(output_path) as rendered_image:
        width = int(rendered_image.width)
        height = int(rendered_image.height)

    return GeneratedItemArtifact(
        slot_id=slot.slot_id,
        item_id=slot.item_id,
        render_mode=decision.render_mode,
        visual_goal=decision.visual_goal,
        original_url=slot.url,
        output_path=str(output_path),
        width=width,
        height=height,
        target_json_paths=_target_json_paths_for_item(slots=planning_result.slots, item_id=slot.item_id),
        stage1_prompt_input_path=str(paths["stage1_prompt_input_path"]),
        stage1_prompt_output_path=str(paths["stage1_prompt_output_path"]),
        stage1_image_prompt_path=str(paths["stage1_image_prompt_path"]),
        stage1_placeholder_map_path=str(paths["stage1_placeholder_map_path"]),
    )


def _representative_slots(slots: list[PageFlyImageSlot]) -> list[PageFlyImageSlot]:
    grouped: dict[str, list[PageFlyImageSlot]] = defaultdict(list)
    for slot in slots:
        grouped[slot.item_id].append(slot)

    representatives: list[PageFlyImageSlot] = []
    for item_id, item_slots in grouped.items():
        decisions = [slot.decision for slot in item_slots if slot.decision is not None]
        if not decisions or len(decisions) != len(item_slots):
            raise RuntimeError(f"Every slot for item {item_id} must have a planner decision.")
        render_modes = {decision.render_mode for decision in decisions}
        if len(render_modes) != 1:
            raise RuntimeError(
                f"PageFly item {item_id} has inconsistent render modes across slots: {sorted(render_modes)}"
            )

        def area(slot: PageFlyImageSlot) -> int:
            width = slot.width if isinstance(slot.width, int) and slot.width > 0 else 0
            height = slot.height if isinstance(slot.height, int) and slot.height > 0 else 0
            return width * height

        def preferred_path_rank(slot: PageFlyImageSlot) -> int:
            path = slot.json_path.lower()
            if "originalsrc" in path:
                return 0
            if "transformedsrc" in path:
                return 2
            return 1

        chosen = sorted(
            item_slots,
            key=lambda slot: (
                -area(slot),
                preferred_path_rank(slot),
                slot.root_order,
                slot.slot_id,
            ),
        )[0]
        representatives.append(chosen)

    representatives.sort(key=lambda slot: (slot.root_order, slot.slot_id))
    return representatives


def _target_json_paths_for_item(*, slots: list[PageFlyImageSlot], item_id: str) -> list[str]:
    paths = sorted({slot.json_path for slot in slots if slot.item_id == item_id})
    if not paths:
        raise RuntimeError(f"No json paths found for PageFly item {item_id}")
    return paths


def _render_item(
    *,
    slot: PageFlyImageSlot,
    planning_result: PageFlySlotPlanningResult,
    prompt_template: str,
    prompt_model_client: Any,
    brand_name: str,
    product_name: str,
    angle: str,
    hook: str | None,
    research_excerpt: str,
    pagefly_entry_name: str,
    downloaded_images: list[Any],
    render_model_id: str,
    creative_client: CreativeServiceClient,
    requested_aspect_ratio: str,
    run_dir: Path,
) -> GeneratedItemArtifact:
    decision = slot.decision
    if decision is None:
        raise RuntimeError(f"Selected slot is missing a planner decision: {slot.slot_id}")

    sample_dir = run_dir / "slots" / slot.slot_id
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_reference_path, sample_mime = _prepare_image_part(
        Path(slot.local_path),
        output_dir=sample_dir / "sample",
    )
    stage1_reference_slots = _stage1_reference_slots(
        planning_result=planning_result,
        selected_slot=slot,
    )
    stage1_reference_parts: list[tuple[PageFlyImageSlot, Path, str]] = []
    for reference_slot in stage1_reference_slots:
        if not reference_slot.local_path:
            raise RuntimeError(f"Reference slot is missing local_path: {reference_slot.slot_id}")
        reference_path, reference_mime = _prepare_image_part(
            Path(reference_slot.local_path),
            output_dir=sample_dir / "sample",
        )
        stage1_reference_parts.append((reference_slot, reference_path, reference_mime))

    stage1_prompt_input = _build_pagefly_stage1_prompt_input(
        prompt_template=prompt_template,
        brand_name=brand_name,
        angle=angle,
        selected_slot=slot,
        planning_result=planning_result,
        reference_slots=stage1_reference_slots,
    )
    prompt_context_parts = _build_prompt_context(
        brand_name=brand_name,
        product_name=product_name,
        angle=angle,
        hook=hook,
        selected_slot=slot,
        planning_result=planning_result,
        stage1_reference_slots=stage1_reference_slots,
        downloaded_images=downloaded_images,
        research_excerpt=research_excerpt,
        pagefly_entry_name=pagefly_entry_name,
    )

    stage1_contents: list[Any] = [stage1_prompt_input, *prompt_context_parts]
    stage1_contents.append({"mime_type": sample_mime, "data": sample_reference_path.read_bytes()})
    for reference_slot, reference_path, reference_mime in stage1_reference_parts:
        stage1_contents.append(
            f"Canonical product reference image for PageFly slot {reference_slot.slot_id} is attached below."
        )
        stage1_contents.append({"mime_type": reference_mime, "data": reference_path.read_bytes()})

    raw_output = _extract_gemini_text(
        prompt_model_client.generate_content(
            stage1_contents,
            request_options={"timeout": 180},
        )
    )
    if not raw_output:
        raise RuntimeError(f"Gemini returned no text for slot {slot.slot_id}.")

    stage1_prompt_input_path = sample_dir / "stage1_prompt_input.txt"
    stage1_prompt_input_path.write_text(stage1_prompt_input, encoding="utf-8")
    stage1_prompt_output_path = sample_dir / "stage1_prompt_output.md"
    stage1_prompt_output_path.write_text(raw_output, encoding="utf-8")

    raw_image_prompt = extract_new_image_prompt_from_markdown(raw_output)
    image_prompt, placeholder_map = inline_swipe_render_placeholders(raw_image_prompt)

    stage1_image_prompt_path = sample_dir / "stage1_image_prompt.txt"
    stage1_image_prompt_path.write_text(image_prompt, encoding="utf-8")
    stage1_placeholder_map_path = sample_dir / "stage1_placeholder_map.json"
    stage1_placeholder_map_path.write_text(
        json.dumps(placeholder_map, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    request_id = f"pagefly-full-batch-{run_dir.name}-{slot.slot_id}"
    render_aspect_ratio = _resolve_render_aspect_ratio(
        selected_slot=slot,
        requested_aspect_ratio=requested_aspect_ratio,
    )
    created_job = creative_client.create_image_ads(
        payload=CreativeServiceImageAdsCreateIn(
            prompt=image_prompt,
            count=1,
            aspect_ratio=render_aspect_ratio,
            model_id=str(render_model_id),
            client_request_id=request_id,
        ),
        idempotency_key=request_id,
    )
    completed_job = _poll_image_job(client=creative_client, job_id=created_job.id)
    if completed_job.status != "succeeded":
        raise RuntimeError(
            f"Image generation failed for slot {slot.slot_id} "
            f"(job_id={completed_job.id}): {completed_job.error_detail or 'unknown error'}"
        )
    if not completed_job.outputs:
        raise RuntimeError(f"Image generation returned no outputs for slot {slot.slot_id}.")
    primary_output = completed_job.outputs[0]
    if not primary_output.primary_url:
        raise RuntimeError(f"Image generation output missing primary_url for slot {slot.slot_id}.")

    output_dir = sample_dir / "generated_images"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "generated_00.png"
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        payload = client.get(primary_output.primary_url).content
        if not payload:
            raise RuntimeError(f"Downloaded generated output is empty for slot {slot.slot_id}.")
        output_path.write_bytes(payload)
    _resize_output_to_match_source_dimensions(output_path=output_path, selected_slot=slot)

    with Image.open(output_path) as rendered_image:
        width = int(rendered_image.width)
        height = int(rendered_image.height)

    return GeneratedItemArtifact(
        slot_id=slot.slot_id,
        item_id=slot.item_id,
        render_mode=decision.render_mode,
        visual_goal=decision.visual_goal,
        original_url=slot.url,
        output_path=str(output_path),
        width=width,
        height=height,
        target_json_paths=_target_json_paths_for_item(slots=planning_result.slots, item_id=slot.item_id),
        stage1_prompt_input_path=str(stage1_prompt_input_path),
        stage1_prompt_output_path=str(stage1_prompt_output_path),
        stage1_image_prompt_path=str(stage1_image_prompt_path),
        stage1_placeholder_map_path=str(stage1_placeholder_map_path),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate PageFly replacement images for every image item, upload them to a public Hetzner bucket, "
            "and emit a rewritten import-ready PageFly export."
        )
    )
    parser.add_argument("--pagefly", required=True, help="Path to the source .pagefly export or raw JSON file.")
    parser.add_argument("--brand-name", required=True, help="Brand name for swipe adaptation.")
    parser.add_argument("--product-name", required=True, help="Product name for swipe adaptation.")
    parser.add_argument("--angle", required=True, help="Angle to use for all page assets.")
    parser.add_argument("--hook", default=None, help="Optional hook/headline guidance for the run.")
    parser.add_argument(
        "--research-file",
        required=True,
        help="Grounding document to use for the batch run. This must cover the supplied angle.",
    )
    parser.add_argument(
        "--prompt-model",
        default=None,
        help="Stage-one Gemini prompt model. Defaults to SWIPE_PROMPT_MODEL from the backend .env.",
    )
    parser.add_argument(
        "--render-model-id",
        default=None,
        help="Stage-two creative service render model id. Defaults to SWIPE_IMAGE_RENDER_MODEL.",
    )
    parser.add_argument("--count", type=int, default=1, help="Outputs per slot. Must remain 1 for rewrite flow.")
    parser.add_argument(
        "--research-max-chars",
        type=int,
        default=12000,
        help="Max characters to include from the research file after excerpt selection.",
    )
    parser.add_argument("--bucket-name", required=True, help="Public Hetzner bucket name.")
    parser.add_argument("--bucket-endpoint", required=True, help="Hetzner object storage endpoint.")
    parser.add_argument("--bucket-region", default="hel1", help="Hetzner bucket region.")
    parser.add_argument("--bucket-access-key", required=True, help="Hetzner bucket access key.")
    parser.add_argument("--bucket-secret-key", required=True, help="Hetzner bucket secret key.")
    parser.add_argument(
        "--public-base-url",
        default=None,
        help="Optional public base URL for the bucket. Defaults to https://<bucket>.<endpoint-host>.",
    )
    parser.add_argument(
        "--key-prefix",
        default="pagefly-generated",
        help="Object key prefix inside the public bucket.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT_DIR / "tmp" / "pagefly-full-batch"),
        help="Base output directory for batch artifacts.",
    )
    parser.add_argument(
        "--resume-run-dir",
        default=None,
        help="Existing full-batch run directory to resume without re-planning or re-rendering completed slots.",
    )
    args = parser.parse_args()
    if int(args.count) != 1:
        raise RuntimeError("Full PageFly batch rewrite requires --count=1 so each item maps to one output.")

    load_dotenv(ROOT_DIR / ".env", override=False)

    pagefly_path = Path(args.pagefly).expanduser().resolve()
    research_path = Path(args.research_file).expanduser().resolve()
    out_root = Path(args.out_dir).expanduser().resolve()
    if isinstance(args.resume_run_dir, str) and args.resume_run_dir.strip():
        run_dir = Path(args.resume_run_dir).expanduser().resolve()
        if not run_dir.exists() or not run_dir.is_dir():
            raise RuntimeError(f"Resume run directory not found: {run_dir}")
    else:
        run_dir = out_root / f"{_slugify(pagefly_path.stem)}-{time.strftime('%Y%m%d-%H%M%S')}"
        run_dir.mkdir(parents=True, exist_ok=True)

    pagefly_entry_name, page_data = _load_pagefly_json(pagefly_path)

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

    if isinstance(args.resume_run_dir, str) and args.resume_run_dir.strip():
        planning_result, slots_artifact_path, reference_plan_path = _restore_planning_result(run_dir=run_dir)
        downloaded_images: list[Any] = sorted({slot.url for slot in planning_result.slots})
    else:
        url_paths = _collect_remote_image_urls(page_data)
        downloaded_images = _download_remote_images(url_paths, output_dir=run_dir / "downloaded_images")
        pagefly_slots = extract_pagefly_image_slots(page_data=page_data, downloaded_images=downloaded_images)
        planning_result = plan_pagefly_product_references(
            model=str(prompt_model).strip(),
            brand_name=args.brand_name,
            product_name=args.product_name,
            angle=args.angle,
            hook=args.hook,
            slots=pagefly_slots,
        )
        slots_artifact_path, reference_plan_path = _write_pagefly_planning_artifacts(
            planning_result=planning_result,
            run_dir=run_dir,
        )
    representative_slots = _representative_slots(planning_result.slots)

    prompt_template, prompt_sha = load_swipe_to_image_ad_prompt()
    _ensure_gemini_configured()
    model_name = prompt_model if str(prompt_model).startswith("models/") else f"models/{prompt_model}"
    prompt_model_client = genai.GenerativeModel(
        model_name=model_name,
        generation_config={"temperature": 0.2, "max_output_tokens": 8000},
    )
    try:
        creative_client = CreativeServiceClient()
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    generated_items: list[GeneratedItemArtifact] = []
    completed_item_ids: set[str] = set()
    for slot in representative_slots:
        existing = _load_existing_generated_item(
            slot=slot,
            planning_result=planning_result,
            run_dir=run_dir,
        )
        if existing is None:
            continue
        generated_items.append(existing)
        completed_item_ids.add(existing.item_id)

    total_items = len(representative_slots)
    for index, slot in enumerate(representative_slots, start=1):
        if slot.item_id in completed_item_ids:
            print(
                f"[{index}/{total_items}] Skipping {slot.slot_id} item={slot.item_id} (already rendered)",
                flush=True,
            )
            continue
        decision = slot.decision
        mode = decision.render_mode if decision else "unknown"
        print(
            f"[{index}/{total_items}] Rendering {slot.slot_id} item={slot.item_id} mode={mode}",
            flush=True,
        )
        generated = _render_item(
            slot=slot,
            planning_result=planning_result,
            prompt_template=prompt_template,
            prompt_model_client=prompt_model_client,
            brand_name=args.brand_name,
            product_name=args.product_name,
            angle=args.angle,
            hook=args.hook,
            research_excerpt=research_excerpt,
            pagefly_entry_name=pagefly_entry_name,
            downloaded_images=downloaded_images,
            render_model_id=render_model_id,
            creative_client=creative_client,
            requested_aspect_ratio="1:1",
            run_dir=run_dir,
        )
        generated_items.append(generated)
        completed_item_ids.add(generated.item_id)

    endpoint = _normalize_endpoint(args.bucket_endpoint)
    public_base_url = (
        str(args.public_base_url).strip().rstrip("/")
        if isinstance(args.public_base_url, str) and args.public_base_url.strip()
        else _default_public_base_url(bucket=args.bucket_name, endpoint=endpoint)
    )
    s3_client = _build_s3_client(
        endpoint=endpoint,
        access_key=args.bucket_access_key,
        secret_key=args.bucket_secret_key,
        region=str(args.bucket_region).strip(),
    )

    rewritten_payload = json.loads(json.dumps(page_data))
    published_replacements: list[PublishedReplacement] = []
    for artifact in generated_items:
        public_url = _upload_public_file(
            s3_client=s3_client,
            bucket=args.bucket_name,
            public_base_url=public_base_url,
            key_prefix=str(args.key_prefix).strip(),
            pagefly_stem=pagefly_path.stem,
            slot_id=artifact.slot_id,
            local_path=Path(artifact.output_path),
            verify_public_url=True,
        )
        for json_path in artifact.target_json_paths:
            _set_json_path_value(rewritten_payload, json_path, public_url)
        published_replacements.append(
            PublishedReplacement(
                slot_id=artifact.slot_id,
                item_id=artifact.item_id,
                render_mode=artifact.render_mode,
                original_url=artifact.original_url,
                generated_local_path=artifact.output_path,
                public_url=public_url,
                width=artifact.width,
                height=artifact.height,
                target_json_paths=artifact.target_json_paths,
            )
        )

    rewritten_json_path, rewritten_pagefly_path, upload_manifest_path = _write_pagefly_outputs(
        original_pagefly_path=pagefly_path,
        entry_name=pagefly_entry_name,
        rewritten_payload=rewritten_payload,
        replacements=published_replacements,
        out_dir=run_dir / "published",
    )

    batch_manifest = {
        "pagefly_export": str(pagefly_path),
        "pagefly_entry_name": pagefly_entry_name,
        "brand_name": args.brand_name,
        "product_name": args.product_name,
        "angle": args.angle,
        "hook": args.hook,
        "prompt_model": prompt_model,
        "render_model_id": render_model_id,
        "prompt_template_sha256": prompt_sha,
        "downloaded_image_count": len(downloaded_images),
        "slot_count": len(planning_result.slots),
        "item_count": len(representative_slots),
        "pagefly_slots_path": str(slots_artifact_path),
        "pagefly_reference_plan_path": str(reference_plan_path),
        "public_base_url": public_base_url,
        "rewritten_json_path": str(rewritten_json_path),
        "rewritten_pagefly_path": str(rewritten_pagefly_path),
        "upload_manifest_path": str(upload_manifest_path),
        "generated_items": [
            {
                "slotId": artifact.slot_id,
                "itemId": artifact.item_id,
                "renderMode": artifact.render_mode,
                "visualGoal": artifact.visual_goal,
                "originalUrl": artifact.original_url,
                "outputPath": artifact.output_path,
                "width": artifact.width,
                "height": artifact.height,
                "targetJsonPaths": artifact.target_json_paths,
                "stage1PromptInputPath": artifact.stage1_prompt_input_path,
                "stage1PromptOutputPath": artifact.stage1_prompt_output_path,
                "stage1ImagePromptPath": artifact.stage1_image_prompt_path,
                "stage1PlaceholderMapPath": artifact.stage1_placeholder_map_path,
            }
            for artifact in generated_items
        ],
        "published_replacements": [
            {
                "slotId": replacement.slot_id,
                "itemId": replacement.item_id,
                "renderMode": replacement.render_mode,
                "originalUrl": replacement.original_url,
                "generatedLocalPath": replacement.generated_local_path,
                "publicUrl": replacement.public_url,
                "width": replacement.width,
                "height": replacement.height,
                "targetJsonPaths": replacement.target_json_paths,
            }
            for replacement in published_replacements
        ],
    }
    batch_manifest_path = run_dir / "pagefly_full_batch_manifest.json"
    batch_manifest_path.write_text(
        json.dumps(batch_manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Full batch run directory: {run_dir}")
    print(f"Rendered item count: {len(generated_items)}")
    print(f"Public asset base URL: {public_base_url}")
    print(f"Rewritten PageFly export: {rewritten_pagefly_path}")
    print(f"Upload manifest: {upload_manifest_path}")
    print(f"Batch manifest: {batch_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
