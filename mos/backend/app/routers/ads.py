from __future__ import annotations

from functools import lru_cache
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import AdIngestStatusEnum, MediaAssetTypeEnum
from app.db.models import Ad, AdAssetLink, AdIngestRun, Brand, BrandChannelIdentity, MediaAsset, ResearchRun
from app.db.repositories.ads import AdsRepository
from app.schemas.ads_ingestion import AdsIngestionRetryRequest
from app.services.ads_ingestion_report import AdsIngestionReportService
from app.services.media_storage import MediaStorage
from app.temporal.client import get_temporal_client
from app.temporal.workflows.ads_ingestion import AdsIngestionRetryInput, AdsIngestionRetryWorkflow

router = APIRouter(prefix="/ads", tags=["ads"])


def _serialize_media(repo: AdsRepository, ad_id: str) -> list[dict]:
    """
    Attach media assets linked to this ad.
    """
    storage = _media_storage()
    _, media_rows = repo.ad_with_media(ad_id)
    assets = []
    for media, role in media_rows:
        metadata = getattr(media, "metadata_json", {}) or {}
        asset_type = getattr(media, "asset_type", None)
        asset_type_value = getattr(asset_type, "value", None) if asset_type is not None else None
        is_video = asset_type == MediaAssetTypeEnum.VIDEO
        preview_key = getattr(media, "preview_storage_key", None)
        # Never fall back to the original video file for previews (it will be rendered as <img>).
        if not preview_key and not is_video:
            preview_key = getattr(media, "storage_key", None)
        media_key = getattr(media, "storage_key", None)
        preview_bucket = getattr(media, "preview_bucket", None) or getattr(media, "bucket", None) or storage.preview_bucket
        media_bucket = getattr(media, "bucket", None) or storage.bucket
        preview_url = storage.presign_get(bucket=preview_bucket, key=preview_key) if preview_key else None
        media_url = storage.presign_get(bucket=media_bucket, key=media_key) if media_key else None
        mirror_status_raw = getattr(media, "mirror_status", None)
        mirror_status = (
            getattr(mirror_status_raw, "value", None)
            if mirror_status_raw is not None
            else None
        ) or (str(mirror_status_raw) if mirror_status_raw is not None else None)
        mirror_error = getattr(media, "mirror_error", None)
        # If the original is stored but preview generation failed, the asset is still usable.
        if mirror_status == "failed" and mirror_error == "preview_generation_failed" and media_key:
            mirror_status = "partial"
        assets.append(
            {
                "id": str(getattr(media, "id", "")),
                "role": role,
                "asset_type": asset_type_value or str(asset_type) if asset_type else None,
                "source_url": getattr(media, "source_url", None),
                "stored_url": getattr(media, "stored_url", None),
                "storage_key": getattr(media, "storage_key", None),
                "preview_storage_key": getattr(media, "preview_storage_key", None),
                "mirror_status": mirror_status,
                "mirror_error": mirror_error,
                "mime_type": getattr(media, "mime_type", None),
                "width": getattr(media, "width", None),
                "height": getattr(media, "height", None),
                "duration_ms": getattr(media, "duration_ms", None),
                # Prefer the mirrored preview when available; external thumbnail URLs can expire.
                "thumbnail_url": preview_url or metadata.get("thumbnail_url") or metadata.get("preview_url"),
                "preview_url": preview_url,
                "media_url": media_url,
                "metadata": metadata,
            }
        )
    return assets


@lru_cache()
def _media_storage() -> MediaStorage:
    return MediaStorage()


def _fetch_media_for_ad(
    *, session: Session, ad_id: str, media_asset_id: str, org_id: str
) -> MediaAsset:
    media = (
        session.query(MediaAsset)
        .join(AdAssetLink, AdAssetLink.media_asset_id == MediaAsset.id)
        .join(Ad, Ad.id == AdAssetLink.ad_id)
        .join(Brand, Brand.id == Ad.brand_id)
        .filter(Ad.id == ad_id, MediaAsset.id == media_asset_id, Brand.org_id == org_id)
        .first()
    )
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return media


@router.get("/{ad_id}/media/{media_asset_id}/preview")
def redirect_media_preview(
    ad_id: str,
    media_asset_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    media = _fetch_media_for_ad(session=session, ad_id=ad_id, media_asset_id=media_asset_id, org_id=auth.org_id)
    # Only return an actual preview image for videos; do not fall back to the video itself.
    key = media.preview_storage_key
    if not key and getattr(media, "asset_type", None) in (MediaAssetTypeEnum.IMAGE, MediaAssetTypeEnum.SCREENSHOT):
        key = media.storage_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview unavailable")
    storage = _media_storage()
    bucket = media.preview_bucket or media.bucket or storage.preview_bucket
    url = storage.presign_get(bucket=bucket, key=key)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/{ad_id}/media/{media_asset_id}")
def redirect_media_original(
    ad_id: str,
    media_asset_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    media = _fetch_media_for_ad(session=session, ad_id=ad_id, media_asset_id=media_asset_id, org_id=auth.org_id)
    key = media.storage_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media unavailable")
    storage = _media_storage()
    bucket = media.bucket or storage.bucket
    url = storage.presign_get(bucket=bucket, key=key)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/ingestion/retry")
async def retry_ads_ingestion(
    body: AdsIngestionRetryRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    research_run = session.get(ResearchRun, body.research_run_id)
    if not research_run or research_run.org_id != auth.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")

    retry_identity_ids = body.brand_channel_identity_ids
    if not retry_identity_ids and body.failed_only:
        # Retry only identities whose latest ingest run is FAILED.
        runs = list(
            session.scalars(
                select(AdIngestRun)
                .where(AdIngestRun.research_run_id == str(research_run.id))
                .order_by(AdIngestRun.started_at.desc())
            ).all()
        )
        latest_by_identity: dict[str, AdIngestRun] = {}
        for run in runs:
            identity_id = str(getattr(run, "brand_channel_identity_id", "") or "")
            if not identity_id or identity_id in latest_by_identity:
                continue
            latest_by_identity[identity_id] = run

        retry_identity_ids = [
            identity_id
            for identity_id, run in latest_by_identity.items()
            if getattr(run, "status", None) == AdIngestStatusEnum.FAILED
        ]
        if not retry_identity_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No failed ingest runs found for this research run; nothing to retry.",
            )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        AdsIngestionRetryWorkflow.run,
        AdsIngestionRetryInput(
            research_run_id=str(research_run.id),
            results_limit=body.results_limit,
            brand_channel_identity_ids=retry_identity_ids,
            run_creative_analysis=body.run_creative_analysis,
            creative_analysis_max_ads=body.creative_analysis_max_ads,
            creative_analysis_concurrency=body.creative_analysis_concurrency,
            org_id=auth.org_id,
            client_id=research_run.client_id,
        ),
        id=f"ads-ingestion-retry-{research_run.id}-{uuid.uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    return {
        "research_run_id": str(research_run.id),
        "temporal_workflow_id": handle.id,
        "temporal_run_id": handle.first_execution_run_id,
        "brand_channel_identity_ids": retry_identity_ids,
    }


@router.get("/ingestion/runs")
def list_ingestion_runs(
    research_run_id: str = Query(..., alias="researchRunId"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    research_run = session.get(ResearchRun, research_run_id)
    if not research_run or research_run.org_id != auth.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")

    rows = list(
        session.execute(
            select(AdIngestRun, BrandChannelIdentity, Brand)
            .join(BrandChannelIdentity, BrandChannelIdentity.id == AdIngestRun.brand_channel_identity_id)
            .join(Brand, Brand.id == BrandChannelIdentity.brand_id)
            .where(AdIngestRun.research_run_id == str(research_run.id))
            .order_by(AdIngestRun.started_at.desc())
        ).all()
    )

    items: list[dict] = []
    for ingest_run, identity, brand in rows:
        status_raw = getattr(ingest_run, "status", None)
        status_value = (
            getattr(status_raw, "value", None)
            if status_raw is not None
            else None
        ) or (str(status_raw) if status_raw is not None else None)
        items.append(
            {
                "ad_ingest_run_id": str(getattr(ingest_run, "id", "")),
                "research_run_id": str(getattr(ingest_run, "research_run_id", "")),
                "brand_channel_identity_id": str(getattr(ingest_run, "brand_channel_identity_id", "")),
                "brand_id": str(getattr(identity, "brand_id", "")),
                "brand_name": getattr(brand, "canonical_name", None) or getattr(brand, "normalized_name", None),
                "channel": getattr(getattr(ingest_run, "channel", None), "value", None)
                or str(getattr(ingest_run, "channel", "")),
                "requested_url": getattr(ingest_run, "requested_url", None),
                "provider": getattr(ingest_run, "provider", None),
                "provider_run_id": getattr(ingest_run, "provider_run_id", None),
                "provider_dataset_id": getattr(ingest_run, "provider_dataset_id", None),
                "status": status_value,
                "is_partial": bool(getattr(ingest_run, "is_partial", False)),
                "results_limit": getattr(ingest_run, "results_limit", None),
                "items_count": int(getattr(ingest_run, "items_count", 0) or 0),
                "error": getattr(ingest_run, "error", None),
                "started_at": ingest_run.started_at.isoformat() if getattr(ingest_run, "started_at", None) else None,
                "finished_at": ingest_run.finished_at.isoformat() if getattr(ingest_run, "finished_at", None) else None,
            }
        )

    return jsonable_encoder(
        {
            "research_run_id": str(research_run.id),
            "count": len(items),
            "items": items,
        }
    )


@router.get("/ingestion/report")
def get_ingestion_report(
    research_run_id: str = Query(..., alias="researchRunId"),
    limit_failed_media_samples: int = Query(default=20, ge=0, le=200, alias="limitFailedMediaSamples"),
    limit_failed_run_samples: int = Query(default=50, ge=0, le=500, alias="limitFailedRunSamples"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    research_run = session.get(ResearchRun, research_run_id)
    if not research_run or research_run.org_id != auth.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")

    report = AdsIngestionReportService(session).build_report(
        research_run_id=str(research_run.id),
        limit_failed_media_samples=limit_failed_media_samples,
        limit_failed_run_samples=limit_failed_run_samples,
    )

    return jsonable_encoder(
        {
            "research_run_id": report.research_run_id,
            "generated_at_iso": report.generated_at_iso,
            "summary": report.summary,
            "ingest_runs": report.ingest_runs,
            "media_mirror": report.media_mirror,
        }
    )


@router.get("")
def list_ads(
  clientId: str | None = None,
  productId: str | None = None,
  researchRunId: str | None = None,
  limit: int = Query(default=60, ge=1, le=200),
  offset: int = Query(default=0, ge=0),
  auth: AuthContext = Depends(get_current_user),
  session: Session = Depends(get_session),
):
  repo = AdsRepository(session)

  research_run: ResearchRun | None = None
  if researchRunId:
    research_run = session.get(ResearchRun, researchRunId)
    if not research_run or research_run.org_id != auth.org_id:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")
  elif clientId and productId:
    research_run = repo.latest_research_run_for_product(
        org_id=auth.org_id, client_id=clientId, product_id=productId
    )
    if not research_run:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No research run found for product")
  else:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="productId and clientId are required unless researchRunId is provided",
    )

  ads = repo.ads_for_run(str(research_run.id))
  if offset:
    ads = ads[offset:]
  if limit:
    ads = ads[:limit]

  brand_ids = {ad.brand_id for ad in ads if getattr(ad, "brand_id", None)}
  brands = {}
  if brand_ids:
    brands = {str(b.id): b for b in session.query(Brand).filter(Brand.id.in_(brand_ids)).all()}

  serialized = []
  for ad in ads:
    media_assets = _serialize_media(repo, str(ad.id))
    brand_name = None
    b = brands.get(str(ad.brand_id))
    if b:
      brand_name = getattr(b, "canonical_name", None) or getattr(b, "normalized_name", None)

    serialized.append(
      {
        "ad_id": str(ad.id),
        "brand_id": ad.brand_id,
        "brand_name": brand_name,
        "channel": getattr(ad.channel, "value", str(ad.channel)),
        "ad_status": getattr(ad.ad_status, "value", str(ad.ad_status)),
        "cta_type": ad.cta_type,
        "cta_text": ad.cta_text,
        "landing_url": ad.landing_url,
        "destination_domain": ad.destination_domain,
        "headline": ad.headline,
        "primary_text": ad.body_text,
        "start_date": ad.started_running_at.isoformat() if ad.started_running_at else None,
        "end_date": ad.ended_running_at.isoformat() if ad.ended_running_at else None,
        "media_assets": media_assets,
        "raw_json": ad.raw_json,
        "research_run_id": str(research_run.id),
      }
    )

  return jsonable_encoder({"ads": serialized, "research_run_id": str(research_run.id), "count": len(serialized)})
