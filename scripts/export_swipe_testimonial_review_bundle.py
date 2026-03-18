#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "mos" / "backend"


def _load_backend_env() -> None:
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".env.local.consolidated", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def _ensure_backend_imports() -> None:
    _load_backend_env()
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{field_name} must be an object.")
    return value


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be an array.")
    return value


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _clear_review_bundle(run_dir: Path) -> None:
    for name in ("source-images", "generated-images", "review-data"):
        target = run_dir / name
        if target.exists():
            shutil.rmtree(target)
    for name in ("index.html", "index.json"):
        target = run_dir / name
        if target.exists():
            target.unlink()


def _copy_source_image(*, source_path: Path, template_root: Path, destination_root: Path) -> Path:
    relative_path = source_path.relative_to(template_root)
    destination = destination_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    return destination


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip("-")
    if normalized:
        return normalized
    raise RuntimeError(f"Unable to derive a filesystem-safe slug from value: {value!r}")


def _relative_href(*, path: Path, base_dir: Path) -> str:
    return path.resolve().relative_to(base_dir.resolve()).as_posix()


def _guess_suffix(*, content_type: str | None, storage_key: str | None) -> str:
    guessed = mimetypes.guess_extension(content_type or "") if content_type else None
    if guessed == ".jpe":
        return ".jpg"
    if guessed:
        return guessed
    if storage_key:
        storage_suffix = Path(storage_key).suffix
        if storage_suffix:
            return storage_suffix
    return ".bin"


def _load_asset_records(asset_ids: list[str]) -> dict[str, dict[str, Any]]:
    _ensure_backend_imports()

    from app.db.base import session_scope
    from app.db.models import Asset
    from app.services.media_storage import MediaStorage

    storage = MediaStorage()
    by_id: dict[str, dict[str, Any]] = {}
    with session_scope() as session:
        for asset_id in asset_ids:
            asset = session.get(Asset, asset_id)
            if asset is None:
                raise RuntimeError(f"Generated asset was not found in the database: {asset_id}")
            storage_key = _require_string(asset.storage_key, f"asset[{asset_id}].storage_key")
            if asset.file_status and asset.file_status != "ready":
                raise RuntimeError(
                    f"Generated asset is not ready for download: asset_id={asset_id} file_status={asset.file_status}"
                )
            asset_bytes, content_type = storage.download_bytes(key=storage_key)
            by_id[asset_id] = {
                "assetId": str(asset.id),
                "publicId": str(asset.public_id),
                "storageKey": storage_key,
                "contentType": content_type or _optional_string(asset.content_type),
                "content": dict(asset.content or {}),
                "aiMetadata": dict(asset.ai_metadata or {}),
                "createdAt": asset.created_at.isoformat() if asset.created_at else None,
                "bytes": asset_bytes,
            }
    return by_id


def _render_index_html(*, run_dir: Path, index_payload: dict[str, Any]) -> None:
    run_info = _require_dict(index_payload.get("runInfo"), "index.runInfo")
    results = _require_list(index_payload.get("results"), "index.results")

    cards: list[str] = []
    for raw_item in results:
        item = _require_dict(raw_item, "index.results[]")
        source_href = html.escape(_require_string(item.get("sourceImageHref"), "result.sourceImageHref"))
        output_href = html.escape(_require_string(item.get("generatedImageHref"), "result.generatedImageHref"))
        metadata_href = html.escape(_require_string(item.get("metadataHref"), "result.metadataHref"))
        render_prompt_href = html.escape(_require_string(item.get("renderPromptHref"), "result.renderPromptHref"))
        swipe_markdown_href = html.escape(_require_string(item.get("swipePromptMarkdownHref"), "result.swipePromptMarkdownHref"))
        render_prompt_text = _require_string(item.get("renderPromptText"), "result.renderPromptText")
        stage_one_input_text = _optional_string(item.get("stageOneInputText")) or ""
        swipe_prompt_markdown = _optional_string(item.get("swipePromptMarkdown")) or ""
        slot_pointers = _require_list(item.get("slotPointers"), "result.slotPointers")
        slot_pointer_text = "\n".join(str(entry) for entry in slot_pointers)
        workflow_id = _optional_string(item.get("workflowId")) or "[direct activity]"
        run_id = _optional_string(item.get("runId")) or "[not available]"
        template_url = _optional_string(item.get("templateUrl")) or "[missing]"
        asset_created_at = _optional_string(item.get("assetCreatedAt")) or "[missing]"
        job_id = _optional_string(item.get("jobId")) or "[missing]"
        source_url = _optional_string(item.get("sourceUrl")) or "[missing]"
        prompt_model = _optional_string(item.get("promptModel")) or "[missing]"
        render_provider = _optional_string(item.get("renderProvider")) or "[missing]"
        render_model_id = _optional_string(item.get("renderModelId")) or "[missing]"

        details_html = []
        if stage_one_input_text:
            details_html.extend(
                [
                    '  <div class="text-block nested">',
                    "    <h3>Stage One Input Prompt</h3>",
                    f"    <pre>{html.escape(stage_one_input_text)}</pre>",
                    "  </div>",
                ]
            )
        if swipe_prompt_markdown:
            details_html.extend(
                [
                    '  <div class="text-block nested">',
                    "    <h3>Swipe Prompt Markdown</h3>",
                    f"    <pre>{html.escape(swipe_prompt_markdown)}</pre>",
                    "  </div>",
                ]
            )

        cards.append(
            "\n".join(
                [
                    '<section class="card">',
                    '  <div class="card-header">',
                    f'    <div><h2>{html.escape(_require_string(item.get("jobName"), "result.jobName"))}</h2><p class="subhead">{html.escape(_require_string(item.get("templateFile"), "result.templateFile"))}</p></div>',
                    f'    <div class="pill">{html.escape(_require_string(item.get("assetPublicId"), "result.assetPublicId"))}</div>',
                    "  </div>",
                    '  <div class="meta-line">',
                    f'    <span>Asset ID: <b>{html.escape(_require_string(item.get("assetId"), "result.assetId"))}</b></span>',
                    f'    <span>Workflow: <b>{html.escape(workflow_id)}</b></span>',
                    f'    <span>Render provider: <b>{html.escape(render_provider)}</b></span>',
                    f'    <span>Render model: <b>{html.escape(render_model_id)}</b></span>',
                    "  </div>",
                    '  <div class="grid">',
                    '    <div class="panel">',
                    "      <h3>Source</h3>",
                    f'      <a href="{source_href}" target="_blank" rel="noopener noreferrer"><img src="{source_href}" alt="Source image" loading="lazy" /></a>',
                    f'      <div class="path">{html.escape(_require_string(item.get("sourceImagePath"), "result.sourceImagePath"))}</div>',
                    "    </div>",
                    '    <div class="panel">',
                    "      <h3>Render Prompt</h3>",
                    f"      <pre>{html.escape(render_prompt_text)}</pre>",
                    '      <div class="links">',
                    f'        <a href="{render_prompt_href}" target="_blank" rel="noopener noreferrer">render prompt file</a>',
                    f'        <a href="{swipe_markdown_href}" target="_blank" rel="noopener noreferrer">swipe markdown</a>',
                    f'        <a href="{metadata_href}" target="_blank" rel="noopener noreferrer">metadata</a>',
                    "      </div>",
                    "    </div>",
                    '    <div class="panel">',
                    "      <h3>Generated</h3>",
                    f'      <a href="{output_href}" target="_blank" rel="noopener noreferrer"><img src="{output_href}" alt="Generated image" loading="lazy" /></a>',
                    f'      <div class="path">{html.escape(_require_string(item.get("generatedImagePath"), "result.generatedImagePath"))}</div>',
                    "    </div>",
                    "  </div>",
                    '  <details class="details-block">',
                    "    <summary>Trace Details</summary>",
                    '    <div class="details-grid">',
                    f'      <div><b>Template URL</b><br/>{html.escape(template_url)}</div>',
                    f'      <div><b>Created At</b><br/>{html.escape(asset_created_at)}</div>',
                    f'      <div><b>Job ID</b><br/>{html.escape(job_id)}</div>',
                    f'      <div><b>Run ID</b><br/>{html.escape(run_id)}</div>',
                    f'      <div><b>Source URL</b><br/>{html.escape(source_url)}</div>',
                    f'      <div><b>Prompt Model</b><br/>{html.escape(prompt_model)}</div>',
                    f'      <div><b>Slot Pointers</b><br/><pre>{html.escape(slot_pointer_text)}</pre></div>',
                    "    </div>",
                    *details_html,
                    "  </details>",
                    "</section>",
                ]
            )
        )

    saved_draft_version_id = _optional_string(run_info.get("savedDraftVersionId")) or "[not saved]"

    document = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Swipe Testimonial Review</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f4efe6; --panel: #fffdf8; --line: #ded4c5; --ink: #1e1a15; --muted: #6d6358; --accent: #a1551e; }",
            "    * { box-sizing: border-box; }",
            "    body { margin: 0; font: 14px/1.55 Arial, sans-serif; background: radial-gradient(circle at top, #fff9ef 0%, var(--bg) 56%, #ece2d2 100%); color: var(--ink); }",
            "    main { max-width: 1600px; margin: 0 auto; padding: 28px 24px 72px; }",
            "    h1, h2, h3, p { margin: 0; }",
            "    a { color: var(--accent); }",
            "    .hero { background: rgba(255, 253, 248, 0.92); border: 1px solid var(--line); border-radius: 18px; padding: 24px; }",
            "    .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 18px; }",
            "    .tile { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; min-height: 90px; }",
            "    .cards { display: grid; gap: 22px; margin-top: 24px; }",
            "    .card { background: rgba(255, 253, 248, 0.96); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 10px 28px rgba(76, 51, 22, 0.08); }",
            "    .card-header { display: flex; justify-content: space-between; align-items: start; gap: 16px; margin-bottom: 10px; }",
            "    .card-header h2 { font-size: 22px; }",
            "    .subhead { margin-top: 4px; color: var(--muted); word-break: break-word; }",
            "    .pill { border: 1px solid var(--accent); border-radius: 999px; padding: 6px 10px; color: var(--accent); font: 12px/1.2 Arial, sans-serif; }",
            "    .meta-line { display: flex; flex-wrap: wrap; gap: 16px; color: var(--muted); margin-bottom: 16px; }",
            "    .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 1fr); gap: 16px; }",
            "    .panel { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px; min-width: 0; }",
            "    .panel h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 10px; }",
            "    img { display: block; width: 100%; max-height: 520px; object-fit: contain; background: #f7f2ea; border-radius: 10px; }",
            "    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 'SFMono-Regular', Menlo, Consolas, monospace; }",
            "    .path { margin-top: 10px; color: var(--muted); font: 12px/1.45 Arial, sans-serif; word-break: break-all; }",
            "    .links { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; font-size: 12px; }",
            "    .details-block { margin-top: 16px; background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px; }",
            "    .details-block summary { cursor: pointer; color: var(--accent); }",
            "    .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 14px; }",
            "    .text-block { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px; }",
            "    .text-block h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 10px; }",
            "    .nested { margin-top: 14px; }",
            "    @media (max-width: 1200px) { .grid { grid-template-columns: 1fr; } }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="hero">',
            "    <h1>Swipe Testimonial Review</h1>",
            f'    <p style="margin-top: 8px; color: var(--muted);">Run dir: {html.escape(str(run_dir))}</p>',
            '    <div class="summary">',
            f'      <div class="tile"><b>Started</b><br/>{html.escape(_require_string(run_info.get("startedAt"), "runInfo.startedAt"))}</div>',
            f'      <div class="tile"><b>Finished</b><br/>{html.escape(_require_string(run_info.get("finishedAt"), "runInfo.finishedAt"))}</div>',
            f'      <div class="tile"><b>Jobs</b><br/>{len(results)}</div>',
            f'      <div class="tile"><b>Saved Draft</b><br/>{html.escape(saved_draft_version_id)}</div>',
            f'      <div class="tile"><b>Page</b><br/>{html.escape(_require_string(run_info.get("pageId"), "runInfo.pageId"))}</div>',
            f'      <div class="tile"><b>Brief</b><br/>{html.escape(_require_string(run_info.get("assetBriefId"), "runInfo.assetBriefId"))}</div>',
            "    </div>",
            "  </section>",
            '  <section class="cards">',
            *cards,
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    _write_text(run_dir / "index.html", document)


def _build_bundle(*, run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    summary = _require_dict(_load_json(summary_path), "summary")
    template_dir = Path(_require_string(summary.get("templateDir"), "summary.templateDir")).expanduser().resolve()
    if not template_dir.is_dir():
        raise RuntimeError(f"summary.templateDir does not exist: {template_dir}")

    jobs = _require_list(summary.get("jobs"), "summary.jobs")
    asset_ids = [
        _require_string(
            _require_dict(_require_dict(job, "summary.jobs[]").get("asset"), "summary.jobs[].asset").get("assetId"),
            "summary.jobs[].asset.assetId",
        )
        for job in jobs
    ]
    assets_by_id = _load_asset_records(asset_ids)

    source_root = run_dir / "source-images"
    generated_root = run_dir / "generated-images"
    review_data_root = run_dir / "review-data"
    source_root.mkdir(parents=True, exist_ok=True)
    generated_root.mkdir(parents=True, exist_ok=True)
    review_data_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, raw_job in enumerate(jobs, start=1):
        job = _require_dict(raw_job, "summary.jobs[]")
        job_name = _require_string(job.get("name"), "summary.jobs[].name")
        template_file = _require_string(job.get("templateFile"), "summary.jobs[].templateFile")
        template_path = (template_dir / template_file).resolve()
        if not template_path.is_file():
            raise RuntimeError(f"Template image does not exist for job {job_name}: {template_path}")

        asset_ref = _require_dict(job.get("asset"), f"summary.jobs[{job_name}].asset")
        asset_id = _require_string(asset_ref.get("assetId"), f"summary.jobs[{job_name}].asset.assetId")
        asset_record = _require_dict(assets_by_id.get(asset_id), f"asset record {asset_id}")
        ai_metadata = _require_dict(asset_record.get("aiMetadata"), f"asset[{asset_id}].aiMetadata")
        content = _require_dict(asset_record.get("content"), f"asset[{asset_id}].content")

        render_prompt_text = _require_string(ai_metadata.get("promptUsed"), f"asset[{asset_id}].aiMetadata.promptUsed")
        prompt_model = _require_string(ai_metadata.get("swipePromptModel"), f"asset[{asset_id}].aiMetadata.swipePromptModel")
        render_provider = _require_string(
            ai_metadata.get("swipeRenderProvider"),
            f"asset[{asset_id}].aiMetadata.swipeRenderProvider",
        )
        render_model_id = _require_string(
            ai_metadata.get("swipeRenderModelIdUsed"),
            f"asset[{asset_id}].aiMetadata.swipeRenderModelIdUsed",
        )
        source_url = _require_string(ai_metadata.get("swipeSourceUrl"), f"asset[{asset_id}].aiMetadata.swipeSourceUrl")
        template_url = _optional_string(job.get("templateUrl"))

        slug = _slug(f"{index:02d}-{job_name}")
        source_copy_path = _copy_source_image(
            source_path=template_path,
            template_root=template_dir,
            destination_root=source_root,
        )
        generated_suffix = _guess_suffix(
            content_type=_optional_string(asset_record.get("contentType")),
            storage_key=_optional_string(asset_record.get("storageKey")),
        )
        generated_path = generated_root / f"{slug}{generated_suffix}"
        generated_path.write_bytes(asset_record["bytes"])

        render_prompt_path = review_data_root / f"{slug}.render-prompt.txt"
        swipe_markdown_path = review_data_root / f"{slug}.swipe-prompt-markdown.md"
        metadata_path = review_data_root / f"{slug}.json"
        _write_text(render_prompt_path, render_prompt_text)
        _write_text(swipe_markdown_path, _optional_string(ai_metadata.get("swipePromptMarkdown")) or "")

        item = {
            "jobName": job_name,
            "templateFile": template_file,
            "templateUrl": template_url,
            "workflowId": _optional_string(job.get("workflowId")),
            "runId": _optional_string(job.get("runId")),
            "jobId": _optional_string(job.get("jobId")),
            "slotPointers": _require_list(job.get("slotPointers"), f"summary.jobs[{job_name}].slotPointers"),
            "assetId": asset_id,
            "assetPublicId": _require_string(asset_ref.get("publicId"), f"summary.jobs[{job_name}].asset.publicId"),
            "assetCreatedAt": _optional_string(asset_record.get("createdAt")),
            "sourceUrl": source_url,
            "sourceImagePath": str(source_copy_path),
            "sourceImageHref": _relative_href(path=source_copy_path, base_dir=run_dir),
            "generatedImagePath": str(generated_path),
            "generatedImageHref": _relative_href(path=generated_path, base_dir=run_dir),
            "renderPromptText": render_prompt_text,
            "renderPromptHref": _relative_href(path=render_prompt_path, base_dir=run_dir),
            "swipePromptMarkdown": _optional_string(ai_metadata.get("swipePromptMarkdown")),
            "swipePromptMarkdownHref": _relative_href(path=swipe_markdown_path, base_dir=run_dir),
            "stageOneInputText": _optional_string(ai_metadata.get("swipePromptInputText")),
            "promptModel": prompt_model,
            "renderProvider": render_provider,
            "renderModelId": render_model_id,
            "contentSourceUrl": _optional_string(content.get("sourceUrl")),
        }
        metadata_payload = {
            **item,
            "swipePromptExtractedRaw": _optional_string(ai_metadata.get("swipePromptExtractedRaw")),
            "generatedAssetContent": content,
            "generatedAssetAiMetadata": ai_metadata,
        }
        _write_json(metadata_path, metadata_payload)
        item["metadataHref"] = _relative_href(path=metadata_path, base_dir=run_dir)
        results.append(item)

    saved_draft = summary.get("savedDraft")
    saved_draft_version_id: str | None = None
    if saved_draft is not None:
        saved_draft_version_id = _optional_string(
            _require_dict(saved_draft, "summary.savedDraft").get("id")
        )

    return {
        "runInfo": {
            "runDir": str(run_dir),
            "templateDir": str(template_dir),
            "startedAt": _require_string(summary.get("startedAt"), "summary.startedAt"),
            "finishedAt": _require_string(summary.get("finishedAt"), "summary.finishedAt"),
            "funnelId": _require_string(summary.get("funnelId"), "summary.funnelId"),
            "pageId": _require_string(summary.get("pageId"), "summary.pageId"),
            "assetBriefId": _require_string(summary.get("assetBriefId"), "summary.assetBriefId"),
            "savedDraftVersionId": saved_draft_version_id,
        },
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize a completed swipe testimonial run into a local review bundle with copied "
            "source images, downloaded generated images, and an index.html."
        )
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to a completed swipe testimonial run directory that contains summary.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        raise RuntimeError(f"Run directory does not exist: {run_dir}")

    _clear_review_bundle(run_dir)
    index_payload = _build_bundle(run_dir=run_dir)
    _write_json(run_dir / "index.json", index_payload)
    _render_index_html(run_dir=run_dir, index_payload=index_payload)
    print(
        json.dumps(
            {
                "runDir": str(run_dir),
                "indexPath": str(run_dir / "index.html"),
                "generatedImagesDir": str(run_dir / "generated-images"),
                "sourceImagesDir": str(run_dir / "source-images"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
