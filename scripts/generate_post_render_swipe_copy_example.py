#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "mos" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.temporal.activities.swipe_image_ad_activities import (  # noqa: E402
    _generate_rendered_asset_swipe_copy_pack,
)


def _workflow_default_model() -> str:
    model = (
        os.getenv("SWIPE_PROMPT_MODEL")
        or os.getenv("GEMINI_FILE_SEARCH_MODEL")
        or settings.GEMINI_FILE_SEARCH_MODEL
    )
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError(
            "Could not resolve the swipe prompt model from SWIPE_PROMPT_MODEL, "
            "GEMINI_FILE_SEARCH_MODEL, or settings.GEMINI_FILE_SEARCH_MODEL."
        )
    return model.strip()


def _load_bundle(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")
    return json.loads(bundle_path.read_text())


def _find_asset(bundle: dict[str, Any], asset_id: str) -> dict[str, Any]:
    assets = bundle.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("Bundle is missing the assets list.")
    for asset in assets:
        if isinstance(asset, dict) and asset.get("assetId") == asset_id:
            return asset
    raise RuntimeError(f"Asset not found in bundle: {asset_id}")


def _require_dict(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object.")
    return value


def _read_bytes(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_bytes()


def _resolve_source_swipe_path(bundle_root: Path, asset: dict[str, Any]) -> Path | None:
    swipe_source = asset.get("swipeSource")
    if not isinstance(swipe_source, dict):
        return None
    download = swipe_source.get("download")
    if not isinstance(download, dict):
        return None
    relative_path = download.get("path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    return bundle_root / relative_path


def _resolve_product_reference(bundle_root: Path, asset: dict[str, Any]) -> tuple[bytes | None, str | None, Path | None]:
    product_media = asset.get("productReferenceMedia")
    if not isinstance(product_media, list) or not product_media:
        return None, None, None
    first = product_media[0]
    if not isinstance(first, dict):
        return None, None, None
    relative_path = first.get("path")
    mime_type = first.get("contentType")
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None, None, None
    resolved_path = bundle_root / relative_path
    return _read_bytes(resolved_path), mime_type if isinstance(mime_type, str) else None, resolved_path


def _extract_rendered_headline(raw_ai_metadata: dict[str, Any]) -> str | None:
    prompt_used = raw_ai_metadata.get("promptUsed")
    if not isinstance(prompt_used, str):
        return None
    marker = 'Bottom Dark Zone (Headline):'
    if marker not in prompt_used:
        return None
    snippet = prompt_used.split(marker, 1)[1].strip().splitlines()[0].strip()
    return snippet or None


def _build_brief(bundle: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    brief = dict(_require_dict(asset.get("brief"), label="asset.brief"))
    campaign = _require_dict(bundle.get("campaign"), label="bundle.campaign")
    brief.setdefault("id", asset.get("briefId"))
    brief.setdefault("campaignId", campaign.get("id"))
    brief.setdefault("variantId", asset.get("variantId"))
    return brief


def _keyword_hits(text: str | None, *keywords: str) -> list[str]:
    haystack = (text or "").lower()
    return [keyword for keyword in keywords if keyword.lower() in haystack]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    source_swipe_path = payload.get("sourceSwipeImage")
    rendered_image_path = payload.get("renderedAdImage")
    old_pack = payload.get("previousSwipeCopyPack") or {}
    new_pack = payload.get("newPostRenderSwipeCopyPack") or {}
    rendered_headline = payload.get("renderedAdHeadline")
    old_hits = payload.get("previousKeywordHits") or []
    new_hits = payload.get("newKeywordHits") or []

    lines = [
        f"# Post-Render Swipe Copy Example: {payload['assetId']}",
        "",
        f"- Generated at: {payload['generatedAtUtc']}",
        f"- Model: `{payload['modelUsed']}`",
        f"- Bundle: `{payload['bundlePath']}`",
        f"- Rendered ad image: `{rendered_image_path}`",
        f"- Source swipe image: `{source_swipe_path}`" if source_swipe_path else "- Source swipe image: unavailable",
        "",
        "## What Was Broken Before",
        "",
        f"- Previous Meta headline: {old_pack.get('metaHeadline')}",
        "",
        "### Previous Meta primary text",
        "",
        old_pack.get("metaPrimaryText") or "[missing]",
        "",
        f"- Previous keyword hits: {', '.join(old_hits) if old_hits else 'none'}",
        "",
        "## Rendered Ad Context",
        "",
        f"- Rendered ad headline from prompt/render context: {rendered_headline or '[unavailable]'}",
        "",
        "## New Post-Render Output",
        "",
        f"- New Meta headline: {new_pack.get('metaHeadline')}",
        "",
        "### New Meta primary text",
        "",
        new_pack.get("metaPrimaryText") or "[missing]",
        "",
        f"- New keyword hits: {', '.join(new_hits) if new_hits else 'none'}",
        "",
        "### New claims guardrails",
        "",
    ]
    for guardrail in new_pack.get("claimsGuardrails") or []:
        lines.append(f"- {guardrail}")
    lines.extend(
        [
            "",
            "## Images",
            "",
        ]
    )
    if rendered_image_path:
        lines.extend(
            [
                "### Rendered Ad",
                "",
                f"![Rendered ad]({rendered_image_path})",
                "",
            ]
        )
    if source_swipe_path:
        lines.extend(
            [
                "### Source Swipe",
                "",
                f"![Source swipe]({source_swipe_path})",
                "",
            ]
        )
    lines.extend(
        [
            "## Prompt",
            "",
            "```text",
            payload.get("promptText") or "",
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a post-render swipeCopyPack example from a forensic export bundle."
    )
    parser.add_argument("--bundle-path", required=True, help="Absolute path to the forensic bundle.json file.")
    parser.add_argument("--asset-id", required=True, help="Generated asset id to replay.")
    parser.add_argument(
        "--output-dir",
        help="Directory for generated review files. Defaults to <bundle_dir>/post-render-swipe-copy-examples.",
    )
    parser.add_argument(
        "--model",
        help="Override the swipe prompt model. Defaults to the same model resolution order as the workflow.",
    )
    args = parser.parse_args()

    bundle_path = Path(args.bundle_path).resolve()
    bundle_root = bundle_path.parent
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else bundle_root / "post-render-swipe-copy-examples"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    bundle = _load_bundle(bundle_path)
    asset = _find_asset(bundle, args.asset_id)
    brief = _build_brief(bundle, asset)
    requirement = _require_dict(asset.get("briefRequirement"), label="asset.briefRequirement")
    linked_copy_pack = _require_dict(
        _require_dict(asset.get("linkedAdCopyPack"), label="asset.linkedAdCopyPack").get("copyPack"),
        label="asset.linkedAdCopyPack.copyPack",
    )
    generated_media = _require_dict(asset.get("generatedMedia"), label="asset.generatedMedia")
    rendered_relative_path = generated_media.get("path")
    if not isinstance(rendered_relative_path, str) or not rendered_relative_path.strip():
        raise RuntimeError("asset.generatedMedia.path must be a non-empty string.")
    rendered_path = (bundle_root / rendered_relative_path).resolve()
    rendered_bytes = _read_bytes(rendered_path)
    rendered_mime_type = generated_media.get("contentType")
    if not isinstance(rendered_mime_type, str) or not rendered_mime_type.strip():
        raise RuntimeError("asset.generatedMedia.contentType must be a non-empty string.")

    product_bytes, product_mime_type, product_path = _resolve_product_reference(bundle_root, asset)
    source_swipe_path = _resolve_source_swipe_path(bundle_root, asset)
    model_name = args.model.strip() if isinstance(args.model, str) and args.model.strip() else _workflow_default_model()
    requirement_index = asset.get("requirementIndex")
    if not isinstance(requirement_index, int):
        raise RuntimeError("asset.requirementIndex must be an integer.")

    new_copy_pack, response, used_model, prompt_text = _generate_rendered_asset_swipe_copy_pack(
        session=None,
        brief=brief,
        requirement_index=requirement_index,
        requirement=requirement,
        copy_model=model_name,
        gemini_store_names=list(asset.get("geminiStoreNames") or []),
        rendered_ad_bytes=rendered_bytes,
        rendered_ad_mime_type=rendered_mime_type,
        rendered_ad_source_url=str(rendered_path),
        rendered_ad_source_label=rendered_path.name,
        linked_ad_copy_pack=linked_copy_pack,
        product_prompt_image_bytes=product_bytes,
        product_prompt_image_mime_type=product_mime_type,
    )

    old_copy_pack = _require_dict(asset.get("swipeCopyPack"), label="asset.swipeCopyPack")
    raw_ai_metadata = _require_dict(asset.get("rawAiMetadata"), label="asset.rawAiMetadata")
    rendered_ad_headline = _extract_rendered_headline(raw_ai_metadata)

    payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "assetId": args.asset_id,
        "bundlePath": str(bundle_path),
        "modelRequested": model_name,
        "modelUsed": used_model,
        "renderedAdImage": str(rendered_path),
        "renderedAdHeadline": rendered_ad_headline,
        "sourceSwipeImage": str(source_swipe_path) if source_swipe_path else None,
        "productReferenceImage": str(product_path) if product_path else None,
        "geminiStoreNames": list(asset.get("geminiStoreNames") or []),
        "linkedAdCopyPack": linked_copy_pack,
        "previousSwipeCopyPack": old_copy_pack,
        "newPostRenderSwipeCopyPack": new_copy_pack.model_dump(mode="json", by_alias=True, exclude_none=False),
        "promptText": prompt_text,
        "rawResponseText": response.get("text"),
        "stopReason": response.get("stop_reason"),
        "outputTokens": response.get("output_tokens"),
        "previousKeywordHits": _keyword_hits(
            f"{old_copy_pack.get('metaHeadline', '')}\n{old_copy_pack.get('metaPrimaryText', '')}",
            "hashimoto",
            "weight loss",
            "prescription",
            "herb",
            "drug",
            "checker",
        ),
        "newKeywordHits": _keyword_hits(
            f"{new_copy_pack.meta_headline or ''}\n{new_copy_pack.meta_primary_text or ''}",
            "hashimoto",
            "weight loss",
            "prescription",
            "herb",
            "drug",
            "checker",
        ),
    }

    json_path = output_dir / f"{args.asset_id}-post-render-swipe-copy.json"
    md_path = output_dir / f"{args.asset_id}-post-render-swipe-copy.md"
    _write_json(json_path, payload)
    _write_markdown(md_path, payload)

    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
