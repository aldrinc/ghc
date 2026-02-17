from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, List

import httpx
import google.generativeai as genai

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.services.creative_service_client import (
    CreativeServiceClient,
    CreativeServiceConfigError,
)
from app.services.swipe_prompt import (
    build_swipe_context_block,
    extract_new_image_prompt_from_markdown,
    load_swipe_to_image_ad_prompt,
)


def _ensure_gemini_configured() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")
    genai.configure(api_key=api_key)


def _select_research_lines(text: str, *, keywords: List[str], limit: int) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    selected: List[str] = []
    seen: set[str] = set()
    for ln in lines:
        lower = ln.lower()
        if not any(k in lower for k in keywords):
            continue
        if ln in seen:
            continue
        seen.add(ln)
        selected.append(ln)
        if len(selected) >= limit:
            break
    return selected


def _poll_image_job(client: CreativeServiceClient, job_id: str, *, timeout_seconds: float = 300.0, interval: float = 2.0):
    start = time.monotonic()
    while True:
        job = client.get_image_ads_job(job_id=job_id)
        if job.status in ("succeeded", "failed"):
            return job
        if (time.monotonic() - start) > timeout_seconds:
            raise RuntimeError(f"Timed out waiting for image job completion (job_id={job_id})")
        time.sleep(interval)


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

    texts: List[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str) and part_text:
            texts.append(part_text)
    joined = "\n".join(texts).strip()
    return joined or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo: swipe image -> prompt -> Freestyle image ad")
    parser.add_argument("--swipe-image", required=True, help="Path to a competitor swipe image file (jpg/png).")
    parser.add_argument("--brand-name", required=True, help="Brand name (e.g., The honest herbalist).")
    parser.add_argument("--product", required=True, help="Product name (e.g., the honest herbalist handbook).")
    parser.add_argument("--angle", required=True, help="Angle to use (e.g., Dosage or it's not a guide).")
    parser.add_argument("--research-file", required=True, help="Path to a research document (text/markdown).")
    parser.add_argument("--aspect-ratio", default="1:1", help="Aspect ratio for creative service (default: 1:1).")
    parser.add_argument("--count", type=int, default=1, help="Number of images to render (default: 1).")
    parser.add_argument("--max-output-tokens", type=int, default=6000)
    parser.add_argument("--model", default=None, help="Gemini model name. If omitted, SWIPE_PROMPT_MODEL must be set.")
    parser.add_argument("--render", action="store_true", help="If set, render images via creative service.")
    parser.add_argument("--out-dir", default=".", help="Directory to write rendered images into (default: .).")
    args = parser.parse_args()

    swipe_path = Path(args.swipe_image).expanduser().resolve()
    if not swipe_path.exists() or not swipe_path.is_file():
        raise RuntimeError(f"Swipe image not found: {swipe_path}")

    research_path = Path(args.research_file).expanduser().resolve()
    if not research_path.exists() or not research_path.is_file():
        raise RuntimeError(f"Research file not found: {research_path}")

    model = args.model or os.getenv("SWIPE_PROMPT_MODEL")
    if not model or not str(model).strip():
        raise RuntimeError("Provide --model or set SWIPE_PROMPT_MODEL.")

    swipe_bytes = swipe_path.read_bytes()
    if not swipe_bytes:
        raise RuntimeError(f"Swipe image file is empty: {swipe_path}")
    mime = "image/jpeg" if swipe_path.suffix.lower() in (".jpg", ".jpeg") else "image/png" if swipe_path.suffix.lower() == ".png" else None
    if not mime:
        raise RuntimeError(f"Unsupported swipe image extension: {swipe_path.suffix}")

    research_text = research_path.read_text(encoding="utf-8")
    keywords = ["dosage", "dose", "safe", "safety", "harm", "harmless", "interaction", "blood thinner", "respect"]
    research_lines = _select_research_lines(research_text, keywords=keywords, limit=50)
    if not research_lines:
        raise RuntimeError("No research lines matched the demo keywords; provide a more relevant research file.")

    prompt_template, _prompt_sha = load_swipe_to_image_ad_prompt()
    context_block = build_swipe_context_block(
        brand_name=args.brand_name,
        product_name=args.product,
        audience=None,
        brand_colors_fonts=None,
        must_avoid_claims=None,
        assets=None,
    )

    _ensure_gemini_configured()
    model_name = model if model.startswith("models/") else f"models/{model}"
    generation_config = {"temperature": 0.2, "max_output_tokens": int(args.max_output_tokens)}
    model_client = genai.GenerativeModel(model_name=model_name, generation_config=generation_config)
    contents: List[Any] = [context_block, prompt_template, {"mime_type": mime, "data": swipe_bytes}]
    result = model_client.generate_content(contents, request_options={"timeout": 120})
    raw_output = _extract_gemini_text(result)
    if not raw_output:
        raise RuntimeError("Gemini returned no text")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_out_path = out_dir / f"swipe_prompt_output_{swipe_path.stem}.md"
    prompt_out_path.write_text(raw_output, encoding="utf-8")

    image_prompt = extract_new_image_prompt_from_markdown(raw_output)

    sys.stdout.write("\n=== SWIPE PROMPT OUTPUT (MARKDOWN) ===\n\n")
    sys.stdout.write(f"[Saved full markdown to: {prompt_out_path}]\n\n")
    sys.stdout.write(raw_output.strip() + "\n")
    sys.stdout.write("\n=== IMAGE PROMPT (EXTRACTED) ===\n\n")
    sys.stdout.write(image_prompt.strip() + "\n")
    sys.stdout.flush()

    if not args.render:
        return 0

    try:
        creative_client = CreativeServiceClient()
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    upload = creative_client.upload_asset(
        kind="image",
        source="upload",
        file_name=swipe_path.name,
        file_bytes=swipe_bytes,
        content_type=mime,
        title="Competitor swipe reference",
        description="Competitor swipe reference for layout/composition (do not copy branding)",
        metadata_json={"source": "swipe_demo", "path": str(swipe_path)},
        generate_proxy=True,
    )
    swipe_asset_id = (upload.id or "").strip()
    if not swipe_asset_id:
        raise RuntimeError("Creative service returned empty asset id for uploaded swipe reference")

    render_count = max(6, int(args.count))
    job = creative_client.create_image_ads(
        payload=CreativeServiceImageAdsCreateIn(
            prompt=image_prompt,
            reference_asset_ids=[swipe_asset_id],
            count=render_count,
            aspect_ratio=str(args.aspect_ratio),
            client_request_id=None,
        ),
        idempotency_key="swipe-demo-" + swipe_asset_id[:24],
    )
    completed = _poll_image_job(creative_client, job.id)
    if completed.status != "succeeded":
        raise RuntimeError(f"Creative service job failed (job_id={completed.id}): {completed.error_detail or 'unknown error'}")

    for idx, output in enumerate(completed.outputs[: int(args.count)]):
        if not output.primary_url:
            raise RuntimeError(f"Missing primary_url for output {idx} (job_id={completed.id})")
        # Save the rendered bytes locally for inspection.
        rendered_bytes = httpx.get(output.primary_url, follow_redirects=True, timeout=60).content
        if not rendered_bytes:
            raise RuntimeError(f"Empty rendered image bytes for output {idx} (job_id={completed.id})")
        out_path = out_dir / f"swipe_demo_{completed.id}_{idx}.png"
        out_path.write_bytes(rendered_bytes)
        sys.stdout.write(f"\nWrote: {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
