#!/usr/bin/env python3
"""Turn the raw Ember asset inventory JSON into a browsable markdown catalog.

Input:  .local/ember-asset-inventory.json (from ember_asset_inventory.py)
Output: .local/ember-asset-catalog.md  — grouped, scannable catalog

Groups:
  1. Funnel page images (hero, section imagery)
  2. Facebook ad creatives (swipe cards, testimonial cards)
  3. Product-level imagery (PDP gallery, lifestyle)
  4. Brand-level assets (logo, color mark)
  5. Special callout buckets surfaced from tag inspection
     (founder, hero, testimonial, comparison, ingredients, etc.)

Each row shows public URL, dimensions, status, source, tags, and the prompt
preview when AI-generated.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

IN = Path("/Users/auggieclement/Downloads/mos_strategy/.local/ember-asset-inventory.json")
OUT = Path("/Users/auggieclement/Downloads/mos_strategy/.local/ember-asset-catalog.md")


def pub_url(a: dict) -> str:
    pid = a.get("public_id") or ""
    return f"https://api.moshq.app/public/assets/{pid}" if pid else ""


def row_line(a: dict) -> str:
    pid = a.get("public_id") or ""
    url = pub_url(a)
    w, h = a.get("width") or "?", a.get("height") or "?"
    status = a.get("status") or ""
    src = a.get("file_source") or ""
    tags = ",".join(a.get("tags") or []) or "-"
    content = a.get("content") or {}
    prompt = (content.get("prompt") or "")[:80].replace("\n", " ").replace("|", "/")
    prompt_cell = f"{prompt}…" if prompt else "-"
    # Markdown table row
    return (
        f"| `{pid[:8]}` | [{w}×{h}]({url}) | {status} | {src} | {tags} | {prompt_cell} |"
    )


def section(title: str, assets: list, preamble: str = "") -> str:
    lines: list[str] = []
    lines.append(f"\n## {title}  _({len(assets)})_\n")
    if preamble:
        lines.append(preamble + "\n")
    if not assets:
        lines.append("_(none)_\n")
        return "\n".join(lines)
    lines.append("| id | size | status | src | tags | prompt preview |")
    lines.append("|---|---|---|---|---|---|")
    # Sort: approved first, then newest first
    assets.sort(
        key=lambda a: (
            0 if a.get("status") == "approved" else 1,
            -(int((a.get("created_at") or "0").replace("-", "").replace(":", "").replace("T", "").replace("+", "").split(".")[0] or 0)),
        )
    )
    for a in assets:
        lines.append(row_line(a))
    return "\n".join(lines)


def tag_bucket(assets: list, tag: str) -> list:
    return [a for a in assets if tag in (a.get("tags") or [])]


def main() -> int:
    data = json.loads(IN.read_text())
    assets: list[dict[str, Any]] = data["assets"]
    client = data.get("client") or {}
    products = data.get("products") or []

    # index by channel
    by_channel: dict[str, list] = defaultdict(list)
    for a in assets:
        by_channel[a.get("channel_id") or "<none>"].append(a)

    # summary counters
    total = len(assets)
    approved = sum(1 for a in assets if a.get("status") == "approved")
    draft = sum(1 for a in assets if a.get("status") == "draft")

    lines: list[str] = []
    lines.append(f"# Ember Asset Inventory\n")
    lines.append(
        f"- **Client**: {client.get('name')} (`{client.get('id')}`)\n"
        f"- **Org**: `{client.get('org_id')}`\n"
        f"- **Products**: "
        + ", ".join(f"`{p.get('id')}`" for p in products)
        + "\n"
        f"- **Total assets**: {total}  (approved: {approved}, draft: {draft})\n"
        f"- **Public URL pattern**: `https://api.moshq.app/public/assets/<public_id>`\n"
    )

    # Top-level channel buckets
    lines.append("\n## Counts by channel\n")
    lines.append("| channel | count |")
    lines.append("|---|---|")
    for ch, rows in sorted(by_channel.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {ch} | {len(rows)} |")

    # Broad channel sections
    lines.append(section("Brand-level assets (channel=brand)", by_channel.get("brand", []),
                         "Logo and top-level brand imagery. Use for headers, footers, etc."))
    lines.append(section("Product-level imagery (channel=product)", by_channel.get("product", []),
                         "PDP gallery, lifestyle/flat-lay. Suited for product blocks, hero slots."))
    lines.append(section("Facebook ad creatives (channel=facebook)", by_channel.get("facebook", []),
                         "Swipe cards, testimonial cards, comment threads. Ad format — avoid using in editorial/founder slots."))

    # Funnel channel — subdivide by tag
    funnel_assets = by_channel.get("funnel", [])
    lines.append(f"\n## Funnel-scope images (channel=funnel)  _({len(funnel_assets)})_\n")
    lines.append(
        "_Sub-grouped by dominant tag. An asset may appear under more than one tag, but the main-tag buckets below are mutually exclusive in priority order._\n"
    )

    priority_tags = [
        "hero",
        "testimonial",
        "review_card",
        "social_comment",
        "social_comment_instagram",
        "pdp_ugc_standard",
        "pdp_bold_claim",
        "pdp_personal_highlight",
        "personal_highlight",
        "bold_claim",
        "dorm_selfie",
        "sales_pdp_carousel",
        "avatar",
        "reply_avatar",
        "component_image",
        "funnel_page_image",
        "ai_attachment",
        "ai_generated",
        "shopify_theme_sync",
        "attachment",
        "template",
        "unsplash",
    ]
    seen_ids: set[str] = set()
    for tag in priority_tags:
        bucket = [a for a in funnel_assets if tag in (a.get("tags") or []) and a["id"] not in seen_ids]
        if not bucket:
            continue
        for a in bucket:
            seen_ids.add(a["id"])
        lines.append(section(f"Funnel · `{tag}`", bucket))

    # Remaining funnel assets not caught by a tag
    leftover = [a for a in funnel_assets if a["id"] not in seen_ids]
    if leftover:
        lines.append(section("Funnel · _other_", leftover))

    # Special callouts — likely founder/authority candidates by prompt keyword
    founder_candidates = []
    for a in assets:
        content = a.get("content") or {}
        prompt = (content.get("prompt") or "").lower()
        if any(
            word in prompt
            for word in (
                "neuroendocrinologist",
                "dr. langford",
                "dr langford",
                "catherine langford",
                "founder",
                "doctor portrait",
                "neurologist",
                "clinical researcher",
            )
        ):
            founder_candidates.append(a)
    lines.append(
        section(
            "🔎 Founder / authority candidates (prompt keyword search)",
            founder_candidates,
            "_These are assets whose AI-generation prompt mentions founder/doctor/neuroendocrinologist. Manually verify each before swapping into the founder slot._",
        )
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  {total} assets ({approved} approved, {draft} draft)")
    print(f"  founder candidates flagged: {len(founder_candidates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
