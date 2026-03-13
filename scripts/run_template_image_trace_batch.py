#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from swipe_testimonial_workflow import (
    _JsonApiClient,
    _StaticServer,
    _assets_by_id,
    _collect_template_files,
    _extract_completed_swipe_result,
    _start_swipe_generation,
    _swipe_generation_request_payload,
    _token_from_env,
    _wait_for_swipe_generation,
)


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "mos" / "backend"
DEFAULT_TEMPLATE_DIR = ROOT / "template-images"
REQUIRED_PROVIDER = "creative_service"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _load_backend_env() -> None:
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".env.local.consolidated", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def _resolve_render_provider(*, render_model_id: str | None) -> tuple[str, str | None]:
    _load_backend_env()
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from app.config import settings
    from app.services.image_render_client import get_image_render_provider

    provider = get_image_render_provider(model_id=render_model_id)
    effective_model = (
        render_model_id
        or os.getenv("SWIPE_IMAGE_RENDER_MODEL")
        or os.getenv("IMAGE_RENDER_MODEL")
        or settings.SWIPE_IMAGE_RENDER_MODEL
        or None
    )
    cleaned_model = (
        str(effective_model).strip() if isinstance(effective_model, str) and effective_model.strip() else None
    )
    return provider, cleaned_model


def _require_creative_service_provider(*, render_model_id: str | None) -> None:
    provider, effective_model = _resolve_render_provider(render_model_id=render_model_id)
    if provider == REQUIRED_PROVIDER:
        return

    model_note = (
        f" effective_render_model={effective_model!r}."
        if effective_model is not None
        else " effective_render_model=None."
    )
    requested_note = (
        f" requested_render_model_id={render_model_id!r}."
        if render_model_id is not None
        else ""
    )
    raise RuntimeError(
        "Template image trace batch requires the stage-two render provider to resolve to "
        f"{REQUIRED_PROVIDER!r}, but got {provider!r}."
        f"{requested_note}{model_note} "
        "Pass a Gemini image render model via --render-model-id or update the backend render env "
        "so the existing swipe batch resolves to the embedded creative_service provider."
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _clear_output_root(output_root: Path) -> None:
    for name in ("generated-images", "source-images", "succeeded", "failed"):
        target = output_root / name
        if target.exists():
            for child in target.rglob("*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(target.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            target.rmdir()
    for name in ("manifest.json", "index.json"):
        target = output_root / name
        if target.exists():
            target.unlink()


def _infer_output_suffix(*, asset_row: dict[str, object]) -> str:
    content_type = str(asset_row.get("content_type") or "").strip()
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        return guessed
    return ".bin"


def _download_asset_to_path(
    *,
    client: _JsonApiClient,
    asset_id: str,
    destination: Path,
) -> None:
    url = f"{client.base_url}/assets/{urllib.parse.quote(asset_id, safe='')}/download"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "*/*",
            "Authorization": f"Bearer {client.auth_token}",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _copy_source_image(*, source_path: Path, source_root: Path, destination_root: Path) -> Path:
    relative_path = source_path.relative_to(source_root)
    destination = destination_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    return destination


def _relative_href(*, target_path: Path, base_dir: Path) -> str:
    return target_path.resolve().relative_to(base_dir.resolve()).as_posix()


def _render_index_html(*, output_root: Path, index_payload: dict[str, object]) -> None:
    results = index_payload.get("results")
    rows = results if isinstance(results, list) else []
    cards: list[str] = []
    for raw_item in rows:
        if not isinstance(raw_item, dict):
            continue
        status = str(raw_item.get("status") or "").strip()
        source_href = str(raw_item.get("sourceImageTrackingHref") or "").strip()
        output_href = str(raw_item.get("finalImageHref") or "").strip()
        prompt_text = str(raw_item.get("stageOneOutputPromptText") or "").strip()
        source_file = str(raw_item.get("sourceFile") or "").strip()
        error_text = str(raw_item.get("error") or "").strip()

        prompt_html = (
            f"<pre>{html.escape(prompt_text)}</pre>"
            if prompt_text
            else "<div class=\"empty\">No extracted Gemini prompt was recorded.</div>"
        )
        source_image_html = (
            f"<img src=\"{html.escape(source_href)}\" alt=\"Source image for {html.escape(source_file)}\" />"
            if source_href
            else "<div class=\"empty\">Source image unavailable.</div>"
        )
        output_image_html = (
            f"<img src=\"{html.escape(output_href)}\" alt=\"Output image for {html.escape(source_file)}\" />"
            if output_href and status == "succeeded"
            else "<div class=\"empty\">Output image unavailable.</div>"
        )
        status_html = (
            f"<div class=\"status status-failed\">Failed: {html.escape(error_text or 'Unknown error')}</div>"
            if status == "failed"
            else "<div class=\"status status-succeeded\">Succeeded</div>"
        )
        cards.append(
            "\n".join(
                [
                    "<section class=\"card\">",
                    f"  <div class=\"card-header\"><h2>{html.escape(source_file or 'Unnamed source')}</h2>{status_html}</div>",
                    "  <div class=\"grid\">",
                    "    <div class=\"panel\">",
                    "      <h3>Source Image</h3>",
                    f"      {source_image_html}",
                    "    </div>",
                    "    <div class=\"panel\">",
                    "      <h3>Gemini Prompt</h3>",
                    f"      {prompt_html}",
                    "    </div>",
                    "    <div class=\"panel\">",
                    "      <h3>Output Image</h3>",
                    f"      {output_image_html}",
                    "    </div>",
                    "  </div>",
                    "</section>",
                ]
            )
        )

    run_info = index_payload.get("runInfo")
    run_info_obj = run_info if isinstance(run_info, dict) else {}
    summary = (
        f"Template dir: {html.escape(str(run_info_obj.get('templateDir') or ''))} | "
        f"Successes: {html.escape(str(run_info_obj.get('successCount') or 0))} | "
        f"Failures: {html.escape(str(run_info_obj.get('failureCount') or 0))}"
    )

    document = "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "<head>",
            "  <meta charset=\"utf-8\" />",
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
            "  <title>Template Image Trace Batch</title>",
            "  <style>",
            "    :root { color-scheme: light; }",
            "    body { margin: 0; font: 14px/1.5 Arial, sans-serif; background: #f4f1ea; color: #1f1b16; }",
            "    main { max-width: 1400px; margin: 0 auto; padding: 24px; }",
            "    h1 { margin: 0 0 8px; font-size: 28px; }",
            "    .summary { margin: 0 0 24px; color: #4d463d; }",
            "    .card { background: #fffdf8; border: 1px solid #ddd3c2; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 24px rgba(52, 41, 27, 0.06); }",
            "    .card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }",
            "    .card-header h2 { margin: 0; font-size: 18px; word-break: break-word; }",
            "    .status { padding: 6px 10px; border-radius: 999px; font-weight: 700; font-size: 12px; }",
            "    .status-succeeded { background: #dff4e4; color: #1e6a32; }",
            "    .status-failed { background: #f8dfdf; color: #8a2222; }",
            "    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }",
            "    .panel { background: #fff; border: 1px solid #e7dfd0; border-radius: 12px; padding: 14px; }",
            "    .panel h3 { margin: 0 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: #6b6155; }",
            "    img { display: block; width: 100%; max-height: 480px; object-fit: contain; background: #f7f3ec; border-radius: 8px; }",
            "    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 'SFMono-Regular', Consolas, monospace; }",
            "    .empty { color: #7a7063; font-style: italic; min-height: 32px; display: flex; align-items: center; }",
            "    @media (max-width: 1080px) { .grid { grid-template-columns: 1fr; } }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            "    <h1>Template Image Trace Batch</h1>",
            f"    <p class=\"summary\">{summary}</p>",
            *cards,
            "  </main>",
            "</body>",
            "</html>",
        ]
    )
    _write_text(output_root / "index.html", document)


def _normalize_generation_payload(args: argparse.Namespace) -> dict[str, str | int]:
    payload: dict[str, str | int] = {
        "clientId": args.client_id,
        "productId": args.product_id,
        "campaignId": args.campaign_id,
        "assetBriefId": args.asset_brief_id,
        "requirementIndex": args.requirement_index,
        "aspectRatio": args.aspect_ratio,
        "count": 1,
    }
    if args.model:
        payload["model"] = args.model
    if args.render_model_id:
        payload["renderModelId"] = args.render_model_id
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the repo template-images directory through the existing swipe image creation workflow, "
            "while requiring the mOS embedded creative_service render provider."
        )
    )
    parser.add_argument("--mos-base-url", required=True)
    parser.add_argument("--auth-token-env", required=True)
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--asset-brief-id", required=True)
    parser.add_argument("--requirement-index", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--render-model-id", default=None)
    return parser.parse_args()


def _run_batch(args: argparse.Namespace) -> int:
    template_dir = Path(args.template_dir).expanduser().resolve()
    if not template_dir.is_dir():
        raise RuntimeError(f"Template directory does not exist: {template_dir}")

    output_root = Path(args.output_root).expanduser().resolve()
    if args.clean:
        _clear_output_root(output_root)

    generated_dir = output_root / "generated-images"
    source_dir = output_root / "source-images"
    succeeded_dir = output_root / "succeeded"
    failed_dir = output_root / "failed"
    generated_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    succeeded_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    mos_host = urllib.parse.urlparse(args.mos_base_url).hostname or ""
    if mos_host not in _LOCAL_HOSTS:
        raise RuntimeError(
            "Template image trace batch requires a local mosBaseUrl so the creative_service provider "
            "check matches the backend env used by the swipe workflow."
        )

    _require_creative_service_provider(render_model_id=args.render_model_id)

    auth_token = _token_from_env(args.auth_token_env)
    client = _JsonApiClient(base_url=args.mos_base_url, auth_token=auth_token)
    template_files = _collect_template_files(template_dir)
    generation_defaults = _normalize_generation_payload(args)

    results: list[dict[str, object]] = []
    failure_manifest: list[dict[str, str]] = []

    with _StaticServer(root=template_dir, host=args.host, port=args.port) as static_server:
        source_base_url = static_server.base_url
        for template_member in template_files:
            template_path = template_dir / template_member
            source_url = f"{source_base_url}/{urllib.parse.quote(template_member)}"
            item_base = {
                "sourceFile": template_member,
                "sourceImagePath": str(template_path),
                "sourceImageUrl": source_url,
            }
            try:
                payload = _swipe_generation_request_payload(generation_defaults, source_url)
                workflow_ref = _start_swipe_generation(client, payload=payload)
                workflow_response = _wait_for_swipe_generation(
                    client,
                    workflow_run_id=workflow_ref["workflowRunId"],
                )
                swipe_result = _extract_completed_swipe_result(workflow_response)
                asset_id = swipe_result["assetId"]
                asset_row = _assets_by_id(
                    client,
                    campaign_id=args.campaign_id,
                    product_id=args.product_id,
                    required_asset_ids={asset_id},
                )[asset_id]
                public_id = str(asset_row.get("public_id") or "").strip()
                if not public_id:
                    raise RuntimeError(f"Generated asset {asset_id} is missing public_id.")

                source_copy_path = _copy_source_image(
                    source_path=template_path,
                    source_root=template_dir,
                    destination_root=source_dir,
                )
                output_suffix = _infer_output_suffix(asset_row=asset_row)
                output_path = generated_dir / f"{Path(template_member).name}{output_suffix}"
                _download_asset_to_path(client=client, asset_id=asset_id, destination=output_path)

                raw_ai_metadata = asset_row.get("ai_metadata")
                ai_metadata = raw_ai_metadata if isinstance(raw_ai_metadata, dict) else {}
                raw_markdown = str(ai_metadata.get("swipePromptMarkdown") or "")
                output_prompt = str(ai_metadata.get("swipePromptExtractedRaw") or "")
                raw_markdown_path = succeeded_dir / f"{Path(template_member).name}.swipe-prompt-markdown.md"
                output_prompt_path = succeeded_dir / f"{Path(template_member).name}.image-prompt.txt"
                metadata_path = succeeded_dir / f"{Path(template_member).name}.json"
                _write_text(raw_markdown_path, raw_markdown)
                _write_text(output_prompt_path, output_prompt)

                item = {
                    **item_base,
                    "status": "succeeded",
                    "workflowRunId": workflow_ref["workflowRunId"],
                    "temporalWorkflowId": workflow_ref["temporalWorkflowId"],
                    "jobId": swipe_result["jobId"],
                    "assetId": asset_id,
                    "assetPublicId": public_id,
                    "sourceImageTrackingPath": str(source_copy_path),
                    "sourceImageTrackingHref": _relative_href(
                        target_path=source_copy_path,
                        base_dir=output_root,
                    ),
                    "finalImagePath": str(output_path),
                    "finalImageHref": _relative_href(target_path=output_path, base_dir=output_root),
                    "assetCreatedAt": asset_row.get("created_at"),
                    "finalImageWidth": asset_row.get("width"),
                    "finalImageHeight": asset_row.get("height"),
                    "finalImageContentType": asset_row.get("content_type"),
                    "stageOnePromptModel": ai_metadata.get("swipePromptModel"),
                    "stageTwoRenderModelId": ai_metadata.get("swipeRenderModelIdUsed"),
                    "stageTwoRenderProvider": ai_metadata.get("swipeRenderProvider"),
                    "stageOneOutputPromptText": output_prompt,
                    "stageOneRawMarkdownPath": str(raw_markdown_path),
                    "stageOneOutputPromptPath": str(output_prompt_path),
                    "metadataPath": str(metadata_path),
                }
                _write_json(metadata_path, item)
                results.append(item)
            except Exception as exc:  # noqa: BLE001
                diagnostic_path = failed_dir / f"{Path(template_member).name}.diagnostic.json"
                failure = {
                    **item_base,
                    "status": "failed",
                    "error": str(exc),
                    "diagnosticPath": str(diagnostic_path),
                }
                _write_json(diagnostic_path, failure)
                results.append(failure)
                failure_manifest.append(
                    {
                        "sourceFile": template_member,
                        "diagnosticPath": str(diagnostic_path),
                        "error": str(exc),
                    }
                )

    index_payload = {
        "runInfo": {
            "templateDir": str(template_dir),
            "outputRoot": str(output_root),
            "mosBaseUrl": args.mos_base_url,
            "clientId": args.client_id,
            "productId": args.product_id,
            "campaignId": args.campaign_id,
            "assetBriefId": args.asset_brief_id,
            "requirementIndex": args.requirement_index,
            "aspectRatio": args.aspect_ratio,
            "renderModelId": args.render_model_id,
            "successCount": len([item for item in results if item["status"] == "succeeded"]),
            "failureCount": len([item for item in results if item["status"] == "failed"]),
        },
        "results": results,
    }
    _write_json(
        output_root / "manifest.json",
        {
            "outputRoot": str(output_root),
            "templateDir": str(template_dir),
            "remainingFailedFiles": failure_manifest,
        },
    )
    _write_json(output_root / "index.json", index_payload)
    _render_index_html(output_root=output_root, index_payload=index_payload)
    return 0


def main() -> int:
    args = _parse_args()
    return _run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
