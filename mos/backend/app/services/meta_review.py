from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository


_DESTINATION_TOKEN_RE = re.compile(r"[^a-z0-9]+")
_DESTINATION_ALIASES = {
    "presales": "pre-sales",
    "pre-sales": "pre-sales",
    "pre-sale": "pre-sales",
    "presale": "pre-sales",
    "presales-page": "pre-sales",
    "pre-sales-page": "pre-sales",
    "pre-sale-page": "pre-sales",
    "presales-listicle": "pre-sales",
    "pre-sales-listicle": "pre-sales",
    "pre-sale-listicle": "pre-sales",
    "presales-listicle-page": "pre-sales",
    "pre-sales-listicle-page": "pre-sales",
    "listicle": "pre-sales",
    "sales": "sales",
    "sales-page": "sales",
    "sales-pdp": "sales",
    "pdp": "sales",
    "product-page": "sales",
    "product-detail-page": "sales",
}


def clean_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def load_campaign_asset_brief_map(
    *,
    org_id: str,
    client_id: str,
    campaign_id: str,
    session: Session,
) -> dict[str, dict]:
    artifacts_repo = ArtifactsRepository(session)
    brief_artifacts = artifacts_repo.list(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.asset_brief,
        limit=200,
    )
    brief_map: dict[str, dict] = {}
    for artifact in brief_artifacts:
        data = artifact.data if isinstance(artifact.data, dict) else {}
        briefs = data.get("asset_briefs") or data.get("assetBriefs") or []
        if not isinstance(briefs, list):
            continue
        for brief in briefs:
            if not isinstance(brief, dict):
                continue
            brief_id = clean_optional_text(brief.get("id"))
            if brief_id and brief_id not in brief_map:
                brief_map[brief_id] = brief
    return brief_map


def brief_funnel_id(brief: Any) -> str | None:
    if not isinstance(brief, dict):
        return None
    return clean_optional_text(brief.get("funnelId"))


def asset_brief_id(asset: Any) -> str | None:
    metadata_json = asset.ai_metadata if isinstance(getattr(asset, "ai_metadata", None), dict) else {}
    return clean_optional_text(metadata_json.get("assetBriefId"))


def asset_funnel_id_from_briefs(
    asset: Any,
    *,
    brief_map: dict[str, dict],
) -> str | None:
    brief_id = asset_brief_id(asset)
    if not brief_id:
        return None
    return brief_funnel_id(brief_map.get(brief_id))


def filter_assets_for_funnel_scope(
    assets: Iterable[Any],
    *,
    brief_map: dict[str, dict],
    funnel_id: str,
) -> list[Any]:
    cleaned_funnel_id = clean_optional_text(funnel_id)
    if not cleaned_funnel_id:
        return []
    return [
        asset
        for asset in assets
        if asset_funnel_id_from_briefs(asset, brief_map=brief_map) == cleaned_funnel_id
    ]


def collect_brief_funnel_ids(
    *,
    brief_map: dict[str, dict],
    brief_ids: Iterable[str],
) -> set[str]:
    return {
        funnel_id
        for funnel_id in (brief_funnel_id(brief_map.get(brief_id)) for brief_id in brief_ids)
        if funnel_id
    }


def collect_asset_funnel_ids(
    *,
    assets: Iterable[Any],
    brief_map: dict[str, dict],
) -> set[str]:
    return {
        funnel_id
        for funnel_id in (asset_funnel_id_from_briefs(asset, brief_map=brief_map) for asset in assets)
        if funnel_id
    }


def asset_generation_key(asset: Any) -> str:
    metadata_json = asset.ai_metadata if isinstance(getattr(asset, "ai_metadata", None), dict) else {}
    batch_id = clean_optional_text(metadata_json.get("creativeGenerationBatchId"))
    if batch_id:
        return f"batch:{batch_id}"

    remote_job_id = clean_optional_text(metadata_json.get("remoteJobId"))
    if remote_job_id:
        return f"remoteJob:{remote_job_id}"

    return f"asset:{asset.id}"


def select_assets_for_generation(
    assets: list[Any],
    *,
    generation_key: str | None = None,
    generation_batch_id: str | None = None,
) -> tuple[str | None, list[Any]]:
    if generation_batch_id:
        generation_key = f"batch:{generation_batch_id.strip()}"

    if generation_key:
        selected_assets = [asset for asset in assets if asset_generation_key(asset) == generation_key]
        selected_assets.sort(key=lambda asset: getattr(asset, "created_at", None) or 0)
        return generation_key, selected_assets

    latest_group_assets: dict[str, list[Any]] = {}
    latest_group_timestamps: dict[str, object] = {}

    for asset in assets:
        group_key = asset_generation_key(asset)
        latest_group_assets.setdefault(group_key, []).append(asset)
        created_at = getattr(asset, "created_at", None)
        current_latest = latest_group_timestamps.get(group_key)
        if current_latest is None or (created_at is not None and created_at > current_latest):
            latest_group_timestamps[group_key] = created_at

    if not latest_group_assets:
        return None, []

    selected_group_key = max(
        latest_group_assets.keys(),
        key=lambda key: latest_group_timestamps.get(key) or 0,
    )
    selected_assets = latest_group_assets[selected_group_key]
    selected_assets.sort(key=lambda asset: getattr(asset, "created_at", None) or 0)
    return selected_group_key, selected_assets


def _normalize_destination_token(value: str) -> str:
    lowered = value.strip().lower()
    collapsed = _DESTINATION_TOKEN_RE.sub("-", lowered).strip("-")
    return collapsed


def destination_page_candidates(value: str | None) -> list[str]:
    cleaned = clean_optional_text(value)
    if not cleaned:
        return []
    normalized = _normalize_destination_token(cleaned)
    if not normalized:
        return [cleaned]

    candidates: list[str] = []
    for candidate in (
        cleaned,
        normalized,
        normalized.replace("-", ""),
        _DESTINATION_ALIASES.get(normalized),
    ):
        if not isinstance(candidate, str):
            continue
        stripped = candidate.strip()
        if stripped and stripped not in candidates:
            candidates.append(stripped)
    return candidates


def resolve_meta_review_destination_url(
    *,
    destination_page: str,
    review_paths: dict[str, str],
) -> str | None:
    cleaned = clean_optional_text(destination_page)
    if not cleaned:
        return None
    if cleaned.startswith("/") or cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned

    normalized_review_paths: dict[str, str] = {}
    for key, value in review_paths.items():
        key_cleaned = clean_optional_text(key)
        value_cleaned = clean_optional_text(value)
        if not key_cleaned or not value_cleaned:
            continue
        for candidate in destination_page_candidates(key_cleaned):
            normalized_review_paths.setdefault(candidate, value_cleaned)

    for candidate in destination_page_candidates(cleaned):
        resolved = normalized_review_paths.get(candidate)
        if resolved:
            return resolved
    return None


def normalize_meta_review_destination_page(
    destination_page: str | None,
    *,
    review_paths: dict[str, str],
) -> str | None:
    candidates = destination_page_candidates(destination_page)
    if not candidates:
        return None

    for candidate in candidates:
        if candidate in review_paths:
            return candidate

    normalized_review_keys: dict[str, str] = {}
    for key in review_paths.keys():
        key_cleaned = clean_optional_text(key)
        if not key_cleaned:
            continue
        for candidate in destination_page_candidates(key_cleaned):
            normalized_review_keys.setdefault(candidate, key_cleaned)

    for candidate in candidates:
        resolved_key = normalized_review_keys.get(candidate)
        if resolved_key:
            return resolved_key
    return clean_optional_text(destination_page)
