#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import html
import http.server
import json
import os
import shutil
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "mos" / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import session_scope
from app.db.models import Asset
from app.db.repositories.artifacts import ArtifactsRepository
from app.services.swipe_prompt import load_swipe_to_image_ad_prompt
from app.temporal.activities import swipe_image_ad_activities as swipe_activities
from app.temporal.activities.asset_activities import _extract_brief, _validate_brief_scope
from app.temporal.activities.swipe_image_ad_activities import (
    _build_swipe_stage1_prompt_input,
    _extract_brand_context,
    generate_swipe_image_ad_activity,
)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _clear_output_root(output_root: Path) -> None:
    for name in ("generated-images", "succeeded", "failed"):
        target = output_root / name
        if target.exists():
            shutil.rmtree(target)
    for name in ("manifest.json", "index.json", "index.html", "stage-one-input-prompt.txt"):
        target = output_root / name
        if target.exists():
            target.unlink()


def _download_to_path(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def _infer_output_suffix(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix
    return suffix if suffix else ".bin"


def _load_asset(asset_id: str) -> dict[str, Any]:
    with session_scope() as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            raise RuntimeError(f"Generated asset was not found in the database: {asset_id}")
        return {
            "id": str(asset.id),
            "publicId": str(asset.public_id),
            "content": dict(asset.content or {}),
            "aiMetadata": dict(asset.ai_metadata or {}),
            "width": asset.width,
            "height": asset.height,
            "contentType": asset.content_type,
            "createdAt": asset.created_at.isoformat() if asset.created_at else None,
            "assetBriefArtifactId": str(asset.asset_brief_artifact_id) if asset.asset_brief_artifact_id else None,
        }


def _resolve_shared_prompt_input(
    *,
    org_id: str,
    client_id: str,
    campaign_id: str,
    product_id: str,
    asset_brief_id: str,
    requirement_index: int,
) -> dict[str, Any]:
    prompt_template, prompt_sha = load_swipe_to_image_ad_prompt()
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        brief, brief_artifact_id = _extract_brief(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
        )
        _validate_brief_scope(
            session=session,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
            brief=brief,
        )
        brand_ctx = _extract_brand_context(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )

    requirements = brief.get("requirements") or []
    if not isinstance(requirements, list) or requirement_index < 0 or requirement_index >= len(requirements):
        raise RuntimeError(
            f"requirement_index={requirement_index} is out of range for asset brief {asset_brief_id}."
        )
    requirement = requirements[requirement_index]
    if not isinstance(requirement, dict):
        raise RuntimeError("Asset brief requirement must be an object.")
    angle = requirement.get("angle") if isinstance(requirement.get("angle"), str) else None
    brand_name = str(brand_ctx.get("client_name") or "")
    prompt_input = _build_swipe_stage1_prompt_input(
        prompt_template=prompt_template,
        brand_name=brand_name,
        angle=angle,
    )
    return {
        "promptTemplateSha256": prompt_sha,
        "promptInputText": prompt_input,
        "brandName": brand_name,
        "angle": angle,
        "briefArtifactId": brief_artifact_id,
        "briefRequirement": requirement,
        "briefCreativeConcept": brief.get("creativeConcept"),
        "briefVariantName": brief.get("variantName"),
    }


def _run_stage1_trace(
    *,
    org_id: str,
    client_id: str,
    campaign_id: str,
    product_id: str,
    asset_brief_id: str,
    requirement_index: int,
    source_url: str,
    prompt_input_text: str,
    requested_model: str | None,
    requested_render_model_id: str | None,
) -> dict[str, Any]:
    model = (
        requested_model
        or swipe_activities.os.getenv("SWIPE_PROMPT_MODEL")
        or swipe_activities.os.getenv("GEMINI_FILE_SEARCH_MODEL")
        or swipe_activities.settings.GEMINI_FILE_SEARCH_MODEL
    )
    model_name = swipe_activities._normalize_gemini_model_name(str(model or ""))
    if swipe_activities._is_image_render_model_name(model_name):
        raise RuntimeError(
            "model is configured as an image rendering model; stage one requires a Gemini text model with File Search."
        )

    render_model_id: str | None = None
    render_model_raw = requested_render_model_id or swipe_activities.os.getenv("SWIPE_IMAGE_RENDER_MODEL")
    if render_model_raw:
        render_model_id = swipe_activities._normalize_render_model_id(render_model_raw)
    render_provider = swipe_activities.get_image_render_provider(model_id=render_model_id)
    max_output_tokens = int(
        swipe_activities.os.getenv("SWIPE_PROMPT_MAX_OUTPUT_TOKENS") or "6000"
    )

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        brief, brief_artifact_id = _extract_brief(
            artifacts_repo=artifacts_repo,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
        )
        funnel_id = _validate_brief_scope(
            session=session,
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            asset_brief_id=asset_brief_id,
            brief=brief,
        )
        requirements_raw = brief.get("requirements") or []
        if not isinstance(requirements_raw, list) or requirement_index < 0 or requirement_index >= len(requirements_raw):
            raise RuntimeError(
                f"requirement_index={requirement_index} is out of range for asset brief {asset_brief_id}."
            )
        requirement = requirements_raw[requirement_index]
        if not isinstance(requirement, dict):
            raise RuntimeError("Asset brief requirement must be an object.")

        swipe_bytes, swipe_mime_type, swipe_source_url = swipe_activities._resolve_swipe_image(
            session=session,
            org_id=org_id,
            company_swipe_id=None,
            swipe_image_url=source_url,
        )
        resolved_requires_product_image, policy_source, source_filename = (
            swipe_activities._resolve_swipe_requires_product_image_policy(
                explicit_requires_product_image=None,
                swipe_source_url=swipe_source_url,
            )
        )

        if resolved_requires_product_image is False:
            product_reference_assets = []
        elif resolved_requires_product_image is True:
            product_reference_assets = swipe_activities._select_product_reference_assets(
                session=session,
                org_id=org_id,
                product_id=product_id,
            )
        else:
            try:
                product_reference_assets = swipe_activities._select_product_reference_assets(
                    session=session,
                    org_id=org_id,
                    product_id=product_id,
                )
            except ValueError as exc:
                if "No active source product images are available" in str(exc):
                    product_reference_assets = []
                else:
                    raise

        all_product_reference_image_urls = [
            reference.primary_url
            for reference in product_reference_assets
            if isinstance(reference.primary_url, str) and reference.primary_url.strip()
        ]
        product_reference_image_urls = (
            all_product_reference_image_urls[:1]
            if render_provider == "higgsfield"
            else all_product_reference_image_urls
        )

        product_prompt_image_bytes: bytes | None = None
        product_prompt_image_mime_type: str | None = None
        product_prompt_image_source_url: str | None = None
        if product_reference_image_urls:
            product_prompt_image_source_url = product_reference_image_urls[0]
            product_prompt_image_bytes, product_prompt_image_mime_type = swipe_activities._download_bytes(
                product_prompt_image_source_url,
                max_bytes=int(
                    swipe_activities.os.getenv("SWIPE_IMAGE_MAX_BYTES", str(18 * 1024 * 1024))
                ),
                timeout_seconds=float(
                    swipe_activities.os.getenv("SWIPE_IMAGE_DOWNLOAD_TIMEOUT", "30")
                ),
            )

        (
            gemini_store_names,
            gemini_rag_doc_keys,
            gemini_rag_bundle_doc_keys,
            gemini_rag_document_names,
        ) = swipe_activities._resolve_swipe_stage1_gemini_file_search_context(
            session=session,
            org_id=org_id,
            idea_workspace_id=campaign_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            funnel_id=funnel_id,
            asset_brief_artifact_id=brief_artifact_id,
        )

    gemini_client = swipe_activities._ensure_gemini_client()
    contents: list[Any] = [
        prompt_input_text,
        swipe_activities.genai_types.Part.from_bytes(data=swipe_bytes, mime_type=swipe_mime_type),
    ]
    if product_prompt_image_bytes is not None and product_prompt_image_mime_type is not None:
        contents.append(
            swipe_activities.genai_types.Part.from_bytes(
                data=product_prompt_image_bytes,
                mime_type=product_prompt_image_mime_type,
            )
        )

    generate_config = swipe_activities.genai_types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=max_output_tokens,
        tools=[
            swipe_activities.genai_types.Tool(
                file_search=swipe_activities.genai_types.FileSearch(
                    file_search_store_names=gemini_store_names
                )
            )
        ],
    )
    result = gemini_client.models.generate_content(
        model=model_name,
        contents=contents,
        config=generate_config,
    )
    raw_output = swipe_activities._extract_gemini_text(result)
    if not raw_output:
        raise RuntimeError("Gemini returned no text for swipe prompt generation")

    extracted_image_prompt_raw = swipe_activities.extract_new_image_prompt_from_markdown(raw_output)
    image_prompt, inlined_placeholder_map = swipe_activities.inline_swipe_render_placeholders(
        extracted_image_prompt_raw
    )
    return {
        "promptModel": model_name,
        "renderModelId": render_model_id,
        "renderProvider": render_provider,
        "storesAttached": len(gemini_store_names),
        "geminiStoreNames": gemini_store_names,
        "geminiRagDocKeys": gemini_rag_doc_keys,
        "geminiRagBundleDocKeys": gemini_rag_bundle_doc_keys,
        "geminiRagDocumentNames": gemini_rag_document_names,
        "sourceFilename": source_filename,
        "sourceUrl": swipe_source_url,
        "requiresProductImage": resolved_requires_product_image,
        "requiresProductImagePolicySource": policy_source,
        "productReferenceImageUrlsSelected": product_reference_image_urls,
        "productReferenceImageUrlsAvailable": all_product_reference_image_urls,
        "productPromptImageSourceUrl": product_prompt_image_source_url,
        "rawMarkdown": raw_output,
        "outputPromptText": extracted_image_prompt_raw,
        "inlinedOutputPromptText": image_prompt,
        "inlinedPlaceholderMap": inlined_placeholder_map,
    }


def _iter_template_files(template_dir: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    files = [path for path in sorted(template_dir.iterdir()) if path.is_file() and path.suffix.lower() in allowed]
    if not files:
        raise RuntimeError(f"No image files found in template directory: {template_dir}")
    return files


def _html_pre(value: str) -> str:
    return html.escape(value or "")


def _to_relative_href(*, output_root: Path, target: str | None) -> str | None:
    if not target:
        return None
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme in {"http", "https"}:
        return target
    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = (output_root / target_path).resolve()
    rel_path = os.path.relpath(target_path, output_root)
    return urllib.parse.quote(rel_path.replace(os.sep, "/"), safe="/:@")


def _read_optional_text(path_value: str | None) -> str:
    if not path_value:
        return ""
    try:
        return Path(path_value).read_text(encoding="utf-8")
    except OSError:
        return ""


def _render_index_html(*, output_root: Path, index_payload: dict[str, Any]) -> None:
    run_info = index_payload["runInfo"]
    shared_input = index_payload["sharedStageOneInputPrompt"]["text"]
    shared_input_path = index_payload["sharedStageOneInputPrompt"]["path"]

    cards: list[str] = []
    for item in index_payload["results"]:
        source_href = _to_relative_href(output_root=output_root, target=item.get("sourceImagePath"))
        final_href = _to_relative_href(output_root=output_root, target=item.get("finalImagePath"))
        metadata_href = _to_relative_href(output_root=output_root, target=item.get("metadataPath"))
        diagnostic_href = _to_relative_href(output_root=output_root, target=item.get("diagnosticPath"))
        raw_markdown_href = _to_relative_href(output_root=output_root, target=item.get("stageOneRawMarkdownPath"))
        output_prompt_href = _to_relative_href(output_root=output_root, target=item.get("stageOneOutputPromptPath"))
        metadata_link_html = (
            f'<a href="{html.escape(metadata_href)}" target="_blank" rel="noopener noreferrer">open</a>'
            if metadata_href
            else "[missing]"
        )
        output_prompt_link_html = (
            f'<a href="{html.escape(output_prompt_href)}" target="_blank" rel="noopener noreferrer">open</a>'
            if output_prompt_href
            else "[missing]"
        )
        raw_markdown_link_html = (
            f'<a href="{html.escape(raw_markdown_href)}" target="_blank" rel="noopener noreferrer">open</a>'
            if raw_markdown_href
            else "[missing]"
        )
        diagnostic_link_html = (
            f'<a href="{html.escape(diagnostic_href)}" target="_blank" rel="noopener noreferrer">open</a>'
            if diagnostic_href
            else "[n/a]"
        )
        raw_markdown = _read_optional_text(item.get("stageOneRawMarkdownPath"))
        stage_one_output_prompt = str(item.get("stageOneOutputPromptText") or "")
        status = str(item.get("status") or "unknown")
        asset_id = str(item.get("assetId") or "")
        error_text = str(item.get("error") or "")
        stage_one_prompt_model = str(item.get("stageOnePromptModel") or "")
        stage_two_model_id = str(item.get("stageTwoRenderModelId") or "")
        stage_two_provider = str(item.get("stageTwoRenderProvider") or "")
        stores = item.get("stageOneGeminiStoreNames") or []
        rag_docs = item.get("stageOneGeminiRagDocumentNames") or []
        product_refs = item.get("productReferenceImageUrlsSelected") or []
        source_panel = [
            '<div class="panel">',
            '<div class="panel-title">Source Image</div>',
        ]
        if source_href:
            source_panel.extend(
                [
                    f'<a href="{html.escape(source_href)}" target="_blank" rel="noopener noreferrer">',
                    f'  <img src="{html.escape(source_href)}" alt="{html.escape(str(item.get("sourceFile") or ""))}" loading="lazy" />',
                    "</a>",
                ]
            )
        else:
            source_panel.append('<div class="missing">Source image path missing.</div>')
        source_panel.append(
            f'<div class="path">{html.escape(str(item.get("sourceImagePath") or ""))}</div>'
        )
        source_panel.append("</div>")

        final_panel = [
            '<div class="panel">',
            '<div class="panel-title">Rendered Output</div>',
        ]
        if status == "succeeded" and final_href:
            final_panel.extend(
                [
                    f'<a href="{html.escape(final_href)}" target="_blank" rel="noopener noreferrer">',
                    f'  <img src="{html.escape(final_href)}" alt="{html.escape(str(item.get("sourceFile") or ""))}" loading="lazy" />',
                    "</a>",
                    f'<div class="path">{html.escape(str(item.get("finalImagePath") or ""))}</div>',
                ]
            )
        else:
            final_panel.append('<div class="missing">No rendered image was produced for this item.</div>')
            if error_text:
                final_panel.append(f'<pre class="error">{_html_pre(error_text)}</pre>')
        final_panel.append("</div>")

        card_parts = [
            f'<section class="card {html.escape(status)}">',
            '<div class="card-header">',
            f'  <div class="title">{html.escape(str(item.get("sourceFile") or ""))}</div>',
            f'  <div class="pill {html.escape(status)}">{html.escape(status)}</div>',
            "</div>",
            '<div class="meta-line">',
            f'  <span>Prompt model: <b>{html.escape(stage_one_prompt_model or "[missing]")}</b></span>',
            f'  <span>Render provider: <b>{html.escape(stage_two_provider or "[missing]")}</b></span>',
            f'  <span>Render model: <b>{html.escape(stage_two_model_id or "[missing]")}</b></span>',
            "</div>",
            '<div class="media-grid">',
            *source_panel,
            *final_panel,
            "</div>",
            '<div class="text-grid">',
            '  <div class="text-block">',
            "    <h3>Stage One Input Prompt</h3>",
            f'    <pre>{_html_pre(str(item.get("stageOneInputPromptText") or shared_input))}</pre>',
            "  </div>",
            '  <div class="text-block">',
            "    <h3>Gemini Output Prompt</h3>",
            f'    <pre>{_html_pre(stage_one_output_prompt)}</pre>',
            "  </div>",
            "</div>",
            '<details class="details-block">',
            "  <summary>Trace Details</summary>",
            '  <div class="details-grid">',
            f'    <div><b>Asset ID</b><br/>{html.escape(asset_id or "[not persisted]")}</div>',
            f'    <div><b>Source URL passed to workflow</b><br/>{html.escape(str(item.get("sourceImageUrl") or item.get("stageOneSourceImageUrl") or ""))}</div>',
            f'    <div><b>Gemini stores</b><br/>{html.escape(", ".join(str(value) for value in stores) or "[none]")}</div>',
            f'    <div><b>RAG documents</b><br/>{html.escape(", ".join(str(value) for value in rag_docs) or "[none]")}</div>',
            f'    <div><b>Selected product refs</b><br/>{html.escape(", ".join(str(value) for value in product_refs) or "[none]")}</div>',
            f'    <div><b>Metadata JSON</b><br/>{metadata_link_html}</div>',
            f'    <div><b>Output Prompt File</b><br/>{output_prompt_link_html}</div>',
            f'    <div><b>Raw Gemini Markdown</b><br/>{raw_markdown_link_html}</div>',
            f'    <div><b>Failure Diagnostic</b><br/>{diagnostic_link_html}</div>',
            "  </div>",
        ]
        if raw_markdown:
            card_parts.extend(
                [
                    '  <div class="text-block nested">',
                    "    <h3>Raw Gemini Markdown</h3>",
                    f'    <pre>{_html_pre(raw_markdown)}</pre>',
                    "  </div>",
                ]
            )
        card_parts.extend(
            [
                "</details>",
                "</section>",
            ]
        )
        cards.append("\n".join(card_parts))

    html_output = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Swipe Trace Audit</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f5f1e8; --panel: #fffdf8; --ink: #1c1a17; --muted: #6a6257; --line: #d8cdbd; --success: #1f6b44; --failure: #8a2f2f; --accent: #b66a2c; }",
            "    * { box-sizing: border-box; }",
            "    body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: radial-gradient(circle at top, #fff8e9 0%, var(--bg) 55%, #efe5d5 100%); color: var(--ink); }",
            "    main { max-width: 1480px; margin: 0 auto; padding: 32px 24px 72px; }",
            "    h1, h2, h3 { margin: 0; font-weight: 700; }",
            "    p { margin: 0; }",
            "    a { color: var(--accent); }",
            "    .hero { background: rgba(255, 253, 248, 0.86); border: 1px solid var(--line); border-radius: 18px; padding: 24px; backdrop-filter: blur(10px); }",
            "    .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 18px; }",
            "    .summary .tile { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; min-height: 88px; }",
            "    .prompt-block { margin-top: 18px; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }",
            "    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 'SFMono-Regular', Menlo, Consolas, monospace; }",
            "    .cards { display: grid; gap: 20px; margin-top: 24px; }",
            "    .card { background: rgba(255, 253, 248, 0.96); border: 1px solid var(--line); border-radius: 18px; padding: 18px; box-shadow: 0 10px 30px rgba(80, 53, 20, 0.08); }",
            "    .card.failed { border-color: rgba(138, 47, 47, 0.35); }",
            "    .card-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }",
            "    .title { font-size: 22px; }",
            "    .pill { border-radius: 999px; padding: 6px 10px; font: 12px/1.2 Arial, sans-serif; text-transform: uppercase; letter-spacing: 0.08em; border: 1px solid currentColor; }",
            "    .pill.succeeded { color: var(--success); }",
            "    .pill.failed { color: var(--failure); }",
            "    .meta-line { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 10px; color: var(--muted); font: 13px/1.4 Arial, sans-serif; }",
            "    .media-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }",
            "    .panel { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 12px; }",
            "    .panel-title { font: 12px/1.2 Arial, sans-serif; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 10px; }",
            "    .panel img { width: 100%; display: block; border-radius: 10px; background: #f1ede5; }",
            "    .path { margin-top: 10px; color: var(--muted); font: 12px/1.4 Arial, sans-serif; word-break: break-all; }",
            "    .text-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }",
            "    .text-block { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px; }",
            "    .text-block h3 { font-size: 14px; margin-bottom: 10px; font-family: Arial, sans-serif; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }",
            "    .details-block { margin-top: 16px; background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px; }",
            "    .details-block summary { cursor: pointer; font: 14px/1.4 Arial, sans-serif; color: var(--accent); }",
            "    .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 14px; font: 13px/1.45 Arial, sans-serif; }",
            "    .nested { margin-top: 14px; }",
            "    .missing { min-height: 180px; display: grid; place-items: center; border: 1px dashed var(--line); border-radius: 10px; color: var(--muted); background: #faf6ef; }",
            "    .error { color: var(--failure); background: #fff7f7; border: 1px solid rgba(138, 47, 47, 0.18); border-radius: 10px; padding: 10px; margin-top: 12px; }",
            "    @media (max-width: 980px) { .media-grid, .text-grid { grid-template-columns: 1fr; } .card-header { align-items: flex-start; flex-direction: column; } }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="hero">',
            "    <h1>Swipe Trace Audit</h1>",
            f'    <p>Template dir: {html.escape(str(run_info["templateDir"]))}</p>',
            f'    <p>Output root: {html.escape(str(run_info["outputRoot"]))}</p>',
            '    <div class="summary">',
            f'      <div class="tile"><b>Successes</b><br/>{run_info["successCount"]}</div>',
            f'      <div class="tile"><b>Failures</b><br/>{run_info["failureCount"]}</div>',
            f'      <div class="tile"><b>Brand</b><br/>{html.escape(str(run_info["brandName"] or "[missing]"))}</div>',
            f'      <div class="tile"><b>Angle</b><br/>{html.escape(str(run_info["angle"] or "[missing]"))}</div>',
            f'      <div class="tile"><b>Brief</b><br/>{html.escape(str(run_info["assetBriefId"]))}</div>',
            f'      <div class="tile"><b>Requirement Index</b><br/>{run_info["requirementIndex"]}</div>',
            "    </div>",
            '    <div class="prompt-block">',
            "      <h2>Shared Stage One Input Prompt</h2>",
            f'      <p style="margin: 8px 0 12px; color: var(--muted); font: 13px/1.4 Arial, sans-serif;">Saved at {html.escape(shared_input_path)}</p>',
            f'      <pre>{_html_pre(shared_input)}</pre>',
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
    _write_text(output_root / "index.html", html_output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a clean swipe trace batch and emit index.json.")
    parser.add_argument("--template-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--org-id", required=True)
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
    args = parser.parse_args()

    template_dir = Path(args.template_dir).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    if not template_dir.is_dir():
        raise RuntimeError(f"Template directory does not exist: {template_dir}")

    if args.clean:
        _clear_output_root(output_root)

    generated_dir = output_root / "generated-images"
    succeeded_dir = output_root / "succeeded"
    failed_dir = output_root / "failed"
    generated_dir.mkdir(parents=True, exist_ok=True)
    succeeded_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    shared_prompt = _resolve_shared_prompt_input(
        org_id=args.org_id,
        client_id=args.client_id,
        campaign_id=args.campaign_id,
        product_id=args.product_id,
        asset_brief_id=args.asset_brief_id,
        requirement_index=args.requirement_index,
    )
    _write_text(output_root / "stage-one-input-prompt.txt", shared_prompt["promptInputText"])

    handler = functools.partial(_QuietHandler, directory=str(template_dir))
    server = _ThreadingTCPServer((args.host, args.port), handler)
    server_host, server_port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    source_base_url = f"http://{server_host}:{server_port}"
    template_files = _iter_template_files(template_dir)

    results: list[dict[str, Any]] = []
    generated_manifest: list[dict[str, Any]] = []
    prompt_manifest: list[dict[str, Any]] = []
    failure_manifest: list[dict[str, Any]] = []

    try:
        for template_file in template_files:
            source_url = f"{source_base_url}/{urllib.parse.quote(template_file.name)}"
            print(f"[trace] running {template_file.name}", file=sys.stderr, flush=True)
            item_base = {
                "sourceFile": template_file.name,
                "sourceImagePath": str(template_file),
                "sourceImageUrl": source_url,
                "stageOneInputPromptText": shared_prompt["promptInputText"],
            }
            params: dict[str, Any] = {
                "org_id": args.org_id,
                "client_id": args.client_id,
                "product_id": args.product_id,
                "campaign_id": args.campaign_id,
                "asset_brief_id": args.asset_brief_id,
                "requirement_index": args.requirement_index,
                "idea_workspace_id": args.campaign_id,
                "swipe_image_url": source_url,
                "aspect_ratio": args.aspect_ratio,
                "count": 1,
            }
            if args.model:
                params["model"] = args.model
            if args.render_model_id:
                params["render_model_id"] = args.render_model_id

            try:
                activity_result = generate_swipe_image_ad_activity(params)
                asset_ids = activity_result.get("asset_ids") or []
                if not isinstance(asset_ids, list) or len(asset_ids) != 1:
                    raise RuntimeError(
                        f"Expected exactly one generated asset for {template_file.name}; got {asset_ids!r}"
                    )
                asset_id = str(asset_ids[0])
                asset_record = _load_asset(asset_id)
                content = asset_record["content"]
                ai_metadata = asset_record["aiMetadata"]
                final_image_url = str(content.get("sourceUrl") or "")
                if not final_image_url:
                    raise RuntimeError(f"Generated asset {asset_id} is missing content.sourceUrl.")
                output_suffix = _infer_output_suffix(final_image_url)
                output_path = generated_dir / f"{template_file.name}{output_suffix}"
                _download_to_path(final_image_url, output_path)

                raw_markdown = str(ai_metadata.get("swipePromptMarkdown") or "")
                output_prompt = str(
                    ai_metadata.get("swipePromptExtractedRaw")
                    or activity_result.get("image_prompt")
                    or ""
                )
                raw_markdown_path = succeeded_dir / f"{template_file.name}.swipe-prompt-markdown.md"
                output_prompt_path = succeeded_dir / f"{template_file.name}.image-prompt.txt"
                metadata_path = succeeded_dir / f"{template_file.name}.json"
                _write_text(raw_markdown_path, raw_markdown)
                _write_text(output_prompt_path, output_prompt)

                item = {
                    **item_base,
                    "status": "succeeded",
                    "assetId": asset_record["id"],
                    "assetPublicId": asset_record["publicId"],
                    "assetBriefArtifactId": asset_record["assetBriefArtifactId"],
                    "finalImageUrl": final_image_url,
                    "finalImagePath": str(output_path),
                    "finalImageWidth": asset_record["width"],
                    "finalImageHeight": asset_record["height"],
                    "finalImageContentType": asset_record["contentType"],
                    "assetCreatedAt": asset_record["createdAt"],
                    "stageOnePromptModel": str(ai_metadata.get("swipePromptModel") or activity_result.get("swipe_prompt_model") or ""),
                    "stageTwoRenderModelId": str(
                        ai_metadata.get("swipeRenderModelIdUsed") or activity_result.get("swipe_render_model_id") or ""
                    ),
                    "stageTwoRenderProvider": str(
                        ai_metadata.get("swipeRenderProvider") or activity_result.get("swipe_render_provider") or ""
                    ),
                    "stageOneStoresAttached": len(ai_metadata.get("swipeGeminiStoreNames") or []),
                    "stageOneGeminiStoreNames": ai_metadata.get("swipeGeminiStoreNames") or [],
                    "stageOneGeminiRagDocKeys": ai_metadata.get("swipeGeminiRagDocKeys") or [],
                    "stageOneGeminiRagBundleDocKeys": ai_metadata.get("swipeGeminiRagBundleDocKeys") or [],
                    "stageOneGeminiRagDocumentNames": ai_metadata.get("swipeGeminiRagDocumentNames") or [],
                    "stageOneSourceImageSha256": ai_metadata.get("swipePromptImageSha256"),
                    "stageOneSourceFilename": ai_metadata.get("swipeSourceFilename"),
                    "stageOnePromptInputText": str(ai_metadata.get("swipePromptInputText") or shared_prompt["promptInputText"]),
                    "stageOneOutputPromptText": output_prompt,
                    "stageOneRawMarkdownPath": str(raw_markdown_path),
                    "stageOneOutputPromptPath": str(output_prompt_path),
                    "metadataPath": str(metadata_path),
                    "productReferenceImageUrlsSelected": ai_metadata.get("swipeProductReferenceImageUrlsSelected") or [],
                    "productReferenceImageUrlsAvailable": ai_metadata.get("swipeProductReferenceImageUrlsAvailable") or [],
                }
                _write_json(metadata_path, item)
                results.append(item)
                print(
                    f"[trace] succeeded {template_file.name} asset={item['assetId']} model={item['stageTwoRenderModelId']}",
                    file=sys.stderr,
                    flush=True,
                )
                prompt_manifest.append(
                    {
                        "sourceFile": template_file.name,
                        "imagePromptPath": str(output_prompt_path),
                        "rawMarkdownPath": str(raw_markdown_path),
                        "metadataPath": str(metadata_path),
                    }
                )
                generated_manifest.append(
                    {
                        "sourceFile": template_file.name,
                        "status": "succeeded",
                        "outputPath": str(output_path),
                        "outputUrl": final_image_url,
                        "imagePromptPath": str(output_prompt_path),
                        "metadataPath": str(metadata_path),
                        "renderProvider": item["stageTwoRenderProvider"],
                        "renderModelId": item["stageTwoRenderModelId"],
                        "aspectRatio": args.aspect_ratio,
                        "assetId": item["assetId"],
                        "assetPublicId": item["assetPublicId"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                stage1_trace: dict[str, Any] | None = None
                stage1_trace_error: str | None = None
                try:
                    stage1_trace = _run_stage1_trace(
                        org_id=args.org_id,
                        client_id=args.client_id,
                        campaign_id=args.campaign_id,
                        product_id=args.product_id,
                        asset_brief_id=args.asset_brief_id,
                        requirement_index=args.requirement_index,
                        source_url=source_url,
                        prompt_input_text=shared_prompt["promptInputText"],
                        requested_model=args.model,
                        requested_render_model_id=args.render_model_id,
                    )
                except Exception as stage1_exc:  # noqa: BLE001
                    stage1_trace_error = str(stage1_exc)

                diagnostic_path = failed_dir / f"{template_file.name}.diagnostic.json"
                failure = {
                    **item_base,
                    "status": "failed",
                    "error": str(exc),
                    "diagnosticPath": str(diagnostic_path),
                }
                if stage1_trace is not None:
                    raw_markdown_path = failed_dir / f"{template_file.name}.swipe-prompt-markdown.md"
                    output_prompt_path = failed_dir / f"{template_file.name}.image-prompt.txt"
                    _write_text(raw_markdown_path, str(stage1_trace["rawMarkdown"]))
                    _write_text(output_prompt_path, str(stage1_trace["outputPromptText"]))
                    failure.update(
                        {
                            "stageOnePromptModel": stage1_trace["promptModel"],
                            "stageTwoRenderModelId": stage1_trace["renderModelId"],
                            "stageTwoRenderProvider": stage1_trace["renderProvider"],
                            "stageOneStoresAttached": stage1_trace["storesAttached"],
                            "stageOneGeminiStoreNames": stage1_trace["geminiStoreNames"],
                            "stageOneGeminiRagDocKeys": stage1_trace["geminiRagDocKeys"],
                            "stageOneGeminiRagBundleDocKeys": stage1_trace["geminiRagBundleDocKeys"],
                            "stageOneGeminiRagDocumentNames": stage1_trace["geminiRagDocumentNames"],
                            "stageOneSourceFilename": stage1_trace["sourceFilename"],
                            "stageOneSourceImageUrl": stage1_trace["sourceUrl"],
                            "stageOneRequiresProductImage": stage1_trace["requiresProductImage"],
                            "stageOneRequiresProductImagePolicySource": stage1_trace[
                                "requiresProductImagePolicySource"
                            ],
                            "stageOneOutputPromptText": stage1_trace["outputPromptText"],
                            "stageOneInlinedOutputPromptText": stage1_trace["inlinedOutputPromptText"],
                            "stageOneRawMarkdownPath": str(raw_markdown_path),
                            "stageOneOutputPromptPath": str(output_prompt_path),
                            "productReferenceImageUrlsSelected": stage1_trace[
                                "productReferenceImageUrlsSelected"
                            ],
                            "productReferenceImageUrlsAvailable": stage1_trace[
                                "productReferenceImageUrlsAvailable"
                            ],
                            "productPromptImageSourceUrl": stage1_trace["productPromptImageSourceUrl"],
                        }
                    )
                if stage1_trace_error is not None:
                    failure["stageOneDiagnosticError"] = stage1_trace_error
                _write_json(diagnostic_path, failure)
                results.append(failure)
                print(f"[trace] failed {template_file.name}: {exc}", file=sys.stderr, flush=True)
                failure_manifest.append(
                    {
                        "sourceFile": template_file.name,
                        "diagnosticPath": str(diagnostic_path),
                        "classification": "run_failed",
                        "error": str(exc),
                    }
                )
    finally:
        server.shutdown()
        server.server_close()

    _write_json(generated_dir / "manifest.json", generated_manifest)
    _write_json(
        output_root / "manifest.json",
        {
            "outputRoot": str(output_root),
            "templateDir": str(template_dir),
            "successfulPromptFiles": prompt_manifest,
            "remainingFailedFiles": failure_manifest,
        },
    )

    index_payload = {
        "runInfo": {
            "templateDir": str(template_dir),
            "outputRoot": str(output_root),
            "sourceBaseUrl": source_base_url,
            "orgId": args.org_id,
            "clientId": args.client_id,
            "productId": args.product_id,
            "campaignId": args.campaign_id,
            "assetBriefId": args.asset_brief_id,
            "requirementIndex": args.requirement_index,
            "aspectRatio": args.aspect_ratio,
            "promptTemplateSha256": shared_prompt["promptTemplateSha256"],
            "briefArtifactId": shared_prompt["briefArtifactId"],
            "briefCreativeConcept": shared_prompt["briefCreativeConcept"],
            "briefVariantName": shared_prompt["briefVariantName"],
            "brandName": shared_prompt["brandName"],
            "angle": shared_prompt["angle"],
            "successCount": len([item for item in results if item["status"] == "succeeded"]),
            "failureCount": len([item for item in results if item["status"] == "failed"]),
        },
        "sharedStageOneInputPrompt": {
            "text": shared_prompt["promptInputText"],
            "path": str(output_root / "stage-one-input-prompt.txt"),
        },
        "results": results,
    }
    _write_json(output_root / "index.json", index_payload)
    _render_index_html(output_root=output_root, index_payload=index_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
