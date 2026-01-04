from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.models import Ad, AdAssetLink, Brand, MediaAsset, ResearchRun
from app.db.repositories.ads import AdsRepository
from app.services.media_storage import MediaStorage

router = APIRouter(prefix="/ads", tags=["ads"])


def _serialize_media(repo: AdsRepository, ad_id: str) -> list[dict]:
    """
    Attach media assets linked to this ad.
    """
    _, media_rows = repo.ad_with_media(ad_id)
    assets = []
    for media, role in media_rows:
        metadata = getattr(media, "metadata_json", {}) or {}
        asset_type = getattr(media, "asset_type", None)
        asset_type_value = getattr(asset_type, "value", None) if asset_type is not None else None
        preview_url = (
            f"/ads/{ad_id}/media/{media.id}/preview"
            if getattr(media, "preview_storage_key", None) or getattr(media, "storage_key", None)
            else None
        )
        media_url = f"/ads/{ad_id}/media/{media.id}" if getattr(media, "storage_key", None) else None
        assets.append(
            {
                "id": str(getattr(media, "id", "")),
                "role": role,
                "asset_type": asset_type_value or str(asset_type) if asset_type else None,
                "source_url": getattr(media, "source_url", None),
                "stored_url": getattr(media, "stored_url", None),
                "storage_key": getattr(media, "storage_key", None),
                "preview_storage_key": getattr(media, "preview_storage_key", None),
                "mirror_status": getattr(media, "mirror_status", None),
                "mime_type": getattr(media, "mime_type", None),
                "width": getattr(media, "width", None),
                "height": getattr(media, "height", None),
                "duration_ms": getattr(media, "duration_ms", None),
                "thumbnail_url": metadata.get("thumbnail_url") or metadata.get("preview_url") or preview_url,
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
    key = media.preview_storage_key or media.storage_key
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


@router.get("")
def list_ads(
  clientId: str | None = None,
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
  elif clientId:
    research_run = repo.latest_research_run_for_client(org_id=auth.org_id, client_id=clientId)
    if not research_run:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No research run found for client")
  else:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="clientId or researchRunId is required")

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
