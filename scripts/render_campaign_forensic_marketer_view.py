#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _html_pre(value: str | None) -> str:
    return html.escape(value or "")


def _slug_label(value: str) -> str:
    return " ".join(part for part in value.replace("_", " ").replace("-", " ").split()).strip()


def _format_when(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ").replace("+00:00", " UTC")


def _badge(text: str, kind: str = "neutral") -> str:
    return f'<span class="badge badge-{html.escape(kind)}">{html.escape(text)}</span>'


def _copy_diff_fields(asset: dict[str, Any]) -> list[str]:
    creative = asset.get("creativeSpec") or {}
    swipe = asset.get("swipeCopyPack") or {}
    diffs: list[str] = []
    pairs = [
        ("headline", _safe_str(creative.get("headline")), _safe_str(swipe.get("metaHeadline"))),
        ("primary text", _safe_str(creative.get("primary_text")), _safe_str(swipe.get("metaPrimaryText"))),
        ("description", _safe_str(creative.get("description")), _safe_str(swipe.get("metaDescription"))),
        ("CTA", _safe_str(creative.get("call_to_action_type")), _safe_str(swipe.get("metaCta"))),
    ]
    for label, left, right in pairs:
        if left != right:
            diffs.append(label)
    return diffs


def _status_meta(asset: dict[str, Any]) -> tuple[str, str, str]:
    creative = asset.get("creativeSpec")
    if not creative:
        return (
            "No campaign copy attached",
            "warn",
            "This creative has no current campaign copy attached in Meta review.",
        )
    if asset.get("creativeSpecMatchesSwipeCopy") is False:
        diffs = _copy_diff_fields(asset)
        diff_text = ", ".join(diffs) if diffs else "copy fields"
        return (
            "Campaign copy differs",
            "danger",
            f"The current campaign copy differs from the swipe-generated copy in: {diff_text}.",
        )
    return (
        "Campaign copy matches",
        "good",
        "The current campaign copy matches the swipe-generated copy for this creative.",
    )


def _display_headline(asset: dict[str, Any]) -> str:
    creative = asset.get("creativeSpec") or {}
    swipe = asset.get("swipeCopyPack") or {}
    baseline = ((asset.get("linkedAdCopyPack") or {}).get("copyPack")) or {}
    return (
        _safe_str(creative.get("headline")).strip()
        or _safe_str(swipe.get("metaHeadline")).strip()
        or _safe_str(baseline.get("metaHeadline")).strip()
        or _safe_str((asset.get("swipeSource") or {}).get("filename")).strip()
        or _safe_str(asset.get("assetId")).strip()
    )


def _source_label(asset: dict[str, Any]) -> str:
    swipe = asset.get("swipeSource") or {}
    return (
        _safe_str(swipe.get("filename")).strip()
        or _safe_str(swipe.get("label")).strip()
        or "Unknown source swipe"
    )


def _copy_card(
    *,
    title: str,
    subtitle: str,
    headline: str,
    description: str,
    cta: str,
    primary_text: str,
    emphasis: str = "neutral",
) -> str:
    return "\n".join(
        [
            f'<section class="copy-card copy-card-{html.escape(emphasis)}">',
            f"<h4>{html.escape(title)}</h4>",
            f'<p class="copy-subtitle">{html.escape(subtitle)}</p>',
            f'<p><span class="field-label">Headline</span>{html.escape(headline or "None")}</p>',
            f'<p><span class="field-label">Description</span>{html.escape(description or "None")}</p>',
            f'<p><span class="field-label">CTA</span>{html.escape(cta or "None")}</p>',
            '<div class="copy-body">',
            '<div class="field-label">Primary Text</div>',
            f'<div class="body-text">{html.escape(primary_text or "None")}</div>',
            "</div>",
            "</section>",
        ]
    )


def _prompt_panel(title: str, explainer: str, text_value: str) -> str:
    return "\n".join(
        [
            '<details class="prompt-panel">',
            f"<summary>{html.escape(title)}</summary>",
            f'<p class="prompt-explainer">{html.escape(explainer)}</p>',
            f'<div class="prompt-text">{_html_pre(text_value or "Not available.")}</div>',
            "</details>",
        ]
    )


def render_marketer_view(export_dir: Path) -> tuple[Path, Path]:
    bundle_path = export_dir / "bundle.json"
    if not bundle_path.exists():
        raise RuntimeError(f"Missing bundle.json: {bundle_path}")

    data = json.loads(bundle_path.read_text())

    technical_source = export_dir / "index.html"
    technical_target = export_dir / "technical-appendix.html"
    if technical_source.exists():
        shutil.copyfile(technical_source, technical_target)

    campaign = data["campaign"]
    assets = data["assets"]
    ad_copy_pack_artifacts = data["adCopyPackArtifacts"]
    warnings = data["warnings"]

    missing_copy_assets = [asset for asset in assets if not asset.get("creativeSpec")]
    mismatched_copy_assets = [asset for asset in assets if asset.get("creativeSpecMatchesSwipeCopy") is False]

    gallery_cards: list[str] = []
    detail_sections: list[str] = []
    sidebar_links: list[str] = []

    for asset in assets:
        asset_id = _safe_str(asset.get("assetId"))
        anchor = f"asset-{asset_id}"
        headline = _display_headline(asset)
        source_label = _source_label(asset)
        status_label, status_kind, status_message = _status_meta(asset)
        created_at = _format_when(_safe_str(asset.get("createdAt")))
        channel = _slug_label(_safe_str(asset.get("channelId")))
        generated_media = asset.get("generatedMedia") or {}
        source_swipe = asset.get("swipeSource") or {}
        source_download = source_swipe.get("download") or {}
        product_refs = asset.get("productReferenceMedia") or []
        swipe_copy = asset.get("swipeCopyPack") or {}
        current_copy = asset.get("creativeSpec") or {}
        baseline_copy = ((asset.get("linkedAdCopyPack") or {}).get("copyPack")) or {}
        prompt_chain = asset.get("promptChain") or {}

        gallery_cards.append(
            "\n".join(
                [
                    f'<a href="#{html.escape(anchor)}" class="gallery-card" data-search="{html.escape(_safe_str(asset.get("searchText")))}" data-channel="{html.escape(channel.lower())}" data-status="{html.escape(status_kind)}">',
                    (
                        f'<img src="{html.escape(_safe_str(generated_media.get("path")))}" alt="{html.escape(headline)}" loading="lazy" />'
                        if _safe_str(generated_media.get("path"))
                        else '<div class="gallery-placeholder">Image unavailable</div>'
                    ),
                    '<div class="gallery-copy">',
                    f'<div class="gallery-badges">{_badge(channel, "info")} {_badge(status_label, status_kind)}</div>',
                    f"<h3>{html.escape(headline)}</h3>",
                    f'<p class="gallery-source">Source swipe: {html.escape(source_label)}</p>',
                    f'<p class="gallery-meta">{html.escape(created_at)}</p>',
                    f'<p class="gallery-id">{html.escape(asset_id)}</p>',
                    "</div>",
                    "</a>",
                ]
            )
        )

        sidebar_links.append(
            "\n".join(
                [
                    f'<a href="#{html.escape(anchor)}" class="sidebar-link" data-search="{html.escape(_safe_str(asset.get("searchText")))}" data-channel="{html.escape(channel.lower())}" data-status="{html.escape(status_kind)}">',
                    f"<strong>{html.escape(headline)}</strong>",
                    f"<span>{html.escape(channel)} · {html.escape(source_label)}</span>",
                    f"<small>{html.escape(asset_id)}</small>",
                    "</a>",
                ]
            )
        )

        product_ref_gallery = []
        for ref in product_refs:
            ref_path = _safe_str(ref.get("path"))
            ref_label = _safe_str(ref.get("assetId")) or "Product reference"
            product_ref_gallery.append(
                "\n".join(
                    [
                        '<figure class="reference-thumb">',
                        f'<img src="{html.escape(ref_path)}" alt="{html.escape(ref_label)}" loading="lazy" />',
                        f"<figcaption>{html.escape(ref_label)}</figcaption>",
                        "</figure>",
                    ]
                )
            )
        if not product_ref_gallery:
            product_ref_gallery.append('<div class="empty-note">No product reference image was attached for this creative.</div>')

        callout_html = ""
        if status_kind != "good":
            callout_html = f'<div class="asset-callout asset-callout-{html.escape(status_kind)}">{html.escape(status_message)}</div>'

        prompt_sections = []
        prompt_sections.append(
            _prompt_panel(
                "1. Swipe Copy Prompt",
                "This is the exact prompt used to generate the swipe-specific copy pack for this creative.",
                _safe_str((asset.get("swipeCopyPrompt") or {}).get("promptText")),
            )
        )
        prompt_sections.append(
            _prompt_panel(
                "2. Image Prompt Input",
                "This is the human-readable input assembled before the image-prompt stage.",
                _safe_str(prompt_chain.get("stage1InputText")),
            )
        )
        prompt_sections.append(
            _prompt_panel(
                "3. Image Prompt Output",
                "This is what the system returned before the final prompt was extracted for rendering.",
                _safe_str(prompt_chain.get("stage1Markdown")),
            )
        )
        prompt_sections.append(
            _prompt_panel(
                "4. Final Render Prompt",
                "This is the exact prompt sent into the image renderer to create the final ad image.",
                _safe_str(prompt_chain.get("stage2RenderPromptUsed")),
            )
        )

        detail_sections.append(
            "\n".join(
                [
                    f'<section id="{html.escape(anchor)}" class="asset-section" data-search="{html.escape(_safe_str(asset.get("searchText")))}" data-channel="{html.escape(channel.lower())}" data-status="{html.escape(status_kind)}">',
                    '<header class="asset-header">',
                    f"<div><p class=\"eyebrow\">{html.escape(channel)} creative review</p><h2>{html.escape(headline)}</h2><p class=\"asset-meta\">Source swipe: {html.escape(source_label)} · Created: {html.escape(created_at)}</p><p class=\"asset-id\">Asset ID: {html.escape(asset_id)}</p></div>",
                    f'<div class="asset-badges">{_badge(status_label, status_kind)} {_badge("Product reference attached" if product_refs else "No product reference", "good" if product_refs else "warn")}</div>',
                    "</header>",
                    callout_html,
                    '<div class="visual-grid">',
                    '<div class="visual-card">',
                    "<h3>Generated Ad</h3>",
                    (
                        f'<img src="{html.escape(_safe_str(generated_media.get("path")))}" alt="{html.escape(headline)}" loading="lazy" />'
                        if _safe_str(generated_media.get("path"))
                        else '<div class="empty-note">Generated image is not available.</div>'
                    ),
                    "</div>",
                    '<div class="visual-card">',
                    "<h3>Source Swipe</h3>",
                    (
                        f'<img src="{html.escape(_safe_str(source_download.get("path")))}" alt="{html.escape(source_label)}" loading="lazy" />'
                        if _safe_str(source_download.get("path"))
                        else '<div class="empty-note">Source swipe image is not available.</div>'
                    ),
                    f'<p class="visual-caption">{html.escape(source_label)}</p>',
                    "</div>",
                    '<div class="visual-card">',
                    "<h3>Product Reference</h3>",
                    '<div class="reference-grid">',
                    "".join(product_ref_gallery),
                    "</div>",
                    "</div>",
                    "</div>",
                    '<div class="copy-grid">',
                    _copy_card(
                        title="Current Campaign Copy",
                        subtitle="What is currently pasted into the campaign today.",
                        headline=_safe_str(current_copy.get("headline")),
                        description=_safe_str(current_copy.get("description")),
                        cta=_safe_str(current_copy.get("call_to_action_type")),
                        primary_text=_safe_str(current_copy.get("primary_text")),
                        emphasis="current",
                    ),
                    _copy_card(
                        title="Swipe-Specific Copy",
                        subtitle="What the system generated for this exact swipe execution.",
                        headline=_safe_str(swipe_copy.get("metaHeadline")),
                        description=_safe_str(swipe_copy.get("metaDescription")),
                        cta=_safe_str(swipe_copy.get("metaCta")),
                        primary_text=_safe_str(swipe_copy.get("metaPrimaryText")),
                        emphasis="swipe",
                    ),
                    _copy_card(
                        title="Original Requirement Copy Pack",
                        subtitle="The broader baseline copy pack for this channel and requirement.",
                        headline=_safe_str(baseline_copy.get("metaHeadline")),
                        description=_safe_str(baseline_copy.get("metaDescription")),
                        cta="Not specified",
                        primary_text=_safe_str(baseline_copy.get("metaPrimaryText")),
                        emphasis="baseline",
                    ),
                    "</div>",
                    '<section class="prompt-story">',
                    "<h3>Prompt Storyline</h3>",
                    '<p class="section-note">These are the exact text stages used by the system, but presented in a readable order for review.</p>',
                    "".join(prompt_sections),
                    "</section>",
                    '<p class="appendix-link"><a href="technical-appendix.html#'
                    + html.escape(anchor)
                    + '">Open technical appendix for this creative</a></p>',
                    "</section>",
                ]
            )
        )

    copy_pack_cards: list[str] = []
    for artifact in ad_copy_pack_artifacts:
        for item in artifact.get("copyPackItems", []):
            pack = item.get("copyPack") or {}
            linked_assets = item.get("linkedAssetIds") or []
            copy_pack_cards.append(
                "\n".join(
                    [
                        '<section class="baseline-card">',
                        f"<p class=\"eyebrow\">{html.escape(_slug_label(_safe_str(pack.get('channel'))))} requirement pack</p>",
                        f"<h3>{html.escape(_safe_str(pack.get('metaHeadline')) or _safe_str(pack.get('id')))}</h3>",
                        f'<p class="baseline-meta">{_badge(_slug_label(_safe_str(pack.get("format"))), "info")} {_badge(f"linked creatives: {len(linked_assets)}", "neutral")}</p>',
                        f'<p><span class="field-label">Description</span>{html.escape(_safe_str(pack.get("metaDescription")) or "None")}</p>',
                        '<div class="copy-body">',
                        '<div class="field-label">Primary Text</div>',
                        f'<div class="body-text">{html.escape(_safe_str(pack.get("metaPrimaryText")) or "None")}</div>',
                        "</div>",
                        '<details class="guardrails"><summary>Publishing guardrails</summary>',
                        "<ul>"
                        + "".join(
                            f"<li>{html.escape(_safe_str(rule))}</li>"
                            for rule in (pack.get("claimsGuardrails") or [])
                        )
                        + "</ul></details>",
                        "</section>",
                    ]
                )
            )

    flagged_cards: list[str] = []
    for asset in missing_copy_assets + mismatched_copy_assets:
        headline = _display_headline(asset)
        source_label = _source_label(asset)
        status_label, status_kind, status_message = _status_meta(asset)
        generated_media = asset.get("generatedMedia") or {}
        flagged_cards.append(
            "\n".join(
                [
                    f'<a href="#asset-{html.escape(_safe_str(asset.get("assetId")))}" class="flag-card">',
                    (
                        f'<img src="{html.escape(_safe_str(generated_media.get("path")))}" alt="{html.escape(headline)}" loading="lazy" />'
                        if _safe_str(generated_media.get("path"))
                        else '<div class="gallery-placeholder">Image unavailable</div>'
                    ),
                    '<div class="flag-copy">',
                    f"<p>{_badge(status_label, status_kind)}</p>",
                    f"<h4>{html.escape(headline)}</h4>",
                    f"<p>{html.escape(source_label)}</p>",
                    f'<p class="flag-note">{html.escape(status_message)}</p>',
                    "</div>",
                    "</a>",
                ]
            )
        )

    warning_list = "".join(f"<li>{html.escape(_safe_str(item))}</li>" for item in warnings) or "<li>No warnings.</li>"

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Campaign Forensic Review</title>
  <style>
    :root {{
      --bg: #f7f4ee;
      --paper: #ffffff;
      --line: #dfd6c9;
      --text: #26211b;
      --muted: #73695d;
      --accent: #1463ff;
      --good: #1e8e5a;
      --warn: #b86b00;
      --danger: #b42318;
      --soft-blue: #eef4ff;
      --soft-green: #ebf8f1;
      --soft-orange: #fff4e7;
      --soft-red: #fff0ef;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(180deg, #faf7f1 0%, #f2ede3 100%);
      color: var(--text);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .layout {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      align-self: start;
      height: 100vh;
      overflow: auto;
      background: rgba(255,255,255,0.92);
      border-right: 1px solid var(--line);
      padding: 22px 18px;
      backdrop-filter: blur(10px);
    }}
    .sidebar h1 {{
      margin: 0 0 8px;
      font-size: 22px;
      line-height: 1.15;
    }}
    .sidebar p {{
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }}
    .summary-stack {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0;
    }}
    .controls {{
      margin: 18px 0;
      display: grid;
      gap: 10px;
    }}
    .controls input,
    .controls select {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fffdf9;
      color: var(--text);
      font-size: 14px;
    }}
    .sidebar-nav {{
      display: grid;
      gap: 8px;
    }}
    .sidebar-link {{
      display: block;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid transparent;
      background: #fffdf9;
    }}
    .sidebar-link:hover {{
      border-color: var(--line);
      text-decoration: none;
      background: white;
    }}
    .sidebar-link span,
    .sidebar-link small {{
      display: block;
      color: var(--muted);
      margin-top: 4px;
    }}
    main {{
      padding: 28px;
    }}
    .panel {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 22px;
      margin-bottom: 22px;
      box-shadow: 0 10px 26px rgba(70, 53, 32, 0.05);
    }}
    .hero h2 {{
      margin: 0 0 10px;
      font-size: 30px;
      line-height: 1.1;
    }}
    .hero p {{
      margin: 0 0 10px;
      font-size: 16px;
      line-height: 1.55;
      color: var(--muted);
      max-width: 900px;
    }}
    .badge {{
      display: inline-block;
      padding: 7px 11px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      line-height: 1;
      background: #fffdf9;
      color: var(--text);
      margin: 0 8px 8px 0;
    }}
    .badge-good {{ background: var(--soft-green); color: var(--good); border-color: rgba(30, 142, 90, 0.18); }}
    .badge-warn {{ background: var(--soft-orange); color: var(--warn); border-color: rgba(184, 107, 0, 0.18); }}
    .badge-danger {{ background: var(--soft-red); color: var(--danger); border-color: rgba(180, 35, 24, 0.18); }}
    .badge-info {{ background: var(--soft-blue); color: var(--accent); border-color: rgba(20, 99, 255, 0.18); }}
    .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }}
    .gallery-card,
    .flag-card {{
      display: block;
      background: white;
      border: 1px solid var(--line);
      border-radius: 20px;
      overflow: hidden;
      color: inherit;
      box-shadow: 0 8px 18px rgba(70, 53, 32, 0.04);
    }}
    .gallery-card:hover,
    .flag-card:hover {{
      text-decoration: none;
      transform: translateY(-1px);
      box-shadow: 0 12px 22px rgba(70, 53, 32, 0.08);
    }}
    .gallery-card img,
    .flag-card img {{
      display: block;
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      background: #f1ece3;
    }}
    .gallery-copy,
    .flag-copy {{
      padding: 14px;
    }}
    .gallery-copy h3,
    .flag-copy h4 {{
      margin: 8px 0 6px;
      font-size: 16px;
      line-height: 1.3;
    }}
    .gallery-copy p,
    .flag-copy p {{
      margin: 0 0 6px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .gallery-id {{
      font-size: 12px;
    }}
    .gallery-placeholder {{
      display: grid;
      place-items: center;
      min-height: 220px;
      background: #f1ece3;
      color: var(--muted);
    }}
    .baseline-grid,
    .flag-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .baseline-card {{
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px;
      background: #fffdfa;
    }}
    .baseline-card h3 {{
      margin: 0 0 10px;
      font-size: 20px;
      line-height: 1.25;
    }}
    .baseline-meta {{
      margin-bottom: 10px;
    }}
    .eyebrow {{
      margin: 0 0 8px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
      color: var(--muted);
    }}
    .field-label {{
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .copy-body {{
      margin-top: 12px;
      padding: 14px;
      border-radius: 16px;
      background: #faf6ef;
      border: 1px solid #ede3d5;
    }}
    .body-text {{
      white-space: pre-wrap;
      line-height: 1.6;
      color: var(--text);
    }}
    .guardrails ul {{
      margin: 10px 0 0 20px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .warning-list {{
      margin: 12px 0 0 20px;
      color: var(--muted);
      line-height: 1.55;
    }}
    .asset-section {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 10px 26px rgba(70, 53, 32, 0.05);
      scroll-margin-top: 24px;
    }}
    .asset-header {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      margin-bottom: 16px;
    }}
    .asset-header h2 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.15;
    }}
    .asset-meta,
    .asset-id {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .asset-id {{
      font-size: 12px;
      margin-top: 6px;
    }}
    .asset-callout {{
      padding: 14px 16px;
      border-radius: 18px;
      margin-bottom: 18px;
      line-height: 1.5;
      border: 1px solid transparent;
    }}
    .asset-callout-warn {{
      background: var(--soft-orange);
      border-color: rgba(184, 107, 0, 0.18);
      color: var(--warn);
    }}
    .asset-callout-danger {{
      background: var(--soft-red);
      border-color: rgba(180, 35, 24, 0.18);
      color: var(--danger);
    }}
    .visual-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}
    .visual-card {{
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 14px;
      background: #fffdfa;
    }}
    .visual-card h3 {{
      margin: 0 0 10px;
      font-size: 18px;
    }}
    .visual-card img {{
      width: 100%;
      display: block;
      border-radius: 16px;
      background: #f1ece3;
    }}
    .visual-caption {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }}
    .reference-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
    }}
    .reference-thumb {{
      margin: 0;
    }}
    .reference-thumb img {{
      border-radius: 14px;
      margin-bottom: 6px;
    }}
    .reference-thumb figcaption {{
      font-size: 12px;
      color: var(--muted);
      word-break: break-word;
    }}
    .copy-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}
    .copy-card {{
      border-radius: 20px;
      padding: 16px;
      border: 1px solid var(--line);
      background: #fffdfa;
    }}
    .copy-card-current {{ background: #f7fbff; }}
    .copy-card-swipe {{ background: #f6fff9; }}
    .copy-card-baseline {{ background: #fff9f4; }}
    .copy-card h4 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}
    .copy-subtitle {{
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .copy-card p {{
      margin: 0 0 10px;
      line-height: 1.45;
    }}
    .prompt-story {{
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 18px;
      background: #fffdfa;
    }}
    .prompt-story h3 {{
      margin: 0 0 8px;
      font-size: 22px;
    }}
    .section-note,
    .prompt-explainer {{
      color: var(--muted);
      line-height: 1.55;
    }}
    .prompt-panel {{
      border-top: 1px solid #ece2d6;
      padding-top: 12px;
      margin-top: 12px;
    }}
    .prompt-panel summary {{
      cursor: pointer;
      font-weight: 700;
      font-size: 16px;
    }}
    .prompt-text {{
      margin-top: 12px;
      padding: 14px;
      border-radius: 16px;
      background: #faf6ef;
      border: 1px solid #ede3d5;
      white-space: pre-wrap;
      line-height: 1.6;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 15px;
    }}
    .appendix-link {{
      margin-top: 16px;
      color: var(--muted);
    }}
    @media (max-width: 1200px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
    }}
    @media (max-width: 980px) {{
      .visual-grid,
      .copy-grid {{ grid-template-columns: 1fr; }}
      .asset-header {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h1>Campaign Forensic Review</h1>
      <p><strong>{html.escape(_safe_str(campaign.get("name")))}</strong></p>
      <p>Client: {html.escape(_safe_str(campaign.get("client_name")))}</p>
      <p>Product: {html.escape(_safe_str(campaign.get("product_name")))}</p>
      <div class="summary-stack">
        {_badge(f"Creatives: {len(assets)}", "info")}
        {_badge(f"Campaign copy attached: {len(assets) - len(missing_copy_assets)}", "good")}
        {_badge(f"Missing campaign copy: {len(missing_copy_assets)}", "warn" if missing_copy_assets else "good")}
        {_badge(f"Copy mismatches: {len(mismatched_copy_assets)}", "danger" if mismatched_copy_assets else "good")}
      </div>
      <p>Main view: marketer-friendly. Technical details live in <a href="technical-appendix.html">technical appendix</a>.</p>
      <div class="controls">
        <input id="asset-search" type="search" placeholder="Search by headline, source swipe, or ID" />
        <select id="channel-filter">
          <option value="">All channels</option>
          <option value="facebook">Facebook</option>
          <option value="instagram">Instagram</option>
        </select>
        <select id="status-filter">
          <option value="">All statuses</option>
          <option value="good">Campaign copy matches</option>
          <option value="warn">No campaign copy attached</option>
          <option value="danger">Campaign copy differs</option>
        </select>
      </div>
      <nav class="sidebar-nav" id="sidebar-nav">
        {''.join(sidebar_links)}
      </nav>
    </aside>

    <main>
      <section class="panel hero">
        <p class="eyebrow">Human-readable review</p>
        <h2>What happened in this campaign</h2>
        <p>This view is organized for a marketer, not an engineer. Each creative shows the final generated ad, the source swipe that influenced it, any product reference image, the copy currently pasted into the campaign, the swipe-specific copy the system generated for that creative, the original requirement-level copy pack, and the readable prompt chain that produced the image.</p>
        <p>If you want the raw metadata, IDs, and JSON-heavy technical view, use <a href="technical-appendix.html">technical appendix</a> or <a href="bundle.json">bundle.json</a>.</p>
      </section>

      <section class="panel">
        <p class="eyebrow">Baseline copy packs</p>
        <h2>Requirement-Level Copy Packs</h2>
        <div class="baseline-grid">
          {''.join(copy_pack_cards)}
        </div>
      </section>

      <section class="panel">
        <p class="eyebrow">Needs attention</p>
        <h2>Flagged Creatives</h2>
        <p>These are the creatives where the current campaign copy is missing or differs from the swipe-generated copy.</p>
        <div class="flag-grid">
          {''.join(flagged_cards) or '<p>Nothing is flagged.</p>'}
        </div>
      </section>

      <section class="panel">
        <p class="eyebrow">Quick browse</p>
        <h2>Creative Gallery</h2>
        <div class="gallery-grid" id="gallery-grid">
          {''.join(gallery_cards)}
        </div>
      </section>

      <section class="panel">
        <p class="eyebrow">Warnings</p>
        <h2>Export Notes</h2>
        <ul class="warning-list">{warning_list}</ul>
      </section>

      {''.join(detail_sections)}
    </main>
  </div>

  <script>
    const searchInput = document.getElementById('asset-search');
    const channelFilter = document.getElementById('channel-filter');
    const statusFilter = document.getElementById('status-filter');
    const filterTargets = Array.from(document.querySelectorAll('[data-search]'));

    function applyFilters() {{
      const query = (searchInput.value || '').trim().toLowerCase();
      const channel = (channelFilter.value || '').trim().toLowerCase();
      const status = (statusFilter.value || '').trim().toLowerCase();

      filterTargets.forEach((element) => {{
        const haystack = (element.dataset.search || '').toLowerCase();
        const matchesQuery = !query || haystack.includes(query);
        const matchesChannel = !channel || (element.dataset.channel || '') === channel;
        const matchesStatus = !status || (element.dataset.status || '') === status;
        element.style.display = matchesQuery && matchesChannel && matchesStatus ? '' : 'none';
      }});
    }}

    searchInput.addEventListener('input', applyFilters);
    channelFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""

    index_path = export_dir / "index.html"
    index_path.write_text(html_doc, encoding="utf-8")
    return index_path, technical_target


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a marketer-friendly forensic index from an existing campaign forensic bundle.")
    parser.add_argument("export_dir", help="Path to the campaign forensic export directory.")
    args = parser.parse_args()

    export_dir = Path(args.export_dir).expanduser().resolve()
    index_path, appendix_path = render_marketer_view(export_dir)
    print(f"index={index_path}")
    print(f"appendix={appendix_path}")


if __name__ == "__main__":
    main()
