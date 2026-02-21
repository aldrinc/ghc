#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import mimetypes
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import select, text


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "mos" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum
from app.db.models import ClientSwipeAsset, CompanySwipeAsset, CompanySwipeMedia
from app.db.repositories.artifacts import ArtifactsRepository
from app.services.media_storage import MediaStorage
from app.services.swipe_prompt import build_swipe_context_block, load_swipe_to_image_ad_prompt
from app.temporal.activities.swipe_image_ad_activities import (
    _brand_colors_fonts_from_design_tokens,
    _build_product_offer_context_block,
    _extract_brand_context,
    _format_audience_from_canon,
    _must_avoid_claims_from_canon,
)


@dataclass(frozen=True)
class SwipeCatalogEntry:
    company_swipe_id: str
    display_name: str
    custom_title: str | None
    company_title: str | None
    media_names: list[str]


@dataclass(frozen=True)
class PromptTemplateVersion:
    sha256: str
    text: str
    source: str


def _basename_from_urlish(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    parsed = urlparse(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw
    if not path:
        return None
    name = Path(unquote(path)).name.strip()
    return name or None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _collapse_whitespace(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _preview(value: str, max_chars: int = 220) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def _html_pre(value: str | None) -> str:
    return html.escape(value or "")


def _sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_prompt_template_versions() -> tuple[PromptTemplateVersion, dict[str, PromptTemplateVersion]]:
    local_text, local_sha = load_swipe_to_image_ad_prompt()
    local_version = PromptTemplateVersion(
        sha256=local_sha,
        text=local_text,
        source="working_copy",
    )
    versions: dict[str, PromptTemplateVersion] = {local_version.sha256: local_version}

    head_relpath = "mos/backend/app/prompts/swipe/swipe_to_image_ad.md"
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{head_relpath}"],
            check=True,
            capture_output=True,
            text=True,
        )
        head_text = proc.stdout
        if head_text:
            head_sha = _sha256_text(head_text)
            versions.setdefault(
                head_sha,
                PromptTemplateVersion(
                    sha256=head_sha,
                    text=head_text,
                    source="git_HEAD",
                ),
            )
    except Exception:
        pass

    return local_version, versions


def _load_brief(
    *,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
    asset_brief_id: str,
) -> dict[str, Any]:
    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        briefs_artifacts = artifacts_repo.list(
            org_id=org_id,
            client_id=client_id,
            campaign_id=campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            limit=200,
        )

        for art in briefs_artifacts:
            payload = art.data if isinstance(art.data, dict) else {}
            for entry in payload.get("asset_briefs") or []:
                if isinstance(entry, dict) and str(entry.get("id")) == str(asset_brief_id):
                    return entry

    raise RuntimeError(f"Asset brief not found for export: {asset_brief_id}")


def _load_swipe_catalog(*, org_id: str, client_id: str) -> dict[str, SwipeCatalogEntry]:
    with session_scope() as session:
        client_swipes = list(
            session.scalars(
                select(ClientSwipeAsset)
                .where(
                    ClientSwipeAsset.org_id == org_id,
                    ClientSwipeAsset.client_id == client_id,
                )
                .order_by(ClientSwipeAsset.created_at.desc())
            ).all()
        )

        company_ids = [entry.company_swipe_id for entry in client_swipes if entry.company_swipe_id]
        company_assets = {
            str(item.id): item
            for item in session.scalars(
                select(CompanySwipeAsset).where(CompanySwipeAsset.id.in_(company_ids))
            ).all()
        } if company_ids else {}

        media_by_company_id: dict[str, list[CompanySwipeMedia]] = {}
        if company_ids:
            media_rows = list(
                session.scalars(
                    select(CompanySwipeMedia)
                    .where(CompanySwipeMedia.swipe_asset_id.in_(company_ids))
                    .order_by(CompanySwipeMedia.created_at.asc())
                ).all()
            )
            for media in media_rows:
                key = str(media.swipe_asset_id)
                media_by_company_id.setdefault(key, []).append(media)

    out: dict[str, SwipeCatalogEntry] = {}
    for entry in client_swipes:
        company_swipe_id = str(entry.company_swipe_id or "").strip()
        if not company_swipe_id:
            continue

        company_asset = company_assets.get(company_swipe_id)
        media_rows = media_by_company_id.get(company_swipe_id, [])
        media_names: list[str] = []
        for media in media_rows:
            for candidate in (media.path, media.download_url, media.url, media.thumbnail_url):
                name = _basename_from_urlish(candidate)
                if name and name not in media_names:
                    media_names.append(name)

        custom_title = _safe_str(entry.custom_title).strip() or None
        company_title = _safe_str(getattr(company_asset, "title", "")).strip() or None
        default_media_name = media_names[0] if media_names else None
        display_name = custom_title or company_title or default_media_name or company_swipe_id

        out[company_swipe_id] = SwipeCatalogEntry(
            company_swipe_id=company_swipe_id,
            display_name=display_name,
            custom_title=custom_title,
            company_title=company_title,
            media_names=media_names,
        )
    return out


def export_brief_outputs(*, brief_id: str, output_root: Path) -> Path:
    assets_sql = text(
        """
        SELECT
          id::text AS asset_id,
          org_id::text AS org_id,
          client_id::text AS client_id,
          COALESCE(campaign_id::text, '') AS campaign_id,
          COALESCE(product_id::text, '') AS product_id,
          created_at,
          channel_id,
          format,
          content_type,
          size_bytes,
          width,
          height,
          storage_key,
          content,
          ai_metadata
        FROM assets
        WHERE content->>'assetBriefId' = :brief_id
          AND storage_key IS NOT NULL
        ORDER BY COALESCE((content->>'requirementIndex')::int, -1), created_at ASC, id ASC
        """
    )
    with session_scope() as session:
        rows = [dict(item._mapping) for item in session.execute(assets_sql, {"brief_id": brief_id}).all()]

    if not rows:
        raise RuntimeError(f"No stored assets found for brief: {brief_id}")

    first = rows[0]
    org_id = first["org_id"]
    client_id = first["client_id"]
    campaign_id = first["campaign_id"] or None
    product_id = first["product_id"] or None
    if not product_id:
        raise RuntimeError(f"Missing product_id for brief assets: {brief_id}")

    brief = _load_brief(org_id=org_id, client_id=client_id, campaign_id=campaign_id, asset_brief_id=brief_id)
    constraints = [item for item in (brief.get("constraints") or []) if isinstance(item, str) and item.strip()]
    tone_guidelines = [item for item in (brief.get("toneGuidelines") or []) if isinstance(item, str) and item.strip()]
    visual_guidelines = [item for item in (brief.get("visualGuidelines") or []) if isinstance(item, str) and item.strip()]
    creative_concept = _safe_str(brief.get("creativeConcept")).strip()
    if not creative_concept:
        raise RuntimeError(f"Asset brief is missing creativeConcept: {brief_id}")

    with session_scope() as session:
        brand_ctx = _extract_brand_context(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
        )
        canon = brand_ctx.get("canon") if isinstance(brand_ctx.get("canon"), dict) else {}
        tokens = brand_ctx.get("design_system_tokens") if isinstance(brand_ctx.get("design_system_tokens"), dict) else {}
        audience = _format_audience_from_canon(canon)
        brand_colors_fonts = _brand_colors_fonts_from_design_tokens(tokens)
        must_avoid_claims = _must_avoid_claims_from_canon(canon)
        funnel_id = _safe_str(brief.get("funnelId") or brief.get("funnel_id")).strip() or None
        offer_context_block, _, _ = _build_product_offer_context_block(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            funnel_id=funnel_id,
        )

    local_template_version, template_versions_by_sha = _load_prompt_template_versions()
    swipe_catalog = _load_swipe_catalog(org_id=org_id, client_id=client_id)
    used_company_ids = Counter(
        _safe_str((row.get("ai_metadata") or {}).get("swipeCompanyId")).strip()
        for row in rows
        if _safe_str((row.get("ai_metadata") or {}).get("swipeCompanyId")).strip()
    )

    output_dir = output_root / brief_id
    output_dir.mkdir(parents=True, exist_ok=True)

    for old_file in output_dir.glob("*_asset-*.*"):
        old_file.unlink(missing_ok=True)

    storage = MediaStorage()
    manifest_path = output_dir / "manifest.tsv"
    prompts_path = output_dir / "prompt_details.jsonl"
    index_path = output_dir / "index.html"

    manifest_columns = [
        "idx",
        "file_name",
        "asset_id",
        "created_at",
        "requirement_index",
        "channel_id",
        "format",
        "source_kind",
        "swipe_company_id",
        "swipe_template_name",
        "swipe_source_url",
        "swipe_prompt_model",
        "prompt_template_sha256",
        "prompt_template_sha_match",
        "prompt_template_source",
        "content_type",
        "size_bytes",
        "width",
        "height",
        "storage_key",
        "generated_prompt_chars",
        "renderer_prompt_chars",
        "gemini_markdown_chars",
        "gemini_markdown_is_full",
    ]

    prompt_details_lines: list[str] = []
    manifest_rows: list[dict[str, Any]] = []
    card_html: list[str] = []

    for idx, row in enumerate(rows, start=1):
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        metadata = row.get("ai_metadata") if isinstance(row.get("ai_metadata"), dict) else {}

        requirement_index = int(content.get("requirementIndex")) if content.get("requirementIndex") is not None else -1
        requirement = content.get("requirement") if isinstance(content.get("requirement"), dict) else {}
        channel_id = _safe_str(row.get("channel_id")).strip()

        reconstructed_context_block = build_swipe_context_block(
            brand_name=_safe_str(brand_ctx.get("client_name")),
            product_name=_safe_str(brand_ctx.get("product_title")),
            audience=audience,
            brand_colors_fonts=brand_colors_fonts,
            must_avoid_claims=must_avoid_claims,
            assets=None,
            creative_concept=creative_concept,
            channel=_safe_str(requirement.get("channel")).strip() or channel_id,
            angle=_safe_str(requirement.get("angle")).strip() or None,
            hook=_safe_str(requirement.get("hook")).strip() or None,
            constraints=constraints,
            tone_guidelines=tone_guidelines,
            visual_guidelines=visual_guidelines,
        )
        reconstructed_context_block = "\n\n".join([reconstructed_context_block, offer_context_block]).strip()
        stored_context_block = _safe_str(metadata.get("swipePromptContextBlock")).strip()
        effective_context_block = stored_context_block or reconstructed_context_block

        swipe_company_id = _safe_str(metadata.get("swipeCompanyId")).strip()
        swipe_source_url = _safe_str(metadata.get("swipeSourceUrl")).strip()
        swipe_catalog_entry = swipe_catalog.get(swipe_company_id)
        source_name = _basename_from_urlish(swipe_source_url)
        swipe_template_name = (
            swipe_catalog_entry.display_name
            if swipe_catalog_entry
            else source_name or (swipe_company_id or "[UNKNOWN]")
        )

        generated_prompt = _safe_str(content.get("prompt"))
        renderer_prompt = _safe_str(metadata.get("promptUsed"))
        gemini_markdown_full = _safe_str(metadata.get("swipePromptMarkdown"))
        gemini_markdown_preview = _safe_str(metadata.get("swipePromptMarkdownPreview"))
        gemini_markdown = gemini_markdown_full or gemini_markdown_preview
        gemini_markdown_is_full = bool(gemini_markdown_full)

        prompt_template_sha_asset = _safe_str(metadata.get("swipePromptTemplateSha256")).strip()
        template_version = (
            template_versions_by_sha.get(prompt_template_sha_asset)
            if prompt_template_sha_asset
            else local_template_version
        ) or local_template_version
        prompt_template_text = template_version.text
        prompt_template_sha = template_version.sha256
        prompt_template_source = template_version.source
        prompt_template_sha_match = bool(prompt_template_sha_asset and prompt_template_sha_asset == prompt_template_sha)

        original_prompt_text = (
            f"{effective_context_block}\n\n"
            f"{prompt_template_text}\n\n"
            f"[COMPETITOR_SWIPE_IMAGE_URL]\n{swipe_source_url or '[UNKNOWN]'}\n"
        )

        storage_key = _safe_str(row.get("storage_key"))
        content_type = _safe_str(row.get("content_type")).strip() or "application/octet-stream"
        ext = None
        if storage_key and "." in storage_key.rsplit("/", 1)[-1]:
            ext = storage_key.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
        if not ext:
            guessed = mimetypes.guess_extension(content_type)
            ext = guessed.lstrip(".") if guessed else "bin"

        file_name = f"{idx:03d}_req{requirement_index}_asset-{row['asset_id']}.{ext}"
        output_path = output_dir / file_name
        data, downloaded_content_type = storage.download_bytes(key=storage_key)
        output_path.write_bytes(data)
        final_content_type = downloaded_content_type or content_type

        created_at = row.get("created_at")
        created_at_str = created_at.isoformat() if created_at is not None else ""
        source_kind = _safe_str(content.get("sourceKind"))
        swipe_prompt_model = _safe_str(metadata.get("swipePromptModel"))

        manifest_rows.append(
            {
                "idx": idx,
                "file_name": file_name,
                "asset_id": _safe_str(row.get("asset_id")),
                "created_at": created_at_str,
                "requirement_index": requirement_index,
                "channel_id": channel_id,
                "format": _safe_str(row.get("format")),
                "source_kind": source_kind,
                "swipe_company_id": swipe_company_id,
                "swipe_template_name": swipe_template_name,
                "swipe_source_url": swipe_source_url,
                "swipe_prompt_model": swipe_prompt_model,
                "prompt_template_sha256": prompt_template_sha_asset,
                "prompt_template_sha_match": "yes" if prompt_template_sha_match else "no",
                "prompt_template_source": prompt_template_source,
                "content_type": final_content_type,
                "size_bytes": row.get("size_bytes") or len(data),
                "width": row.get("width") or "",
                "height": row.get("height") or "",
                "storage_key": storage_key,
                "generated_prompt_chars": len(generated_prompt),
                "renderer_prompt_chars": len(renderer_prompt),
                "gemini_markdown_chars": len(gemini_markdown),
                "gemini_markdown_is_full": "yes" if gemini_markdown_is_full else "no",
            }
        )

        prompt_details = {
            "asset_id": _safe_str(row.get("asset_id")),
            "file_name": file_name,
            "requirement_index": requirement_index,
            "swipe_company_id": swipe_company_id,
            "swipe_template_name": swipe_template_name,
            "swipe_source_url": swipe_source_url,
            "prompt_template_key": _safe_str(metadata.get("swipePromptTemplateKey")) or "prompts/swipe/swipe_to_image_ad.md",
            "prompt_template_sha256_asset": prompt_template_sha_asset,
            "prompt_template_sha256_local": prompt_template_sha,
            "prompt_template_sha_match": prompt_template_sha_match,
            "prompt_template_source": prompt_template_source,
            "swipe_prompt_model": swipe_prompt_model,
            "context_block": effective_context_block,
            "original_prompt_input_text": original_prompt_text,
            "generated_prompt_extracted": generated_prompt,
            "renderer_prompt_used": renderer_prompt,
            "gemini_output_markdown": gemini_markdown,
            "gemini_output_markdown_is_full": gemini_markdown_is_full,
            "gemini_output_truncated_note": ""
            if gemini_markdown_is_full
            else "Only preview is stored for this asset in ai_metadata.swipePromptMarkdownPreview.",
        }
        prompt_details_lines.append(json.dumps(prompt_details, ensure_ascii=False))

        media_names = ", ".join(swipe_catalog_entry.media_names) if swipe_catalog_entry else ""
        markdown_state = "full" if gemini_markdown_is_full else "preview-only"

        card_html.append(
            "\n".join(
                [
                    '<div class="card">',
                    f'  <img src="{html.escape(file_name)}" alt="{html.escape(_safe_str(row.get("asset_id")))}" loading="lazy" />',
                    '  <div class="meta">',
                    f'    <div><b>{html.escape(_safe_str(row.get("asset_id")))}</b></div>',
                    f'    <div>req={requirement_index} · {html.escape(channel_id)}/{html.escape(_safe_str(row.get("format")))}</div>',
                    f'    <div>template: {html.escape(swipe_template_name)}</div>',
                    f'    <div>source: {html.escape(source_name or "[UNKNOWN]")}</div>',
                    f'    <div>created: {html.escape(created_at_str)}</div>',
                    f'    <div>prompt preview: {html.escape(_preview(_collapse_whitespace(generated_prompt)))}</div>',
                    '    <details>',
                    "      <summary>Prompt Details</summary>",
                    f'      <div class="section"><b>Swipe Template</b><br/>companySwipeId: {html.escape(swipe_company_id or "[UNKNOWN]")}<br/>label: {html.escape(swipe_template_name)}<br/>sourceUrl: {html.escape(swipe_source_url or "[UNKNOWN]")}<br/>mediaFiles: {html.escape(media_names or "[UNKNOWN]")}</div>',
                    f'      <div class="section"><b>Prompt Template</b><br/>key: {html.escape(_safe_str(metadata.get("swipePromptTemplateKey")) or "prompts/swipe/swipe_to_image_ad.md")}<br/>asset sha: {html.escape(prompt_template_sha_asset or "[UNKNOWN]")}<br/>resolved sha: {html.escape(prompt_template_sha)}<br/>template source: {html.escape(prompt_template_source)}<br/>sha match: {"yes" if prompt_template_sha_match else "no"}</div>',
                    '      <details class="nested">',
                    "        <summary>Original Prompt Input (full)</summary>",
                    f'        <pre>{_html_pre(original_prompt_text)}</pre>',
                    "      </details>",
                    '      <details class="nested">',
                    "        <summary>Generated Prompt (extracted, full)</summary>",
                    f'        <pre>{_html_pre(generated_prompt)}</pre>',
                    "      </details>",
                    '      <details class="nested">',
                    "        <summary>Renderer Prompt Used (full)</summary>",
                    f'        <pre>{_html_pre(renderer_prompt)}</pre>',
                    "      </details>",
                    '      <details class="nested">',
                    f"        <summary>Gemini Output Markdown ({markdown_state})</summary>",
                    f'        <pre>{_html_pre(gemini_markdown)}</pre>',
                    (
                        '        <div class="warn">Only preview is persisted for this run. '
                        'Future runs now store full markdown in ai_metadata.swipePromptMarkdown.</div>'
                        if not gemini_markdown_is_full
                        else ""
                    ),
                    "      </details>",
                    "    </details>",
                    "  </div>",
                    "</div>",
                ]
            )
        )

    with manifest_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=manifest_columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(manifest_rows)

    prompts_path.write_text("\n".join(prompt_details_lines) + "\n", encoding="utf-8")

    used_templates = []
    for company_swipe_id, count in used_company_ids.most_common():
        entry = swipe_catalog.get(company_swipe_id)
        label = entry.display_name if entry else company_swipe_id
        media_names = ", ".join(entry.media_names) if entry else ""
        used_templates.append(
            f"<tr><td>{html.escape(company_swipe_id)}</td><td>{html.escape(label)}</td><td>{count}</td><td>{html.escape(media_names)}</td></tr>"
        )

    catalog_rows = []
    for company_swipe_id, entry in sorted(swipe_catalog.items(), key=lambda item: item[1].display_name.lower()):
        is_used = "used" if company_swipe_id in used_company_ids else "unused"
        count = used_company_ids.get(company_swipe_id, 0)
        catalog_rows.append(
            f"<tr><td>{html.escape(company_swipe_id)}</td><td>{html.escape(entry.display_name)}</td><td>{html.escape(entry.custom_title or '')}</td><td>{html.escape(entry.company_title or '')}</td><td>{html.escape(', '.join(entry.media_names))}</td><td>{is_used}</td><td>{count}</td></tr>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Swipe Brief Export</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 16px; background: #f7f7f7; color: #222; }}
    h1 {{ font-size: 20px; margin: 0 0 8px; }}
    h2 {{ font-size: 16px; margin: 24px 0 8px; }}
    p {{ margin: 4px 0; }}
    .hint {{ color: #555; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #ddd; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #f0f0f0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
    .card {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }}
    img {{ display: block; width: 100%; height: auto; background: #eee; }}
    .meta {{ padding: 8px; font-size: 12px; line-height: 1.4; word-break: break-word; }}
    details {{ margin-top: 6px; }}
    details summary {{ cursor: pointer; font-weight: 600; }}
    details.nested summary {{ font-weight: 500; }}
    .section {{ margin-top: 8px; padding: 6px; background: #fafafa; border: 1px solid #ececec; border-radius: 6px; }}
    pre {{ margin: 6px 0 0; padding: 8px; background: #101010; color: #f8f8f2; border-radius: 6px; overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    .warn {{ margin-top: 6px; color: #9a6f00; font-size: 12px; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; background: #e9eef8; font-size: 12px; margin-right: 6px; }}
  </style>
</head>
<body>
  <h1>Swipe Brief Export: {html.escape(brief_id)}</h1>
  <p><span class="pill">assets: {len(manifest_rows)}</span><span class="pill">used swipe templates: {len(used_company_ids)}</span><span class="pill">client swipes available: {len(swipe_catalog)}</span></p>
  <p class="hint">Files: manifest.tsv (summary), prompt_details.jsonl (full prompt payload per asset). Prompts are collapsed by default below each card.</p>

  <h2>Used Swipe Templates</h2>
  <table>
    <thead><tr><th>companySwipeId</th><th>label</th><th>generated assets</th><th>media files</th></tr></thead>
    <tbody>
      {''.join(used_templates) if used_templates else '<tr><td colspan="4">No used swipe templates found in ai_metadata.</td></tr>'}
    </tbody>
  </table>

  <h2>Client Swipe Coverage</h2>
  <table>
    <thead><tr><th>companySwipeId</th><th>display</th><th>custom title</th><th>company title</th><th>media files</th><th>status</th><th>used count</th></tr></thead>
    <tbody>
      {''.join(catalog_rows) if catalog_rows else '<tr><td colspan="7">No client swipe entries found.</td></tr>'}
    </tbody>
  </table>

  <h2>Generated Assets</h2>
  <div class="grid">
    {''.join(card_html)}
  </div>
</body>
</html>
"""
    index_path.write_text(html_doc, encoding="utf-8")

    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all generated assets for an asset brief, including swipe template + full prompt details."
    )
    parser.add_argument("brief_id", help="Asset brief id (e.g. brief_exp_eye_comfort_var_angle_001)")
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / "swipe-output"),
        help="Root output folder (default: repo/swipe-output)",
    )
    args = parser.parse_args()

    output_dir = export_brief_outputs(
        brief_id=args.brief_id,
        output_root=Path(args.output_root).expanduser().resolve(),
    )
    print(f"exported_dir={output_dir}")
    print(f"index={output_dir / 'index.html'}")
    print(f"manifest={output_dir / 'manifest.tsv'}")
    print(f"prompt_details={output_dir / 'prompt_details.jsonl'}")


if __name__ == "__main__":
    main()
