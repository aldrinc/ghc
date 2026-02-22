from __future__ import annotations

import concurrent.futures
import hashlib
import io
import mimetypes
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence

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
from app.db.repositories.products import ProductsRepository
from app.db.repositories.swipes import ClientSwipesRepository, CompanySwipesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.creative_service import CreativeServiceImageAdsCreateIn
from app.schemas.creative_service import CreativeServiceVideoAttachmentIn
from app.services.creative_service_client import (
    CreativeServiceClient,
    CreativeServiceConfigError,
    CreativeServiceRequestError,
)
from app.services.design_systems import resolve_design_system_tokens
from app.services.media_storage import IMMUTABLE_CACHE_CONTROL, MediaStorage
from app.services.video_ads_orchestrator import (
    VideoAdsOrchestrator,
    VideoOrchestrationError,
    VideoTurnTrace,
    build_initial_video_message,
)

_IMAGE_TERMINAL_STATUSES = {"succeeded", "failed"}
_SUPPORTED_FORMATS = {"image", "video"}


@dataclass(frozen=True)
class _ProductReferenceAsset:
    local_asset_id: str
    primary_url: str
    title: str | None
    remote_asset_id: str | None


@dataclass(frozen=True)
class _SwipeCandidate:
    company_swipe_id: str


def _repo(session) -> AssetsRepository:
    return AssetsRepository(session)


def _stable_idempotency_key(*parts: str) -> str:
    payload = "|".join(parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:48]


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


def _load_swipe_candidates(*, session, org_id: str, client_id: str) -> list[_SwipeCandidate]:
    client_swipes = ClientSwipesRepository(session).list(org_id=org_id, client_id=client_id)
    if not client_swipes:
        raise ValueError(
            "Swipe-only creative generation requires client swipe entries. "
            "Save at least one swipe for this client before producing creative."
        )

    company_repo = CompanySwipesRepository(session)
    candidates: list[_SwipeCandidate] = []
    seen_company_ids: set[str] = set()

    for entry in client_swipes:
        company_swipe_id = str(entry.company_swipe_id or "").strip()
        if not company_swipe_id:
            continue
        if company_swipe_id in seen_company_ids:
            continue

        company_asset = company_repo.get_asset(org_id=org_id, swipe_id=company_swipe_id)
        if not company_asset:
            continue
        media = company_repo.list_media(org_id=org_id, swipe_asset_id=company_swipe_id)
        has_usable_media = any(
            isinstance((item.download_url or item.url or item.thumbnail_url), str)
            and str(item.download_url or item.url or item.thumbnail_url).strip()
            for item in media
        )
        if not has_usable_media:
            continue

        candidates.append(
            _SwipeCandidate(
                company_swipe_id=company_swipe_id,
            )
        )
        seen_company_ids.add(company_swipe_id)

    if not candidates:
        raise ValueError(
            "Swipe-only creative generation requires at least one client swipe mapped to a company swipe with media."
        )

    return candidates


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


def _build_image_reference_text(references: Sequence[_ProductReferenceAsset]) -> str:
    lines = [
        "Use the following product reference images as the source of truth for product appearance and fit.",
    ]
    for idx, reference in enumerate(references, start=1):
        label = reference.title or f"Product reference {idx}"
        lines.append(f"{idx}. {label}: {reference.primary_url}")
    return "\n".join(lines)


def _create_generated_asset_from_url(
    *,
    session,
    org_id: str,
    client_id: str,
    campaign_id: str | None,
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

    try:
        creative_client = CreativeServiceClient()
    except CreativeServiceConfigError as exc:
        raise RuntimeError(str(exc)) from exc

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

        total_assets_per_brief = int(settings.CREATIVE_SERVICE_ASSETS_PER_BRIEF or 6)
        requirement_allocations = _split_requirement_asset_counts(requirements, total_assets_per_brief)

        swipe_candidates = _load_swipe_candidates(
            session=session,
            org_id=org_id,
            client_id=client_id,
        )
        swipe_parallelism = int(os.getenv("SWIPE_BRIEF_MAX_CONCURRENCY", "4"))
        if swipe_parallelism <= 0:
            raise ValueError("SWIPE_BRIEF_MAX_CONCURRENCY must be greater than zero.")
        from app.temporal.activities.swipe_image_ad_activities import generate_swipe_image_ad_activity

        created_asset_ids: list[str] = []
        for requirement_index, req, _allocation_count in requirement_allocations:
            fmt = req.get("format") or "image"
            if not isinstance(fmt, str) or not fmt.strip():
                raise ValueError("Asset requirement format must be a non-empty string.")
            normalized_format = fmt.strip().lower()
            if normalized_format != "image":
                raise ValueError(
                    "Swipe-only creative generation currently supports image requirements only. "
                    f"Unsupported format={fmt!r} for requirementIndex={requirement_index}."
                )

            future_to_swipe_id: dict[concurrent.futures.Future, str] = {}
            max_workers = min(swipe_parallelism, len(swipe_candidates))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                for swipe_candidate in swipe_candidates:
                    future = executor.submit(
                        generate_swipe_image_ad_activity,
                        {
                            "org_id": org_id,
                            "client_id": client_id,
                            "product_id": product_id,
                            "campaign_id": campaign_id,
                            "asset_brief_id": asset_brief_id,
                            "requirement_index": requirement_index,
                            "company_swipe_id": swipe_candidate.company_swipe_id,
                            "count": 1,
                            "workflow_run_id": workflow_run_id,
                        },
                    )
                    future_to_swipe_id[future] = swipe_candidate.company_swipe_id

                for future in concurrent.futures.as_completed(future_to_swipe_id):
                    company_swipe_id = future_to_swipe_id[future]
                    try:
                        swipe_result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        for pending in future_to_swipe_id:
                            if not pending.done():
                                pending.cancel()
                        raise RuntimeError(
                            "Swipe image ad generation failed "
                            f"(asset_brief_id={asset_brief_id}, requirement_index={requirement_index}, "
                            f"company_swipe_id={company_swipe_id})."
                        ) from exc

                generated_ids = swipe_result.get("asset_ids") if isinstance(swipe_result, dict) else None
                if not isinstance(generated_ids, list) or not generated_ids:
                    raise RuntimeError(
                        "Swipe image ad generation returned no asset_ids "
                        f"(asset_brief_id={asset_brief_id}, requirement_index={requirement_index}, "
                        f"company_swipe_id={company_swipe_id})."
                    )
                created_asset_ids.extend([str(asset_id) for asset_id in generated_ids if asset_id])

        if not created_asset_ids:
            raise RuntimeError(f"No swipe-based assets were generated for brief {asset_brief_id}.")

        log_activity(
            "asset_generation",
            "completed",
            payload_out={
                "asset_brief_id": asset_brief_id,
                "asset_ids": created_asset_ids,
                "mode": "swipe_only",
            },
        )
        return {"asset_ids": created_asset_ids}

        variant_id = brief.get("variantId") or brief.get("variant_id")
        constraints = [item for item in (brief.get("constraints") or []) if isinstance(item, str)]
        tone_guidelines = [item for item in (brief.get("toneGuidelines") or []) if isinstance(item, str)]
        visual_guidelines = [item for item in (brief.get("visualGuidelines") or []) if isinstance(item, str)]
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
        image_reference_text = _build_image_reference_text(product_reference_assets)
        if logo_reference_asset:
            image_reference_text = "\n\n".join(
                [
                    image_reference_text,
                    f"Brand logo reference (optional, use if adding a logo): {logo_reference_asset.primary_url}",
                ]
            ).strip()
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
        reference_signature = _stable_idempotency_key("image_reference_assets_v3", *image_reference_asset_ids)

        retention_expires_at = _retention_expires_at()
        created_asset_ids: list[str] = []
        variant_cursor = 0

        video_orchestrator = VideoAdsOrchestrator(client=creative_client)

        for requirement_index, req, allocation_count in requirement_allocations:
            channel_id = req.get("channel") or "meta"
            fmt = req.get("format") or "image"
            if not isinstance(channel_id, str) or not channel_id.strip():
                raise ValueError("Asset requirement channel must be a non-empty string.")
            if not isinstance(fmt, str) or not fmt.strip():
                raise ValueError("Asset requirement format must be a non-empty string.")

            normalized_format = fmt.strip().lower()
            if normalized_format not in _SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported creative brief format '{fmt}'. Supported formats: {sorted(_SUPPORTED_FORMATS)}."
                )

            if normalized_format == "image":
                prompt = _build_image_prompt(
                    creative_concept=creative_concept,
                    channel_id=channel_id,
                    requirement=req,
                    constraints=constraints,
                    tone_guidelines=tone_guidelines,
                    visual_guidelines=visual_guidelines,
                )
                idempotency_key = _stable_idempotency_key(
                    org_id,
                    client_id,
                    str(campaign_id or ""),
                    asset_brief_id,
                    "image",
                    str(requirement_index),
                    str(allocation_count),
                    reference_signature,
                )
                existing_run = _get_existing_run_by_idempotency(session=session, idempotency_key=idempotency_key)
                if existing_run:
                    if existing_run.status != "succeeded":
                        raise RuntimeError(
                            f"Existing image run is not reusable for idempotency key {idempotency_key}. "
                            f"status={existing_run.status} error={existing_run.error_detail}"
                        )
                    existing_asset_ids = _existing_output_asset_ids(
                        session=session,
                        run_id=str(existing_run.id),
                        output_kinds={"output"},
                    )
                    if len(existing_asset_ids) < allocation_count:
                        raise RuntimeError(
                            f"Existing idempotent image run {existing_run.id} has insufficient outputs. "
                            f"expected_at_least={allocation_count} actual={len(existing_asset_ids)}"
                        )
                    created_asset_ids.extend(existing_asset_ids[:allocation_count])
                    variant_cursor += allocation_count
                    _record_run_event(
                        session=session,
                        run_id=str(existing_run.id),
                        retention_expires_at=existing_run.retention_expires_at,
                        event_type="image.request.reused",
                        status="succeeded",
                        payload={"reason": "idempotent_replay", "asset_ids": existing_asset_ids[:allocation_count]},
                    )
                    continue

                image_payload = CreativeServiceImageAdsCreateIn(
                    prompt=prompt,
                    reference_text=image_reference_text,
                    reference_asset_ids=image_reference_asset_ids,
                    count=max(6, allocation_count),
                    aspect_ratio="1:1",
                    client_request_id=idempotency_key,
                )

                run = CreativeServiceRun(
                    org_id=org_id,
                    client_id=client_id,
                    campaign_id=campaign_id,
                    product_id=product_id,
                    workflow_run_id=workflow_run_id,
                    asset_brief_id=asset_brief_id,
                    requirement_index=requirement_index,
                    variant_index=variant_cursor,
                    service_kind="image",
                    operation_kind="image_ads",
                    status="queued",
                    idempotency_key=idempotency_key,
                    request_payload=image_payload.model_dump(mode="json"),
                    retention_expires_at=retention_expires_at,
                )
                session.add(run)
                session.commit()
                session.refresh(run)

                _record_run_event(
                    session=session,
                    run_id=str(run.id),
                    retention_expires_at=retention_expires_at,
                    event_type="image.request.queued",
                    status="queued",
                    payload=image_payload.model_dump(mode="json"),
                )

                try:
                    created_job = creative_client.create_image_ads(
                        payload=image_payload,
                        idempotency_key=idempotency_key,
                    )
                except (CreativeServiceRequestError, RuntimeError) as exc:
                    run.status = "failed"
                    run.error_detail = str(exc)
                    run.finished_at = datetime.now(timezone.utc)
                    run.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    _record_run_event(
                        session=session,
                        run_id=str(run.id),
                        retention_expires_at=retention_expires_at,
                        event_type="image.request.failed",
                        status="failed",
                        payload={"error": str(exc)},
                    )
                    raise RuntimeError(f"Image ad generation request failed for brief {asset_brief_id}: {exc}") from exc

                run.remote_job_id = created_job.id
                run.status = created_job.status
                run.response_payload = created_job.model_dump(mode="json")
                run.started_at = datetime.now(timezone.utc)
                run.updated_at = datetime.now(timezone.utc)
                session.commit()

                _record_run_event(
                    session=session,
                    run_id=str(run.id),
                    retention_expires_at=retention_expires_at,
                    event_type="image.request.accepted",
                    status=created_job.status,
                    payload=created_job.model_dump(mode="json"),
                )

                completed_job = _wait_for_image_job(
                    creative_client=creative_client,
                    job_id=created_job.id,
                    run=run,
                    session=session,
                    retention_expires_at=retention_expires_at,
                )

                if completed_job.status != "succeeded":
                    run.status = "failed"
                    run.error_detail = completed_job.error_detail or "Image generation failed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.updated_at = datetime.now(timezone.utc)
                    session.commit()
                    raise RuntimeError(
                        f"Image generation failed for brief {asset_brief_id} "
                        f"(job_id={completed_job.id}): {run.error_detail}"
                    )

                try:
                    if len(completed_job.outputs) < allocation_count:
                        raise RuntimeError(
                            f"Image generation returned fewer outputs than requested for brief {asset_brief_id}. "
                            f"requested={allocation_count} returned={len(completed_job.outputs)}"
                        )

                    for local_index, output in enumerate(completed_job.outputs[:allocation_count]):
                        if not output.primary_url:
                            raise RuntimeError(
                                f"Image generation output missing primary_url for brief {asset_brief_id} "
                                f"(job_id={completed_job.id}, output_index={local_index})"
                            )

                        local_asset_id = _create_generated_asset_from_url(
                            session=session,
                            org_id=org_id,
                            client_id=client_id,
                            campaign_id=campaign_id,
                            product_id=product_id,
                            funnel_id=funnel_id,
                            brief_artifact_id=brief_artifact_id,
                            asset_brief_id=asset_brief_id,
                            variant_id=variant_id,
                            variant_index=variant_cursor,
                            channel_id=channel_id.strip(),
                            fmt=fmt.strip(),
                            requirement_index=requirement_index,
                            requirement=req,
                            primary_url=output.primary_url,
                            prompt=prompt,
                            source_kind="image_output",
                            expected_asset_kind="image",
                            retention_expires_at=retention_expires_at,
                            extra_ai_metadata={
                                "remoteJobId": completed_job.id,
                                "remoteOutputIndex": output.output_index,
                                "remoteAssetId": output.asset_id,
                                "promptUsed": output.prompt_used,
                            },
                            attach_to_product=True,
                        )
                        created_asset_ids.append(local_asset_id)
                        _record_output(
                            session=session,
                            run_id=str(run.id),
                            turn_id=None,
                            retention_expires_at=retention_expires_at,
                            output_kind="output",
                            output_index=output.output_index if output.output_index is not None else local_index,
                            remote_asset_id=output.asset_id,
                            primary_uri=output.primary_uri,
                            primary_url=output.primary_url,
                            prompt_used=output.prompt_used,
                            local_asset_id=local_asset_id,
                            metadata={"requirementIndex": requirement_index, "variantIndex": variant_cursor},
                        )
                        variant_cursor += 1

                    for ref_idx, reference in enumerate(completed_job.references):
                        if not reference.primary_url:
                            continue
                        ref_asset_id = _create_generated_asset_from_url(
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
                            primary_url=reference.primary_url,
                            prompt=prompt,
                            source_kind="image_reference",
                            expected_asset_kind="image",
                            retention_expires_at=retention_expires_at,
                            extra_ai_metadata={
                                "remoteJobId": completed_job.id,
                                "remoteReferenceIndex": ref_idx,
                                "remoteAssetId": reference.asset_id,
                            },
                            attach_to_product=False,
                        )
                        _record_output(
                            session=session,
                            run_id=str(run.id),
                            turn_id=None,
                            retention_expires_at=retention_expires_at,
                            output_kind="reference",
                            output_index=reference.position if reference.position is not None else ref_idx,
                            remote_asset_id=reference.asset_id,
                            primary_uri=reference.primary_uri,
                            primary_url=reference.primary_url,
                            prompt_used=None,
                            local_asset_id=ref_asset_id,
                            metadata={"requirementIndex": requirement_index},
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
                        event_type="image.request.failed",
                        status="failed",
                        payload={"error": str(exc)},
                    )
                    raise

                run.status = "succeeded"
                run.finished_at = datetime.now(timezone.utc)
                run.updated_at = datetime.now(timezone.utc)
                run.response_payload = completed_job.model_dump(mode="json")
                session.commit()
                _record_run_event(
                    session=session,
                    run_id=str(run.id),
                    retention_expires_at=retention_expires_at,
                    event_type="image.request.completed",
                    status="succeeded",
                    payload=completed_job.model_dump(mode="json"),
                )

            elif normalized_format == "video":
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
                            "attachments": [attachment.model_dump(mode="json") for attachment in video_reference_attachments],
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
                    run.started_at = orchestrated.turns[0].started_at if orchestrated.turns else datetime.now(timezone.utc)
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
