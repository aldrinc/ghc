from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image
from sqlalchemy import select
from temporalio import activity

from app.config import settings
from app.db.base import session_scope
from app.db.enums import ArtifactTypeEnum, AssetSourceEnum, AssetStatusEnum
from app.db.models import (
    CreativeServiceEvent,
    CreativeServiceOutput,
    CreativeServiceRun,
    CreativeServiceTurn,
    Funnel,
)
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.assets import AssetsRepository
from app.db.repositories.claude_context_files import ClaudeContextFilesRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.swipes import CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.creative_generation import (
    AdCopyPackArtifact,
    AdCopyPackStructuredOutput,
    CreativeGenerationPlanArtifact,
    CreativeGenerationPlanItem,
)
from app.schemas.creative_service import CreativeServiceVideoAttachmentIn
from app.services.claude_files import (
    CLAUDE_DEFAULT_MODEL,
    build_document_blocks,
    call_claude_structured_message,
    ensure_uploaded_to_claude,
)
from app.services.creative_service_client import (
    CreativeServiceClient,
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.design_systems import resolve_design_system_tokens
from app.services.gemini_file_search import ensure_uploaded_to_gemini_file_search, is_gemini_file_search_enabled
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage
from app.services.video_ads_orchestrator import (
    VideoAdsOrchestrator,
    VideoOrchestrationError,
    VideoTurnTrace,
    build_initial_video_message,
)

_IMAGE_TERMINAL_STATUSES = {"succeeded", "failed"}
_SUPPORTED_FORMATS = {"image", "video"}
_DEFAULT_SWIPE_SOURCE_SET_KEY = "default_initial_swipes_v1"
_AD_COPY_PACK_SCHEMA_VERSION = 2
_DEFAULT_SWIPE_SOURCE_LABELS = [
    "10.png",
    "11.png",
    "12.png",
    "5.png",
    "6.png",
    "7.png",
    "8.png",
    "9.png",
    "_initial_swipe_contact_sheet.jpg",
    "big_text.jpg",
    "boss_babe.jpg",
    "brush.jpg",
    "care_bag.jpg",
    "derm_fag.jpg",
    "drawing.jpg",
    "fatigue.jpg",
    "fb_message_ad.jpg",
    "green.jpg",
    "grocery.jpg",
    "health_cute_advertorial.jpg",
    "old_school.jpg",
    "raise_a_winner.jpg",
    "researchers.jpg",
    "spanish_doctor_cta.jpg",
    "Static #1.png",
    "Static #2.png",
    "Static #3.png",
    "Static #4.png",
    "target_1.jpg",
    "women_health.jpg",
]
_AD_COPY_PACK_DOC_KEY_PREFIX = "ad_copy_pack"
_AD_COPY_PACK_OUTPUT_SCHEMA = AdCopyPackStructuredOutput.model_json_schema(by_alias=True)


@dataclass(frozen=True)
class _ProductReferenceAsset:
    local_asset_id: str
    primary_url: str
    title: str | None
    remote_asset_id: str | None


@dataclass(frozen=True)
class _SwipeCandidate:
    company_swipe_id: str
    swipe_requires_product_image: bool | None


@dataclass(frozen=True)
class _DefaultSwipeSource:
    company_swipe_id: str
    source_label: str
    source_media_url: str
    product_image_policy: bool | None


def _normalize_requirement_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"image", "image_ad", "image-ad"}:
        return "image"
    if normalized in {"video", "video_ad", "video-ad"}:
        return "video"
    return normalized


def _extract_requirement_swipe_source(requirement: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Resolve an optional explicit swipe source from a requirement payload.

    Supported keys:
    - companySwipeId / company_swipe_id
    - swipeImageUrl / swipe_image_url
    """
    company_swipe_id = requirement.get("companySwipeId")
    if not isinstance(company_swipe_id, str) or not company_swipe_id.strip():
        company_swipe_id = requirement.get("company_swipe_id")
    if isinstance(company_swipe_id, str):
        company_swipe_id = company_swipe_id.strip() or None
    else:
        company_swipe_id = None

    swipe_image_url = requirement.get("swipeImageUrl")
    if not isinstance(swipe_image_url, str) or not swipe_image_url.strip():
        swipe_image_url = requirement.get("swipe_image_url")
    if isinstance(swipe_image_url, str):
        swipe_image_url = swipe_image_url.strip() or None
    else:
        swipe_image_url = None

    if company_swipe_id and swipe_image_url:
        raise ValueError(
            "Asset brief requirement must provide exactly one swipe source when explicit swipe keys are set "
            "(companySwipeId/company_swipe_id OR swipeImageUrl/swipe_image_url)."
        )
    return company_swipe_id, swipe_image_url


def _extract_requirement_swipe_requires_product_image(requirement: dict[str, Any]) -> bool | None:
    raw = requirement.get("swipeRequiresProductImage")
    if raw is None:
        raw = requirement.get("swipe_requires_product_image")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    raise ValueError(
        "Asset brief requirement swipeRequiresProductImage/swipe_requires_product_image "
        "must be a boolean when provided."
    )


def _extract_swipe_requires_product_image_from_tags(tags: list[str] | None) -> bool | None:
    normalized_tags = {
        tag.strip().lower()
        for tag in (tags or [])
        if isinstance(tag, str) and tag.strip()
    }
    requires_tag = "swipe:requires_product_image"
    no_product_tag = "swipe:no_product_image"

    has_requires_tag = requires_tag in normalized_tags
    has_no_product_tag = no_product_tag in normalized_tags
    if has_requires_tag and has_no_product_tag:
        raise ValueError(
            "Client swipe tags contain conflicting product image policy tags: "
            "`swipe:requires_product_image` and `swipe:no_product_image`."
        )
    if has_requires_tag:
        return True
    if has_no_product_tag:
        return False
    return None


def _repo(session) -> AssetsRepository:
    return AssetsRepository(session)


def _stable_idempotency_key(*parts: str) -> str:
    payload = "|".join(parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:48]


def _resolve_creative_generation_execution_key(*, workflow_run_id: str | None) -> str:
    if isinstance(workflow_run_id, str) and workflow_run_id.strip():
        return workflow_run_id.strip()

    try:
        info = activity.info()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Creative generation checkpointing requires workflow_run_id or Temporal activity context."
        ) from exc

    workflow_id = str(getattr(info, "workflow_id", "") or "").strip()
    run_id = str(getattr(info, "run_id", "") or "").strip()
    if workflow_id and run_id:
        return f"{workflow_id}:{run_id}"
    if workflow_id:
        return workflow_id

    raise RuntimeError(
        "Creative generation checkpointing requires workflow_run_id or Temporal activity context."
    )


def _build_creative_generation_batch_id(*, execution_key: str, asset_brief_id: str) -> str:
    return _stable_idempotency_key(
        "creative_generation_batch_v1",
        execution_key,
        asset_brief_id,
    )


def _summarize_exception_message(exc: BaseException, *, max_chars: int = 400) -> str:
    prefix = type(exc).__name__
    message = " ".join(str(exc).split())
    if not message:
        return prefix
    summary = message if message.startswith(f"{prefix}:") else f"{prefix}: {message}"
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."


def _existing_creative_generation_assets_by_plan_item(
    *,
    assets: Sequence[Any],
    batch_id: str,
    asset_brief_id: str,
) -> dict[str, str]:
    completed_assets: dict[str, str] = {}
    for asset in assets:
        metadata = getattr(asset, "ai_metadata", None)
        if not isinstance(metadata, dict):
            continue
        candidate_batch_id = str(metadata.get("creativeGenerationBatchId") or "").strip()
        if candidate_batch_id != batch_id:
            continue

        candidate_brief_id = str(metadata.get("assetBriefId") or "").strip()
        if not candidate_brief_id:
            content = getattr(asset, "content", None)
            if isinstance(content, dict):
                candidate_brief_id = str(content.get("assetBriefId") or "").strip()
        if candidate_brief_id != asset_brief_id:
            continue

        plan_item_id = str(metadata.get("creativeGenerationPlanItemId") or "").strip()
        if not plan_item_id:
            continue

        asset_id = str(getattr(asset, "id", "") or "").strip()
        if not asset_id:
            raise RuntimeError(
                "Creative generation checkpoint encountered an asset without an id "
                f"(batch_id={batch_id}, plan_item_id={plan_item_id})."
            )

        existing_asset_id = completed_assets.get(plan_item_id)
        if existing_asset_id and existing_asset_id != asset_id:
            raise RuntimeError(
                "Multiple generated assets found for the same creative generation plan item "
                f"(batch_id={batch_id}, asset_brief_id={asset_brief_id}, plan_item_id={plan_item_id}, "
                f"asset_ids={[existing_asset_id, asset_id]})."
            )
        completed_assets[plan_item_id] = asset_id
    return completed_assets


def _retention_expires_at(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    retention_days = int(settings.CREATIVE_SERVICE_RETENTION_DAYS or 60)
    if retention_days <= 0:
        raise ValueError("CREATIVE_SERVICE_RETENTION_DAYS must be greater than zero.")
    return current + timedelta(days=retention_days)


def _split_requirement_asset_counts(requirements: list[dict[str, Any]], total_assets: int) -> list[tuple[int, dict[str, Any], int]]:
    if not requirements:
        raise ValueError("Asset brief has no requirements to generate assets from.")
    if total_assets <= 0:
        raise ValueError("CREATIVE_SERVICE_ASSETS_PER_BRIEF must be greater than zero.")
    if len(requirements) > total_assets:
        raise ValueError(
            f"Asset brief has {len(requirements)} requirements but only {total_assets} assets are allowed per brief."
        )

    base = total_assets // len(requirements)
    remainder = total_assets % len(requirements)
    allocations: list[tuple[int, dict[str, Any], int]] = []
    for idx, req in enumerate(requirements):
        allocation = base + (1 if idx < remainder else 0)
        allocations.append((idx, req, allocation))
    return allocations


def _build_image_prompt(
    *,
    creative_concept: str,
    channel_id: str,
    requirement: dict[str, Any],
    constraints: list[str],
    tone_guidelines: list[str],
    visual_guidelines: list[str],
) -> str:
    prompt_parts = [
        "Generate ORIGINAL high-performing paid social ad creative images.",
        f"Creative concept: {creative_concept.strip()}",
        f"Channel: {channel_id.strip()}",
        "Format: image.",
    ]

    angle = requirement.get("angle")
    if isinstance(angle, str) and angle.strip():
        prompt_parts.append(f"Angle: {angle.strip()}")
    hook = requirement.get("hook")
    if isinstance(hook, str) and hook.strip():
        prompt_parts.append(f"Hook: {hook.strip()}")

    if constraints:
        prompt_parts.append(f"Constraints: {constraints}")
    if tone_guidelines:
        prompt_parts.append(f"Tone guidelines: {tone_guidelines}")
    if visual_guidelines:
        prompt_parts.append(f"Visual guidelines: {visual_guidelines}")

    return "\n".join(prompt_parts).strip()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str).encode("utf-8")


def _json_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _resolve_idea_workspace_id(*, campaign_id: str | None, client_id: str) -> str:
    candidate = (campaign_id or client_id or "").strip()
    if not candidate:
        raise ValueError("idea_workspace_id resolution failed; expected campaign_id or client_id.")
    return candidate


def _extract_source_filename(source_url: str | None) -> str | None:
    if not isinstance(source_url, str) or not source_url.strip():
        return None
    raw = source_url.strip()
    parsed = urlparse(raw)
    path = parsed.path or raw
    cleaned = unquote(path).rsplit("/", 1)[-1].strip()
    if not cleaned:
        return None
    return cleaned


def _extract_company_swipe_media_url(media: Any) -> str | None:
    for candidate in (
        getattr(media, "download_url", None),
        getattr(media, "url", None),
        getattr(media, "thumbnail_url", None),
        getattr(media, "path", None),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _resolve_default_swipe_sources(*, session, org_id: str) -> list[_DefaultSwipeSource]:
    from app.temporal.activities.swipe_image_ad_activities import _resolve_swipe_requires_product_image_policy

    company_repo = CompanySwipesRepository(session)
    by_label: dict[str, _DefaultSwipeSource] = {}
    duplicates: set[str] = set()

    for swipe_asset in company_repo.list_assets(org_id=org_id, limit=5000):
        swipe_id = str(getattr(swipe_asset, "id", "") or "").strip()
        if not swipe_id:
            continue
        media_items = company_repo.list_media(org_id=org_id, swipe_asset_id=swipe_id)
        for media in media_items:
            source_media_url = _extract_company_swipe_media_url(media)
            if not source_media_url:
                continue
            source_label = _extract_source_filename(source_media_url)
            if not source_label:
                continue
            if source_label not in _DEFAULT_SWIPE_SOURCE_LABELS:
                continue
            product_image_policy, _policy_source, _source_filename = _resolve_swipe_requires_product_image_policy(
                explicit_requires_product_image=None,
                swipe_source_url=source_media_url,
            )
            source = _DefaultSwipeSource(
                company_swipe_id=swipe_id,
                source_label=source_label,
                source_media_url=source_media_url,
                product_image_policy=product_image_policy,
            )
            if source_label in by_label:
                existing = by_label[source_label]
                if (
                    existing.company_swipe_id != source.company_swipe_id
                    or existing.source_media_url != source.source_media_url
                ):
                    duplicates.add(source_label)
                continue
            by_label[source_label] = source

    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(
            "Default swipe set resolution found duplicate source labels in company_swipe_assets. "
            f"Resolve duplicates before creative generation. duplicates={duplicate_list}"
        )

    missing = [label for label in _DEFAULT_SWIPE_SOURCE_LABELS if label not in by_label]
    if missing:
        raise ValueError(
            "Default swipe set resolution is incomplete for creative generation. "
            f"Missing required source labels: {', '.join(missing)}"
        )

    return [by_label[label] for label in _DEFAULT_SWIPE_SOURCE_LABELS]


def _extract_brief(
    *,
    artifacts_repo: ArtifactsRepository,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
    asset_brief_id: str,
) -> tuple[dict[str, Any], str]:
    briefs_artifacts = artifacts_repo.list(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.asset_brief,
        limit=200,
    )

    brief: dict[str, Any] | None = None
    brief_artifact_id: str | None = None
    for art in briefs_artifacts:
        payload = art.data if isinstance(art.data, dict) else {}
        for entry in payload.get("asset_briefs") or []:
            if isinstance(entry, dict) and str(entry.get("id")) == str(asset_brief_id):
                brief = entry
                brief_artifact_id = str(art.id)
                break
        if brief:
            break

    if not brief or not isinstance(brief, dict):
        raise ValueError(f"Asset brief not found: {asset_brief_id}")
    if not brief_artifact_id:
        raise RuntimeError(f"Asset brief artifact id not resolved for brief {asset_brief_id}")
    return brief, brief_artifact_id


def _validate_brief_scope(
    *,
    session,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
    asset_brief_id: str,
    brief: dict[str, Any],
) -> str | None:
    funnel_id = brief.get("funnelId")
    if not funnel_id:
        return None

    funnel = session.scalars(select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)).first()
    if not funnel:
        raise ValueError(f"Funnel not found for asset brief {asset_brief_id}")
    if str(funnel.client_id) != str(client_id):
        raise ValueError("Funnel must belong to the same client as the asset brief")
    if campaign_id and str(funnel.campaign_id) != str(campaign_id):
        raise ValueError("Funnel must belong to the same campaign as the asset brief")
    return str(funnel_id)


def _pick_latest_context_file(files: Sequence[Any], *, doc_key: str):
    best = None
    for record in files:
        if (getattr(record, "doc_key", None) or "") != doc_key:
            continue
        if best is None:
            best = record
            continue
        created_at = getattr(record, "created_at", None)
        best_created_at = getattr(best, "created_at", None)
        if best_created_at is None:
            best = record
            continue
        if created_at is not None and created_at > best_created_at:
            best = record
    return best


def _find_latest_campaign_artifact_for_brief(
    *,
    artifacts_repo: ArtifactsRepository,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
    artifact_type: ArtifactTypeEnum,
    asset_brief_id: str,
    source_brief_sha256: str | None = None,
):
    artifacts = artifacts_repo.list(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=artifact_type,
        limit=200,
    )
    for artifact in artifacts:
        payload = artifact.data if isinstance(artifact.data, dict) else {}
        if str(payload.get("assetBriefId") or payload.get("asset_brief_id") or "").strip() != asset_brief_id:
            continue
        if source_brief_sha256 is not None:
            candidate_sha = str(
                payload.get("sourceBriefSha256") or payload.get("source_brief_sha256") or ""
            ).strip()
            if candidate_sha != source_brief_sha256:
                continue
        return artifact
    return None


def _select_copy_generation_context_files(
    *,
    session,
    org_id: str,
    idea_workspace_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
) -> list[Any]:
    context_files = ClaudeContextFilesRepository(session).list_for_generation_context(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )
    selected: list[Any] = []
    for doc_key in (
        "client_canon_compact",
        "client_canon",
        "strategy_v2_stage3",
        "strategy_v2_offer",
        "strategy_v2_copy",
        "strategy_v2_copy_context",
        "metric_schema",
        f"strategy_sheet:{campaign_id or 'none'}",
        f"experiment_specs:{campaign_id or 'none'}",
        f"asset_briefs:{campaign_id or 'none'}",
    ):
        picked = _pick_latest_context_file(context_files, doc_key=doc_key)
        if picked is not None:
            selected.append(picked)

    if not any(
        (getattr(record, "doc_key", None) or "").startswith("client_canon")
        or (getattr(record, "doc_key", None) or "") in {"strategy_v2_stage3", "strategy_v2_offer", "strategy_v2_copy", "strategy_v2_copy_context"}
        for record in selected
    ):
        raise RuntimeError(
            "Missing required copy-pack generation context files. "
            "Expected client_canon* or Strategy V2 context artifacts in Claude workspace."
        )
    return selected


def _build_ad_copy_pack_prompt(
    *,
    brief: dict[str, Any],
    image_requirements: list[tuple[int, dict[str, Any]]],
) -> str:
    requirements_payload = []
    for requirement_index, requirement in image_requirements:
        requirements_payload.append(
            {
                "requirementIndex": requirement_index,
                "channel": requirement.get("channel"),
                "format": requirement.get("format"),
                "funnelStage": requirement.get("funnelStage"),
                "angle": requirement.get("angle"),
                "hook": requirement.get("hook"),
            }
        )

    prompt_payload = {
        "assetBrief": {
            "id": brief.get("id"),
            "campaignId": brief.get("campaignId"),
            "clientId": brief.get("clientId"),
            "funnelId": brief.get("funnelId"),
            "experimentId": brief.get("experimentId"),
            "variantId": brief.get("variantId"),
            "variantName": brief.get("variantName"),
            "creativeConcept": brief.get("creativeConcept"),
            "constraints": brief.get("constraints") or [],
            "toneGuidelines": brief.get("toneGuidelines") or [],
            "visualGuidelines": brief.get("visualGuidelines") or [],
        },
        "imageRequirements": requirements_payload,
    }

    return (
        "Generate one ad copy pack for each image-ad requirement in the attached asset brief.\n"
        "Use the attached strategy, offer, copy, copy-context, and experiment documents as the source of truth.\n"
        "Do not invent claims, pricing, guarantees, or proof. If a detail is unsupported, keep the copy conservative.\n"
        "The copy pack will be reused across multiple swipe-source executions for the same requirement, so it must be platform-ready and brand-safe.\n\n"
        "Rules:\n"
        "- Return exactly one copy pack per image requirement.\n"
        "- requirementIndex must match the input requirementIndex.\n"
        "- creativeConcept should sharpen the brief into a single creative throughline.\n"
        "- metaPrimaryText should be concise but complete for Meta body copy.\n"
        "- metaHeadline and metaDescription must be publishable without additional editing.\n"
        "- claimsGuardrails must be a list of short, concrete instructions that prevent unsupported claims or unsafe phrasing.\n"
        "- Do not generate on-image headline, body, or CTA copy. The swipe image-ad flow owns all on-image text generation.\n"
        "- Use clear, literal marketing copy. Do not output placeholders.\n\n"
        f"INPUT JSON:\n{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
    )


def _persist_context_doc(
    *,
    org_id: str,
    idea_workspace_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    doc_key: str,
    doc_title: str,
    source_kind: str,
    content_bytes: bytes,
) -> None:
    ensure_uploaded_to_claude(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=doc_key,
        doc_title=doc_title,
        source_kind=source_kind,
        step_key=None,
        filename=f"{doc_key}.json",
        mime_type="text/plain",
        content_bytes=content_bytes,
        drive_doc_id=None,
        drive_url=None,
    )
    if is_gemini_file_search_enabled():
        ensure_uploaded_to_gemini_file_search(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            client_id=client_id,
            product_id=product_id,
            campaign_id=campaign_id,
            doc_key=doc_key,
            doc_title=doc_title,
            source_kind=source_kind,
            step_key=None,
            filename=f"{doc_key}.json",
            mime_type="text/plain",
            content_bytes=content_bytes,
            drive_doc_id=None,
            drive_url=None,
        )


def _get_or_create_ad_copy_pack_artifact(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    asset_brief_id: str,
    brief_artifact_id: str,
    brief: dict[str, Any],
) -> Any:
    image_requirements = [
        (idx, requirement)
        for idx, requirement in enumerate(brief.get("requirements") or [])
        if isinstance(requirement, dict) and _normalize_requirement_format(str(requirement.get("format") or "")) == "image"
    ]
    if not image_requirements:
        raise ValueError(
            f"Asset brief {asset_brief_id} has no image-ad requirements; cannot build ad copy pack."
        )

    brief_payload = {
        "adCopyPackSchemaVersion": _AD_COPY_PACK_SCHEMA_VERSION,
        "assetBriefId": asset_brief_id,
        "sourceBriefArtifactId": brief_artifact_id,
        "brief": brief,
    }
    source_brief_sha256 = _json_sha256(brief_payload)
    artifacts_repo = ArtifactsRepository(session)
    existing_artifact = _find_latest_campaign_artifact_for_brief(
        artifacts_repo=artifacts_repo,
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.ad_copy_pack,
        asset_brief_id=asset_brief_id,
        source_brief_sha256=source_brief_sha256,
    )
    if existing_artifact is not None:
        return existing_artifact

    idea_workspace_id = _resolve_idea_workspace_id(campaign_id=campaign_id, client_id=client_id)
    context_files = _select_copy_generation_context_files(
        session=session,
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
    )
    prompt = _build_ad_copy_pack_prompt(brief=brief, image_requirements=image_requirements)
    response = call_claude_structured_message(
        model=CLAUDE_DEFAULT_MODEL,
        system=(
            "Generate deterministic ad copy packs for swipe-first creative production. "
            "Use the attached documents as the source of truth. Do not invent unsupported claims."
        ),
        user_content=[{"type": "text", "text": prompt}, *build_document_blocks(context_files)],
        output_schema=_AD_COPY_PACK_OUTPUT_SCHEMA,
        max_tokens=6000,
        temperature=0.2,
    )
    parsed = response.get("parsed")
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Claude did not return a JSON object for ad copy pack generation (asset_brief_id={asset_brief_id})."
        )

    validated = AdCopyPackStructuredOutput.model_validate(parsed)
    if len(validated.copy_packs) != len(image_requirements):
        raise RuntimeError(
            "Ad copy pack generation returned the wrong number of items. "
            f"asset_brief_id={asset_brief_id} expected={len(image_requirements)} returned={len(validated.copy_packs)}"
        )

    expected_indexes = [idx for idx, _requirement in image_requirements]
    seen_indexes = [item.requirement_index for item in validated.copy_packs]
    if sorted(expected_indexes) != sorted(seen_indexes):
        raise RuntimeError(
            "Ad copy pack generation returned mismatched requirement indexes. "
            f"asset_brief_id={asset_brief_id} expected={expected_indexes} returned={seen_indexes}"
        )

    artifact_payload = AdCopyPackArtifact(
        schemaVersion=_AD_COPY_PACK_SCHEMA_VERSION,
        assetBriefId=asset_brief_id,
        sourceBriefArtifactId=brief_artifact_id,
        sourceBriefSha256=source_brief_sha256,
        sourceFunnelId=str(brief.get("funnelId")).strip() if isinstance(brief.get("funnelId"), str) and brief.get("funnelId").strip() else None,
        copyPacks=sorted(validated.copy_packs, key=lambda item: item.requirement_index),
    )
    artifact = artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.ad_copy_pack,
        data=artifact_payload.model_dump(mode="json", by_alias=True),
    )
    _persist_context_doc(
        org_id=org_id,
        idea_workspace_id=idea_workspace_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        doc_key=f"{_AD_COPY_PACK_DOC_KEY_PREFIX}:{asset_brief_id}",
        doc_title="Ad Copy Pack",
        source_kind=ArtifactTypeEnum.ad_copy_pack.value,
        content_bytes=_json_bytes(artifact_payload.model_dump(mode="json", by_alias=True)),
    )
    return artifact


def _create_creative_generation_plan_artifact(
    *,
    session,
    org_id: str,
    client_id: str,
    product_id: str,
    campaign_id: str | None,
    asset_brief_id: str,
    brief_artifact_id: str,
    brief: dict[str, Any],
    ad_copy_pack_artifact: Any,
    batch_id: str,
) -> Any:
    artifacts_repo = ArtifactsRepository(session)
    source_payload = ad_copy_pack_artifact.data if isinstance(ad_copy_pack_artifact.data, dict) else {}
    validated_copy_artifact = AdCopyPackArtifact.model_validate(source_payload)
    default_swipes = _resolve_default_swipe_sources(session=session, org_id=org_id)
    copy_pack_ids_by_requirement = {
        item.requirement_index: item.id for item in validated_copy_artifact.copy_packs
    }
    items = _build_creative_generation_plan_items(
        asset_brief_id=asset_brief_id,
        batch_id=batch_id,
        requirements=brief.get("requirements") or [],
        default_swipes=default_swipes,
        copy_pack_ids_by_requirement=copy_pack_ids_by_requirement,
    )

    if not items:
        raise ValueError(
            f"Creative generation plan would be empty for asset brief {asset_brief_id}. "
            "At least one image-ad requirement is required."
        )

    plan_payload = CreativeGenerationPlanArtifact(
        assetBriefId=asset_brief_id,
        sourceBriefArtifactId=brief_artifact_id,
        adCopyPackArtifactId=str(ad_copy_pack_artifact.id),
        batchId=batch_id,
        sourceSetKey=_DEFAULT_SWIPE_SOURCE_SET_KEY,
        items=items,
    )
    return artifacts_repo.insert(
        org_id=org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id,
        artifact_type=ArtifactTypeEnum.creative_generation_plan,
        data=plan_payload.model_dump(mode="json", by_alias=True),
    )


def _build_creative_generation_plan_items(
    *,
    asset_brief_id: str,
    batch_id: str,
    requirements: Sequence[Any],
    default_swipes: Sequence[_DefaultSwipeSource],
    copy_pack_ids_by_requirement: dict[int, str],
) -> list[CreativeGenerationPlanItem]:
    items: list[CreativeGenerationPlanItem] = []
    for requirement_index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError("Asset brief requirements must be objects.")
        normalized_format = _normalize_requirement_format(str(requirement.get("format") or ""))
        if normalized_format != "image":
            continue
        copy_pack_id = copy_pack_ids_by_requirement.get(requirement_index)
        if not isinstance(copy_pack_id, str) or not copy_pack_id.strip():
            raise ValueError(
                "Creative generation plan requires an ad copy pack for every image requirement. "
                f"asset_brief_id={asset_brief_id} missing_requirement_index={requirement_index}"
            )
        for source in default_swipes:
            items.append(
                CreativeGenerationPlanItem(
                    id=_stable_idempotency_key(
                        "creative_generation_plan_item_v1",
                        batch_id,
                        asset_brief_id,
                        str(requirement_index),
                        source.company_swipe_id,
                        source.source_label,
                    ),
                    batchId=batch_id,
                    assetBriefId=asset_brief_id,
                    requirementIndex=requirement_index,
                    channel=str(requirement.get("channel") or "meta"),
                    format=str(requirement.get("format") or "image_ad"),
                    funnelStage=(
                        str(requirement.get("funnelStage")).strip()
                        if isinstance(requirement.get("funnelStage"), str) and requirement.get("funnelStage").strip()
                        else None
                    ),
                    angle=(
                        str(requirement.get("angle")).strip()
                        if isinstance(requirement.get("angle"), str) and requirement.get("angle").strip()
                        else None
                    ),
                    hook=(
                        str(requirement.get("hook")).strip()
                        if isinstance(requirement.get("hook"), str) and requirement.get("hook").strip()
                        else None
                    ),
                    companySwipeId=source.company_swipe_id,
                    sourceLabel=source.source_label,
                    sourceMediaUrl=source.source_media_url,
                    copyPackId=copy_pack_id,
                    productImagePolicy=source.product_image_policy,
                    sourceSetKey=_DEFAULT_SWIPE_SOURCE_SET_KEY,
                )
            )
    return items


def _record_run_event(
    *,
    session,
    run_id: str,
    retention_expires_at: datetime,
    event_type: str,
    status: str | None,
    payload: dict[str, Any],
    turn_id: str | None = None,
) -> None:
    session.add(
        CreativeServiceEvent(
            run_id=run_id,
            turn_id=turn_id,
            event_type=event_type,
            status=status,
            payload=payload,
            retention_expires_at=retention_expires_at,
        )
    )
    session.commit()


def _record_output(
    *,
    session,
    run_id: str,
    turn_id: str | None,
    retention_expires_at: datetime,
    output_kind: str,
    output_index: int | None,
    remote_asset_id: str | None,
    primary_uri: str | None,
    primary_url: str | None,
    prompt_used: str | None,
    local_asset_id: str | None,
    metadata: dict[str, Any],
) -> None:
    session.add(
        CreativeServiceOutput(
            run_id=run_id,
            turn_id=turn_id,
            output_kind=output_kind,
            output_index=output_index,
            remote_asset_id=remote_asset_id,
            primary_uri=primary_uri,
            primary_url=primary_url,
            prompt_used=prompt_used,
            local_asset_id=local_asset_id,
            metadata_json=metadata,
            retention_expires_at=retention_expires_at,
        )
    )
    session.commit()


def _get_existing_run_by_idempotency(*, session, idempotency_key: str) -> CreativeServiceRun | None:
    return session.scalars(
        select(CreativeServiceRun).where(CreativeServiceRun.idempotency_key == idempotency_key)
    ).first()


def _existing_output_asset_ids(
    *,
    session,
    run_id: str,
    output_kinds: set[str],
) -> list[str]:
    rows = session.scalars(
        select(CreativeServiceOutput)
        .where(
            CreativeServiceOutput.run_id == run_id,
            CreativeServiceOutput.output_kind.in_(list(output_kinds)),
            CreativeServiceOutput.local_asset_id.is_not(None),
        )
        .order_by(CreativeServiceOutput.created_at.asc())
    ).all()
    out: list[str] = []
    for row in rows:
        if row.local_asset_id:
            out.append(str(row.local_asset_id))
    return out


def _upsert_turn_traces(
    *,
    session,
    run_id: str,
    traces: Sequence[VideoTurnTrace],
    retention_expires_at: datetime,
) -> dict[str, str]:
    turn_id_map: dict[str, str] = {}
    for idx, trace in enumerate(traces):
        existing = session.scalars(
            select(CreativeServiceTurn).where(
                CreativeServiceTurn.run_id == run_id,
                CreativeServiceTurn.remote_turn_id == trace.turn_id,
            )
        ).first()
        if existing:
            existing.status = trace.status
            existing.response_payload = trace.response_payload
            existing.error_detail = trace.error_detail
            existing.started_at = trace.started_at
            existing.finished_at = trace.finished_at
            existing.updated_at = datetime.now(timezone.utc)
            turn = existing
        else:
            turn = CreativeServiceTurn(
                run_id=run_id,
                turn_index=idx,
                status=trace.status,
                remote_turn_id=trace.turn_id,
                request_payload=trace.request_payload,
                response_payload=trace.response_payload,
                error_detail=trace.error_detail,
                retention_expires_at=retention_expires_at,
                started_at=trace.started_at,
                finished_at=trace.finished_at,
            )
            session.add(turn)
        session.commit()
        session.refresh(turn)
        turn_id_map[trace.turn_id] = str(turn.id)
        _record_run_event(
            session=session,
            run_id=run_id,
            retention_expires_at=retention_expires_at,
            event_type="video.turn",
            status=trace.status,
            payload=trace.response_payload,
            turn_id=str(turn.id),
        )
    return turn_id_map


def _download_remote_asset(*, url: str, timeout_seconds: float) -> tuple[bytes, str]:
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=timeout_seconds)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to download generated asset from creative service url={url}: {exc}") from exc

    content = resp.content
    if not content:
        raise RuntimeError(f"Creative service returned empty asset payload for url={url}")

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type:
        raise RuntimeError(f"Creative service response missing content-type header for url={url}")
    return content, content_type


def _extension_for_content_type(content_type: str) -> str:
    ext = mimetypes.guess_extension(content_type)
    if ext:
        return ext.lstrip(".")
    if "/" in content_type:
        return content_type.split("/", 1)[1]
    raise RuntimeError(f"Unable to infer file extension for content type: {content_type}")


def _asset_kind_for_content_type(content_type: str, *, expected_kind: str | None = None) -> str:
    if content_type.startswith("image/"):
        inferred = "image"
    elif content_type.startswith("video/"):
        inferred = "video"
    else:
        raise RuntimeError(f"Unsupported generated asset content type: {content_type}")

    if expected_kind and inferred != expected_kind:
        raise RuntimeError(
            f"Generated asset content type mismatch. expected_kind={expected_kind} content_type={content_type}"
        )
    return inferred


def _extract_remote_reference_asset_id(*, ai_metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(ai_metadata, dict):
        return None
    remote_id = ai_metadata.get("creativeServiceReferenceAssetId")
    if not isinstance(remote_id, str):
        return None
    cleaned = remote_id.strip()
    return cleaned or None


def _extract_brand_logo_public_id(*, design_tokens: dict[str, Any] | None) -> str | None:
    if not isinstance(design_tokens, dict) or not design_tokens:
        return None
    brand = design_tokens.get("brand")
    if not isinstance(brand, dict):
        return None
    logo_public_id = brand.get("logoAssetPublicId")
    if not isinstance(logo_public_id, str) or not logo_public_id.strip():
        return None
    cleaned = logo_public_id.strip()
    # Treat token placeholders as absent.
    if cleaned.startswith("__"):
        return None
    return cleaned


def _resolve_brand_logo_reference_asset(
    *,
    session,
    org_id: str,
    logo_public_id: str,
) -> _ProductReferenceAsset:
    assets_repo = _repo(session)
    asset = assets_repo.get_by_public_id(org_id=org_id, public_id=logo_public_id)
    if not asset:
        raise ValueError(f"Brand logo asset not found for public_id={logo_public_id}")
    if asset.asset_kind != "image":
        raise ValueError(
            f"Brand logo asset must be an image (public_id={logo_public_id}, asset_kind={asset.asset_kind})"
        )
    if not asset.storage_key:
        raise ValueError(f"Brand logo asset is missing storage_key (public_id={logo_public_id})")
    if asset.file_status and asset.file_status != "ready":
        raise ValueError(
            f"Brand logo asset is not ready (public_id={logo_public_id}, file_status={asset.file_status})"
        )
    now = datetime.now(timezone.utc)
    if asset.expires_at and asset.expires_at <= now:
        raise ValueError(f"Brand logo asset is expired (public_id={logo_public_id}, expires_at={asset.expires_at})")

    title = None
    if isinstance(asset.ai_metadata, dict):
        name = asset.ai_metadata.get("filename")
        if isinstance(name, str) and name.strip():
            title = name.strip()

    storage = MediaStorage()
    return _ProductReferenceAsset(
        local_asset_id=str(asset.id),
        primary_url=storage.presign_get(bucket=storage.bucket, key=asset.storage_key),
        title=title or "Brand logo",
        remote_asset_id=_extract_remote_reference_asset_id(ai_metadata=asset.ai_metadata),
    )


def _select_product_reference_assets(*, session, org_id: str, product_id: str) -> list[_ProductReferenceAsset]:
    limit = int(settings.CREATIVE_SERVICE_PRODUCT_ASSET_CONTEXT_LIMIT or 6)
    if limit <= 0:
        raise ValueError("CREATIVE_SERVICE_PRODUCT_ASSET_CONTEXT_LIMIT must be greater than zero.")

    product = ProductsRepository(session).get(org_id=org_id, product_id=product_id)
    if not product:
        raise ValueError(f"Product not found: {product_id}")

    primary_asset_id = str(product.primary_asset_id) if product.primary_asset_id else None
    assets_repo = _repo(session)
    assets = assets_repo.list(org_id=org_id, product_id=product_id)
    storage = MediaStorage()
    now = datetime.now(timezone.utc)

    allowed_source_types = {AssetSourceEnum.upload, AssetSourceEnum.historical}
    candidates = []
    for asset in assets:
        if asset.asset_kind != "image":
            continue
        if asset.channel_id != "product":
            continue
        if not asset.storage_key:
            continue
        if asset.file_status and asset.file_status != "ready":
            continue
        if asset.expires_at and asset.expires_at <= now:
            continue
        if asset.source_type not in allowed_source_types:
            continue
        candidates.append(asset)

    if primary_asset_id:
        candidates.sort(key=lambda item: str(item.id) != primary_asset_id)
    selected = candidates[:limit]
    if not selected:
        raise ValueError(
            "No active source product images are available for creative generation references. "
            "Upload at least one product image and set it as primary if needed."
        )

    references: list[_ProductReferenceAsset] = []
    for asset in selected:
        title = None
        if isinstance(asset.ai_metadata, dict):
            name = asset.ai_metadata.get("filename")
            if isinstance(name, str):
                cleaned = name.strip()
                if cleaned:
                    title = cleaned
        references.append(
            _ProductReferenceAsset(
                local_asset_id=str(asset.id),
                primary_url=storage.presign_get(bucket=storage.bucket, key=asset.storage_key),
                title=title,
                remote_asset_id=_extract_remote_reference_asset_id(ai_metadata=asset.ai_metadata),
            )
        )
    return references


def _ensure_remote_reference_asset_ids(
    *,
    session,
    org_id: str,
    creative_client: CreativeServiceClient,
    references: Sequence[_ProductReferenceAsset],
) -> list[str]:
    if not references:
        raise ValueError("At least one product reference asset is required.")

    assets_repo = _repo(session)
    storage = MediaStorage()
    remote_asset_ids: list[str] = []
    for index, reference in enumerate(references):
        if reference.remote_asset_id:
            remote_asset_ids.append(reference.remote_asset_id)
            continue

        asset = assets_repo.get(org_id=org_id, asset_id=reference.local_asset_id)
        if not asset:
            raise RuntimeError(
                f"Local product asset disappeared while syncing reference asset: {reference.local_asset_id}"
            )
        if not asset.storage_key:
            raise RuntimeError(f"Local product asset is missing storage key: {reference.local_asset_id}")

        content_bytes, downloaded_content_type = storage.download_bytes(key=asset.storage_key)
        if not content_bytes:
            raise RuntimeError(f"Local product asset content is empty: {reference.local_asset_id}")
        content_type = (downloaded_content_type or asset.content_type or "").strip().lower()
        if not content_type:
            raise RuntimeError(
                f"Unable to determine content type for local product asset {reference.local_asset_id}"
            )

        ext = _extension_for_content_type(content_type)
        title_slug = (reference.title or f"mos_product_reference_{index + 1}").strip().replace(" ", "_")
        file_name = title_slug if title_slug.endswith(f".{ext}") else f"{title_slug}.{ext}"

        created = creative_client.upload_asset(
            kind="image",
            source="upload",
            file_name=file_name,
            file_bytes=content_bytes,
            content_type=content_type,
            title=reference.title,
            description="MOS product reference asset for image ad generation",
            metadata_json={
                "source": "mos_product_asset",
                "mos_asset_id": reference.local_asset_id,
                "reference_index": index,
            },
            generate_proxy=True,
        )
        remote_asset_id = created.id.strip()
        if not remote_asset_id:
            raise RuntimeError(f"Creative service returned empty asset id for local asset {reference.local_asset_id}")

        metadata = dict(asset.ai_metadata) if isinstance(asset.ai_metadata, dict) else {}
        metadata.update(
            {
                "creativeServiceReferenceAssetId": remote_asset_id,
                "creativeServiceReferenceAssetSyncedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        assets_repo.update(org_id=org_id, asset_id=reference.local_asset_id, ai_metadata=metadata)

        remote_asset_ids.append(remote_asset_id)

    return remote_asset_ids


def _create_generated_asset_from_url(
    *,
    session,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
    experiment_id: str | None = None,
    product_id: str | None,
    funnel_id: str | None,
    brief_artifact_id: str,
    asset_brief_id: str,
    variant_id: str | None,
    variant_index: int | None,
    channel_id: str,
    fmt: str,
    requirement_index: int,
    requirement: dict[str, Any],
    primary_url: str,
    prompt: str,
    source_kind: str,
    expected_asset_kind: str | None,
    retention_expires_at: datetime,
    extra_ai_metadata: dict[str, Any],
    attach_to_product: bool,
) -> str:
    timeout_seconds = float(settings.CREATIVE_SERVICE_TIMEOUT_SECONDS or 30.0)
    content, content_type = _download_remote_asset(url=primary_url, timeout_seconds=timeout_seconds)

    asset_kind = _asset_kind_for_content_type(content_type, expected_kind=expected_asset_kind)
    sha256 = hashlib.sha256(content).hexdigest()
    ext = _extension_for_content_type(content_type)

    storage = MediaStorage()
    key = storage.build_key(sha256=sha256, ext=ext, kind="orig")
    if not storage.object_exists(bucket=storage.bucket, key=key):
        storage.upload_bytes(
            bucket=storage.bucket,
            key=key,
            data=content,
            content_type=content_type,
            cache_control=IMMUTABLE_CACHE_CONTROL,
        )

    width: int | None = None
    height: int | None = None
    if asset_kind == "image":
        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to inspect generated image dimensions for url={primary_url}: {exc}") from exc

    created_asset = _repo(session).create(
        org_id=org_id,
        client_id=client_id,
        campaign_id=campaign_id,
        experiment_id=experiment_id,
        product_id=product_id if attach_to_product else None,
        funnel_id=funnel_id,
        variant_id=variant_id,
        asset_brief_artifact_id=brief_artifact_id,
        source_type=AssetSourceEnum.ai,
        status=AssetStatusEnum.draft,
        asset_kind=asset_kind,
        channel_id=channel_id,
        format=fmt,
        content={
            "assetBriefId": asset_brief_id,
            "requirementIndex": requirement_index,
            "requirement": requirement,
            "sourceKind": source_kind,
            "sourceUrl": primary_url,
            "variantIndex": variant_index,
            "prompt": prompt,
        },
        storage_key=key,
        content_type=content_type,
        size_bytes=len(content),
        width=width,
        height=height,
        file_source="ai",
        file_status="ready",
        ai_metadata={
            "assetBriefId": asset_brief_id,
            "requirementIndex": requirement_index,
            "variantIndex": variant_index,
            "sourceKind": source_kind,
            "sourceUrl": primary_url,
            "prompt": prompt,
            "sha256": sha256,
            **extra_ai_metadata,
        },
        tags=["creative", "generated", "asset_brief", channel_id, source_kind],
        expires_at=retention_expires_at,
    )
    return str(created_asset.id)


def _wait_for_image_job(
    *,
    creative_client: CreativeServiceClient,
    job_id: str,
    run: CreativeServiceRun,
    session,
    retention_expires_at: datetime,
):
    poll_interval = float(settings.CREATIVE_SERVICE_POLL_INTERVAL_SECONDS or 2.0)
    poll_timeout = float(settings.CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS or 300.0)
    if poll_interval <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_INTERVAL_SECONDS must be greater than zero.")
    if poll_timeout <= 0:
        raise ValueError("CREATIVE_SERVICE_POLL_TIMEOUT_SECONDS must be greater than zero.")

    started = time.monotonic()
    prev_status = run.status
    while True:
        job = creative_client.get_image_ads_job(job_id=job_id)
        run.status = job.status
        run.response_payload = job.model_dump(mode="json")
        run.updated_at = datetime.now(timezone.utc)
        session.commit()

        if prev_status != job.status:
            _record_run_event(
                session=session,
                run_id=str(run.id),
                retention_expires_at=retention_expires_at,
                event_type="image.status",
                status=job.status,
                payload=job.model_dump(mode="json"),
            )
            prev_status = job.status

        if job.status in _IMAGE_TERMINAL_STATUSES:
            return job

        if (time.monotonic() - started) > poll_timeout:
            raise RuntimeError(
                f"Timed out waiting for image ads job completion (job_id={job_id}, timeout_seconds={poll_timeout})"
            )
        time.sleep(poll_interval)


@activity.defn
def generate_assets_for_brief_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate and persist creative assets for a single asset brief.

    This activity calls an external creative service contract and stores generated media locally.
    """

    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    product_id = params.get("product_id")
    asset_brief_id = params.get("asset_brief_id")
    workflow_run_id = params.get("workflow_run_id")

    if not isinstance(product_id, str) or not product_id.strip():
        raise ValueError("product_id is required to generate assets for a brief.")
    if not isinstance(asset_brief_id, str) or not asset_brief_id.strip():
        raise ValueError("asset_brief_id is required to generate assets.")
    execution_key = _resolve_creative_generation_execution_key(workflow_run_id=workflow_run_id)
    batch_id = _build_creative_generation_batch_id(
        execution_key=execution_key,
        asset_brief_id=asset_brief_id,
    )

    def log_activity(step: str, status: str, *, payload_in=None, payload_out=None, error: str | None = None) -> None:
        if not workflow_run_id:
            return
        with session_scope() as log_session:
            WorkflowsRepository(log_session).log_activity(
                workflow_run_id=str(workflow_run_id),
                step=step,
                status=status,
                payload_in=payload_in,
                payload_out=payload_out,
                error=error,
            )

    log_activity(
        "asset_generation",
        "started",
        payload_in={"asset_brief_id": asset_brief_id, "campaign_id": campaign_id, "product_id": product_id},
    )

    creative_client: CreativeServiceClient | None = None

    try:
        with session_scope() as session:
            artifacts_repo = ArtifactsRepository(session)
            assets_repo = AssetsRepository(session)
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

            creative_concept = brief.get("creativeConcept")
            if not isinstance(creative_concept, str) or not creative_concept.strip():
                raise ValueError("Asset brief is missing creativeConcept.")

            requirements_raw = brief.get("requirements") or []
            if not isinstance(requirements_raw, list) or not requirements_raw:
                raise ValueError("Asset brief has no requirements to generate assets from.")

            requirements: list[dict[str, Any]] = []
            for req in requirements_raw:
                if not isinstance(req, dict):
                    raise ValueError("Asset brief requirements must be objects.")
                requirements.append(req)

            from app.temporal.activities.swipe_image_ad_activities import generate_swipe_image_ad_activity

            requirement_allocations = _split_requirement_asset_counts(
                requirements,
                int(settings.CREATIVE_SERVICE_ASSETS_PER_BRIEF or 6),
            )
            variant_id = brief.get("variantId") or brief.get("variant_id")
            constraints = [item for item in (brief.get("constraints") or []) if isinstance(item, str)]
            tone_guidelines = [item for item in (brief.get("toneGuidelines") or []) if isinstance(item, str)]
            visual_guidelines = [item for item in (brief.get("visualGuidelines") or []) if isinstance(item, str)]
            selected_swipe_sources: list[dict[str, Any]] = []
            for req in requirements:
                explicit_company_swipe_id, explicit_swipe_image_url = _extract_requirement_swipe_source(req)
                explicit_swipe_requires_product_image = _extract_requirement_swipe_requires_product_image(req)
                if explicit_swipe_requires_product_image is not None and not (
                    explicit_company_swipe_id or explicit_swipe_image_url
                ):
                    raise ValueError(
                        "swipeRequiresProductImage/swipe_requires_product_image requires an explicit swipe source "
                        "(companySwipeId/company_swipe_id or swipeImageUrl/swipe_image_url)."
                    )
                normalized_format = _normalize_requirement_format(str(req.get("format") or ""))
                if normalized_format == "image" and (explicit_company_swipe_id or explicit_swipe_image_url):
                    raise ValueError(
                        "Image-ad requirements must not declare explicit swipe bindings in the asset brief. "
                        "Swipe source binding is system-owned and comes from the curated default swipe set."
                    )

            image_reference_asset_ids: list[str] = []
            product_asset_urls: list[str] = []
            video_reference_attachments: list[CreativeServiceVideoAttachmentIn] = []
            retention_expires_at = _retention_expires_at()
            created_asset_ids: list[str] = []
            variant_cursor = 0
            ad_copy_pack_artifact = _get_or_create_ad_copy_pack_artifact(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                asset_brief_id=asset_brief_id,
                brief_artifact_id=brief_artifact_id,
                brief=brief,
            )
            ad_copy_pack_payload = ad_copy_pack_artifact.data if isinstance(ad_copy_pack_artifact.data, dict) else {}
            ad_copy_pack = AdCopyPackArtifact.model_validate(ad_copy_pack_payload)
            copy_pack_by_id = {item.id: item for item in ad_copy_pack.copy_packs}
            creative_generation_plan_artifact = _create_creative_generation_plan_artifact(
                session=session,
                org_id=org_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                asset_brief_id=asset_brief_id,
                brief_artifact_id=brief_artifact_id,
                brief=brief,
                ad_copy_pack_artifact=ad_copy_pack_artifact,
                batch_id=batch_id,
            )
            creative_generation_plan_payload = (
                creative_generation_plan_artifact.data
                if isinstance(creative_generation_plan_artifact.data, dict)
                else {}
            )
            creative_generation_plan = CreativeGenerationPlanArtifact.model_validate(
                creative_generation_plan_payload
            )
            plan_items_by_requirement: dict[int, list[CreativeGenerationPlanItem]] = {}
            for item in creative_generation_plan.items:
                plan_items_by_requirement.setdefault(item.requirement_index, []).append(item)
            completed_image_plan_item_assets = _existing_creative_generation_assets_by_plan_item(
                assets=assets_repo.list(
                    org_id=org_id,
                    campaign_id=campaign_id,
                    product_id=product_id,
                ),
                batch_id=creative_generation_plan.batch_id,
                asset_brief_id=asset_brief_id,
            )

            video_requirements_present = any(
                _normalize_requirement_format(str(req.get("format") or "")) == "video" for req in requirements
            )
            if video_requirements_present:
                try:
                    creative_client = CreativeServiceClient()
                except CreativeServiceConfigError as exc:
                    raise RuntimeError(str(exc)) from exc

                product_reference_assets = _select_product_reference_assets(
                    session=session,
                    org_id=org_id,
                    product_id=product_id,
                )

                design_tokens = resolve_design_system_tokens(session=session, org_id=org_id, client_id=client_id) or {}
                logo_public_id = _extract_brand_logo_public_id(design_tokens=design_tokens)
                logo_reference_asset: _ProductReferenceAsset | None = None
                logo_remote_asset_id: str | None = None
                if logo_public_id:
                    logo_reference_asset = _resolve_brand_logo_reference_asset(
                        session=session,
                        org_id=org_id,
                        logo_public_id=logo_public_id,
                    )
                    # Upload logo as a separate reference so the creative model can use it if desired.
                    logo_remote_asset_id = _ensure_remote_reference_asset_ids(
                        session=session,
                        org_id=org_id,
                        creative_client=creative_client,
                        references=[logo_reference_asset],
                    )[0]
                product_reference_remote_ids = _ensure_remote_reference_asset_ids(
                    session=session,
                    org_id=org_id,
                    creative_client=creative_client,
                    references=product_reference_assets,
                )
                image_reference_asset_ids = list(product_reference_remote_ids)
                if logo_remote_asset_id:
                    image_reference_asset_ids.append(logo_remote_asset_id)
                product_asset_urls = [item.primary_url for item in product_reference_assets]
                video_reference_attachments = [
                    CreativeServiceVideoAttachmentIn(
                        asset_id=remote_asset_id,
                        title=product_reference_assets[idx].title if idx < len(product_reference_assets) else None,
                        role="product_reference",
                    )
                    for idx, remote_asset_id in enumerate(product_reference_remote_ids)
                ]
                if logo_remote_asset_id and logo_reference_asset:
                    video_reference_attachments.append(
                        CreativeServiceVideoAttachmentIn(
                            asset_id=logo_remote_asset_id,
                            title=logo_reference_asset.title,
                            role="brand_logo",
                        )
                    )

            video_orchestrator = VideoAdsOrchestrator(client=creative_client) if creative_client else None

            for requirement_index, req, allocation_count in requirement_allocations:
                channel_id = req.get("channel") or "meta"
                fmt = req.get("format") or "image"
                if not isinstance(channel_id, str) or not channel_id.strip():
                    raise ValueError("Asset requirement channel must be a non-empty string.")
                if not isinstance(fmt, str) or not fmt.strip():
                    raise ValueError("Asset requirement format must be a non-empty string.")

                normalized_format = _normalize_requirement_format(fmt)
                if normalized_format not in _SUPPORTED_FORMATS:
                    raise ValueError(
                        f"Unsupported creative brief format '{fmt}'. Supported formats: {sorted(_SUPPORTED_FORMATS)}."
                    )

                if normalized_format == "image":
                    plan_items = plan_items_by_requirement.get(requirement_index, [])
                    if not plan_items:
                        raise RuntimeError(
                            "Creative generation plan has no swipe execution items for image requirement "
                            f"(asset_brief_id={asset_brief_id}, requirement_index={requirement_index})."
                        )
                    for plan_item in plan_items:
                        copy_pack = copy_pack_by_id.get(plan_item.copy_pack_id)
                        if copy_pack is None:
                            raise RuntimeError(
                                "Creative generation plan references a missing ad copy pack item "
                                f"(asset_brief_id={asset_brief_id}, requirement_index={requirement_index}, "
                                f"copy_pack_id={plan_item.copy_pack_id})."
                            )
                        if not plan_item.company_swipe_id:
                            raise RuntimeError(
                                "Creative generation plan item is missing companySwipeId "
                                f"(asset_brief_id={asset_brief_id}, plan_item_id={plan_item.id})."
                            )

                        existing_asset_id = completed_image_plan_item_assets.get(plan_item.id)
                        if existing_asset_id:
                            created_asset_ids.append(existing_asset_id)
                            selected_swipe_sources.append(
                                {
                                    "requirement_index": requirement_index,
                                    "plan_item_id": plan_item.id,
                                    "company_swipe_id": plan_item.company_swipe_id,
                                    "swipe_source_label": plan_item.source_label,
                                    "swipe_source_url": plan_item.source_media_url,
                                    "swipe_requires_product_image": plan_item.product_image_policy,
                                    "copy_pack_id": copy_pack.id,
                                }
                            )
                            continue

                        try:
                            swipe_result = generate_swipe_image_ad_activity(
                                {
                                    "org_id": org_id,
                                    "client_id": client_id,
                                    "product_id": product_id,
                                    "campaign_id": campaign_id,
                                    "asset_brief_id": asset_brief_id,
                                    "requirement_index": requirement_index,
                                    "company_swipe_id": plan_item.company_swipe_id,
                                    "swipe_source_url": plan_item.source_media_url,
                                    "swipe_source_label": plan_item.source_label,
                                    "swipe_requires_product_image": plan_item.product_image_policy,
                                    "count": 1,
                                    "workflow_run_id": workflow_run_id,
                                    "creative_generation_batch_id": creative_generation_plan.batch_id,
                                    "creative_generation_plan_artifact_id": str(creative_generation_plan_artifact.id),
                                    "creative_generation_plan_item_id": plan_item.id,
                                    "ad_copy_pack_artifact_id": str(ad_copy_pack_artifact.id),
                                    "ad_copy_pack_id": copy_pack.id,
                                },
                            )
                        except Exception as exc:  # noqa: BLE001
                            error_summary = _summarize_exception_message(exc)
                            raise RuntimeError(
                                "Swipe image ad generation failed for planned execution item "
                                f"(asset_brief_id={asset_brief_id}, requirement_index={requirement_index}, "
                                f"plan_item_id={plan_item.id}, company_swipe_id={plan_item.company_swipe_id}, "
                                f"source_label={plan_item.source_label}, error={error_summary})."
                            ) from None

                        generated_ids = swipe_result.get("asset_ids") if isinstance(swipe_result, dict) else None
                        if not isinstance(generated_ids, list) or len(generated_ids) != 1:
                            raise RuntimeError(
                                "Swipe image ad generation returned an invalid asset id list for planned execution item "
                                f"(asset_brief_id={asset_brief_id}, plan_item_id={plan_item.id}, "
                                f"returned={len(generated_ids) if isinstance(generated_ids, list) else 0})."
                            )
                        generated_asset_id = generated_ids[0]
                        if not isinstance(generated_asset_id, str) or not generated_asset_id.strip():
                            raise RuntimeError(
                                "Swipe image ad generation returned an invalid asset id for planned execution item "
                                f"(asset_brief_id={asset_brief_id}, plan_item_id={plan_item.id})."
                            )
                        generated_asset = assets_repo.get(org_id=org_id, asset_id=generated_asset_id)
                        if generated_asset is None:
                            raise RuntimeError(
                                "Generated swipe image asset could not be reloaded for provenance annotation "
                                f"(asset_id={generated_asset_id}, asset_brief_id={asset_brief_id}, plan_item_id={plan_item.id})."
                            )
                        generated_ai_metadata = (
                            dict(generated_asset.ai_metadata) if isinstance(generated_asset.ai_metadata, dict) else {}
                        )
                        generated_ai_metadata.update(
                            {
                                "creativeGenerationBatchId": creative_generation_plan.batch_id,
                                "creativeGenerationPlanArtifactId": str(creative_generation_plan_artifact.id),
                                "creativeGenerationPlanItemId": plan_item.id,
                                "adCopyPackArtifactId": str(ad_copy_pack_artifact.id),
                                "adCopyPackId": copy_pack.id,
                                "swipeSourceLabel": plan_item.source_label,
                                "swipeSourceUrl": plan_item.source_media_url,
                            }
                        )
                        assets_repo.update(
                            org_id=org_id,
                            asset_id=generated_asset_id,
                            ai_metadata=generated_ai_metadata,
                        )
                        completed_image_plan_item_assets[plan_item.id] = generated_asset_id
                        created_asset_ids.append(generated_asset_id)
                        selected_swipe_sources.append(
                            {
                                "requirement_index": requirement_index,
                                "plan_item_id": plan_item.id,
                                "company_swipe_id": plan_item.company_swipe_id,
                                "swipe_source_label": plan_item.source_label,
                                "swipe_source_url": plan_item.source_media_url,
                                "swipe_requires_product_image": plan_item.product_image_policy,
                                "copy_pack_id": copy_pack.id,
                            }
                        )
                    continue

                elif normalized_format == "video":
                    if video_orchestrator is None:
                        raise RuntimeError("Video orchestration client was not initialized.")
                    for _variant_offset in range(allocation_count):
                        current_variant_index = variant_cursor
                        variant_cursor += 1

                        initial_message = build_initial_video_message(
                            creative_concept=creative_concept,
                            channel_id=channel_id,
                            requirement=req,
                            constraints=constraints,
                            tone_guidelines=tone_guidelines,
                            visual_guidelines=visual_guidelines,
                            product_asset_urls=product_asset_urls,
                        )
                        context_payload = {
                            "asset_brief_id": asset_brief_id,
                            "campaign_id": campaign_id,
                            "client_id": client_id,
                            "product_id": product_id,
                            "variant_index": current_variant_index,
                            "requirement_index": requirement_index,
                            "requirement": req,
                            "creative_concept": creative_concept,
                            "constraints": constraints,
                            "tone_guidelines": tone_guidelines,
                            "visual_guidelines": visual_guidelines,
                            "product_asset_urls": product_asset_urls,
                            "product_reference_asset_ids": image_reference_asset_ids,
                        }

                        session_key = _stable_idempotency_key(
                            org_id,
                            client_id,
                            str(campaign_id or ""),
                            asset_brief_id,
                            "video_session",
                            str(requirement_index),
                            str(current_variant_index),
                        )
                        turn_prefix = _stable_idempotency_key(
                            org_id,
                            client_id,
                            str(campaign_id or ""),
                            asset_brief_id,
                            "video_turn",
                            str(requirement_index),
                            str(current_variant_index),
                        )
                        existing_run = _get_existing_run_by_idempotency(session=session, idempotency_key=session_key)
                        if existing_run:
                            if existing_run.status != "succeeded":
                                raise RuntimeError(
                                    f"Existing video run is not reusable for idempotency key {session_key}. "
                                    f"status={existing_run.status} error={existing_run.error_detail}"
                                )
                            existing_asset_ids = _existing_output_asset_ids(
                                session=session,
                                run_id=str(existing_run.id),
                                output_kinds={"final_video"},
                            )
                            if not existing_asset_ids:
                                raise RuntimeError(
                                    f"Existing idempotent video run {existing_run.id} has no final_video local assets."
                                )
                            created_asset_ids.append(existing_asset_ids[0])
                            _record_run_event(
                                session=session,
                                run_id=str(existing_run.id),
                                retention_expires_at=existing_run.retention_expires_at,
                                event_type="video.session.reused",
                                status="succeeded",
                                payload={"reason": "idempotent_replay", "asset_id": existing_asset_ids[0]},
                            )
                            continue

                        run = CreativeServiceRun(
                            org_id=org_id,
                            client_id=client_id,
                            campaign_id=campaign_id,
                            product_id=product_id,
                            workflow_run_id=workflow_run_id,
                            asset_brief_id=asset_brief_id,
                            requirement_index=requirement_index,
                            variant_index=current_variant_index,
                            service_kind="video",
                            operation_kind="video_session",
                            status="queued",
                            idempotency_key=session_key,
                            request_payload={
                                "title": f"{asset_brief_id}-variant-{current_variant_index}",
                                "message": initial_message,
                                "context": context_payload,
                                "attachments": [
                                    attachment.model_dump(mode="json") for attachment in video_reference_attachments
                                ],
                            },
                            retention_expires_at=retention_expires_at,
                        )
                        session.add(run)
                        session.commit()
                        session.refresh(run)

                        _record_run_event(
                            session=session,
                            run_id=str(run.id),
                            retention_expires_at=retention_expires_at,
                            event_type="video.session.queued",
                            status="queued",
                            payload=run.request_payload,
                        )

                        try:
                            orchestrated = video_orchestrator.run_variant(
                                title=f"{asset_brief_id}-variant-{current_variant_index}",
                                initial_text=initial_message,
                                context=context_payload,
                                attachments=video_reference_attachments,
                                session_idempotency_key=session_key,
                                turn_idempotency_prefix=turn_prefix,
                            )
                        except VideoOrchestrationError as exc:
                            run.status = "failed"
                            run.error_detail = str(exc)
                            run.remote_session_id = exc.session_id
                            run.finished_at = datetime.now(timezone.utc)
                            run.updated_at = datetime.now(timezone.utc)
                            session.commit()

                            if exc.turns:
                                _upsert_turn_traces(
                                    session=session,
                                    run_id=str(run.id),
                                    traces=exc.turns,
                                    retention_expires_at=retention_expires_at,
                                )

                            _record_run_event(
                                session=session,
                                run_id=str(run.id),
                                retention_expires_at=retention_expires_at,
                                event_type="video.session.failed",
                                status="failed",
                                payload={"error": str(exc), "session_id": exc.session_id},
                            )
                            raise RuntimeError(
                                f"Video generation failed for brief {asset_brief_id} "
                                f"(variant_index={current_variant_index}): {exc}"
                            ) from exc
                        except Exception as exc:  # noqa: BLE001
                            run.status = "failed"
                            run.error_detail = str(exc)
                            run.finished_at = datetime.now(timezone.utc)
                            run.updated_at = datetime.now(timezone.utc)
                            session.commit()
                            _record_run_event(
                                session=session,
                                run_id=str(run.id),
                                retention_expires_at=retention_expires_at,
                                event_type="video.session.failed",
                                status="failed",
                                payload={"error": str(exc), "session_id": run.remote_session_id},
                            )
                            raise RuntimeError(
                                f"Video generation failed for brief {asset_brief_id} "
                                f"(variant_index={current_variant_index}): {exc}"
                            ) from exc

                        turn_id_map = _upsert_turn_traces(
                            session=session,
                            run_id=str(run.id),
                            traces=orchestrated.turns,
                            retention_expires_at=retention_expires_at,
                        )

                        run.remote_session_id = orchestrated.session_id
                        run.status = "succeeded"
                        run.response_payload = orchestrated.result.model_dump(mode="json")
                        run.started_at = (
                            orchestrated.turns[0].started_at if orchestrated.turns else datetime.now(timezone.utc)
                        )
                        run.finished_at = datetime.now(timezone.utc)
                        run.updated_at = datetime.now(timezone.utc)
                        session.commit()

                        _record_run_event(
                            session=session,
                            run_id=str(run.id),
                            retention_expires_at=retention_expires_at,
                            event_type="video.session.completed",
                            status="succeeded",
                            payload=orchestrated.result.model_dump(mode="json"),
                        )

                        try:
                            final_video = orchestrated.result.final_video
                            if not final_video or not final_video.primary_url:
                                raise RuntimeError(
                                    f"Video result missing final_video.primary_url for brief {asset_brief_id} "
                                    f"(variant_index={current_variant_index}, session_id={orchestrated.session_id})"
                                )

                            final_turn_id = turn_id_map.get(orchestrated.turns[-1].turn_id) if orchestrated.turns else None
                            local_video_asset_id = _create_generated_asset_from_url(
                                session=session,
                                org_id=org_id,
                                client_id=client_id,
                                campaign_id=campaign_id,
                                product_id=product_id,
                                funnel_id=funnel_id,
                                brief_artifact_id=brief_artifact_id,
                                asset_brief_id=asset_brief_id,
                                variant_id=variant_id,
                                variant_index=current_variant_index,
                                channel_id=channel_id.strip(),
                                fmt=fmt.strip(),
                                requirement_index=requirement_index,
                                requirement=req,
                                primary_url=final_video.primary_url,
                                prompt=initial_message,
                                source_kind="video_output",
                                expected_asset_kind="video",
                                retention_expires_at=retention_expires_at,
                                extra_ai_metadata={
                                    "remoteSessionId": orchestrated.session_id,
                                    "remoteTurnIds": [trace.turn_id for trace in orchestrated.turns],
                                    "remoteAssetId": final_video.asset_id,
                                },
                                attach_to_product=True,
                            )
                            created_asset_ids.append(local_video_asset_id)
                            _record_output(
                                session=session,
                                run_id=str(run.id),
                                turn_id=final_turn_id,
                                retention_expires_at=retention_expires_at,
                                output_kind="final_video",
                                output_index=current_variant_index,
                                remote_asset_id=final_video.asset_id,
                                primary_uri=final_video.primary_uri,
                                primary_url=final_video.primary_url,
                                prompt_used=final_video.prompt_used,
                                local_asset_id=local_video_asset_id,
                                metadata={"requirementIndex": requirement_index, "variantIndex": current_variant_index},
                            )

                            pins = (orchestrated.result.project.pins if orchestrated.result.project else {}) or {}
                            for pin_name, pin_value in pins.items():
                                pin_url: str | None = None
                                pin_uri: str | None = None
                                pin_asset_id: str | None = None

                                if isinstance(pin_value, dict):
                                    raw_url = pin_value.get("primary_url")
                                    if isinstance(raw_url, str) and raw_url.strip():
                                        pin_url = raw_url.strip()
                                    raw_uri = pin_value.get("primary_uri")
                                    if isinstance(raw_uri, str) and raw_uri.strip():
                                        pin_uri = raw_uri.strip()
                                    raw_asset_id = pin_value.get("asset_id")
                                    if isinstance(raw_asset_id, str) and raw_asset_id.strip():
                                        pin_asset_id = raw_asset_id.strip()
                                elif isinstance(pin_value, str) and pin_value.startswith("http"):
                                    pin_url = pin_value

                                local_pin_asset_id: str | None = None
                                if pin_url:
                                    local_pin_asset_id = _create_generated_asset_from_url(
                                        session=session,
                                        org_id=org_id,
                                        client_id=client_id,
                                        campaign_id=campaign_id,
                                        product_id=product_id,
                                        funnel_id=funnel_id,
                                        brief_artifact_id=brief_artifact_id,
                                        asset_brief_id=asset_brief_id,
                                        variant_id=variant_id,
                                        variant_index=None,
                                        channel_id=channel_id.strip(),
                                        fmt=fmt.strip(),
                                        requirement_index=requirement_index,
                                        requirement=req,
                                        primary_url=pin_url,
                                        prompt=initial_message,
                                        source_kind=f"video_pin_{pin_name}",
                                        expected_asset_kind=None,
                                        retention_expires_at=retention_expires_at,
                                        extra_ai_metadata={
                                            "remoteSessionId": orchestrated.session_id,
                                            "pinName": pin_name,
                                        },
                                        attach_to_product=False,
                                    )

                                _record_output(
                                    session=session,
                                    run_id=str(run.id),
                                    turn_id=final_turn_id,
                                    retention_expires_at=retention_expires_at,
                                    output_kind=f"pin:{pin_name}",
                                    output_index=None,
                                    remote_asset_id=pin_asset_id,
                                    primary_uri=pin_uri,
                                    primary_url=pin_url,
                                    prompt_used=None,
                                    local_asset_id=local_pin_asset_id,
                                    metadata={"pinName": pin_name},
                                )
                        except Exception as exc:  # noqa: BLE001
                            run.status = "failed"
                            run.error_detail = str(exc)
                            run.finished_at = datetime.now(timezone.utc)
                            run.updated_at = datetime.now(timezone.utc)
                            session.commit()
                            _record_run_event(
                                session=session,
                                run_id=str(run.id),
                                retention_expires_at=retention_expires_at,
                                event_type="video.session.failed",
                                status="failed",
                                payload={"error": str(exc), "session_id": orchestrated.session_id},
                            )
                            raise

            log_activity(
                "asset_generation",
                "completed",
                payload_out={"asset_brief_id": asset_brief_id, "asset_ids": created_asset_ids},
            )
            return {"asset_ids": created_asset_ids}
    except Exception as exc:
        log_activity(
            "asset_generation",
            "failed",
            error=_summarize_exception_message(exc),
        )
        raise


@activity.defn
def persist_assets_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    campaign_id = params.get("campaign_id")
    assets = params.get("assets", [])
    asset_brief_id = params.get("asset_brief_id")
    if not asset_brief_id:
        raise ValueError("asset_brief_id is required to persist assets")
    if not assets:
        raise ValueError("assets are required to persist assets")

    brief = None
    brief_artifact_id = None
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
                    brief = entry
                    brief_artifact_id = art.id
                    break
            if brief:
                break

        if not brief:
            raise ValueError(f"Asset brief not found: {asset_brief_id}")

        funnel_id = brief.get("funnelId")
        if campaign_id and not funnel_id:
            raise ValueError("Asset brief is missing funnelId; assign a funnel before generating assets.")
        if funnel_id:
            funnel = session.scalars(
                select(Funnel).where(Funnel.org_id == org_id, Funnel.id == funnel_id)
            ).first()
            if not funnel:
                raise ValueError(f"Funnel not found for asset brief {asset_brief_id}")
            if str(funnel.client_id) != str(client_id):
                raise ValueError("Funnel must belong to the same client as the asset brief")
            if campaign_id and str(funnel.campaign_id) != str(campaign_id):
                raise ValueError("Funnel must belong to the same campaign as the asset brief")
            experiment_id = brief.get("experimentId")
            if experiment_id and funnel.experiment_spec_id and funnel.experiment_spec_id != experiment_id:
                raise ValueError("Funnel experiment does not match asset brief experiment")

        repo = _repo(session)
        created = []
        for asset in assets:
            created_asset = repo.create(
                org_id=org_id,
                client_id=client_id,
                campaign_id=campaign_id,
                channel_id=asset["channel_id"],
                format=asset["format"],
                content=asset["content"],
                source_type=asset.get("source_type", AssetSourceEnum.generated),
                asset_brief_artifact_id=brief_artifact_id,
                funnel_id=funnel_id,
            )
            created.append(str(created_asset.id))
        return {"assets": created}
