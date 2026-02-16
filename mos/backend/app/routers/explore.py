from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from datetime import date
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import AdChannelEnum, AdStatusEnum, MediaAssetTypeEnum
from app.db.models import (
    Ad,
    AdFacts,
    AdAssetLink,
    AdScore,
    Brand,
    BrandUserPreference,
    MediaAsset,
    ResearchRun,
    ResearchRunBrand,
)
from app.db.repositories.ads import AdsRepository
from app.services.media_storage import MediaStorage

router = APIRouter(prefix="/explore", tags=["explore"])
_ALLOWED_AD_MEDIA_TYPES = {"IMAGE", "VIDEO"}

# Cache storage client to avoid rebuilding per request.
@lru_cache()
def _media_storage() -> MediaStorage:
    return MediaStorage()


@router.get("/brands")
def explore_brands(
    q: str | None = None,
    client_id: str | None = Query(default=None, alias="clientId"),
    product_id: str | None = Query(default=None, alias="productId"),
    research_run_id: str | None = Query(default=None, alias="researchRunId"),
    include_hidden: bool = Query(default=False, alias="includeHidden"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="last_seen"),
    direction: str = Query(default="desc"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = AdsRepository(session)

    scoped_brand_ids: set[str] | None = None
    run: ResearchRun | None = None
    if research_run_id:
        run = session.get(ResearchRun, research_run_id)
        if not run or str(run.org_id) != auth.org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")
    elif client_id or product_id:
        if not (client_id and product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clientId and productId are required together unless researchRunId is provided",
            )
        run = repo.latest_research_run_for_product(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
        )
        if not run:
            return jsonable_encoder({"items": [], "count": 0, "limit": limit, "offset": offset})

    if run:
        scoped_brand_ids = {
            str(row[0])
            for row in session.execute(
                select(ResearchRunBrand.brand_id).where(ResearchRunBrand.research_run_id == run.id)
            ).all()
        }
        if not scoped_brand_ids:
            return jsonable_encoder({"items": [], "count": 0, "limit": limit, "offset": offset})

    hidden_brand_ids = {
        str(row[0])
        for row in session.execute(
            select(BrandUserPreference.brand_id).where(
                BrandUserPreference.org_id == auth.org_id,
                BrandUserPreference.user_external_id == auth.user_id,
                BrandUserPreference.hidden.is_(True),
            )
        ).all()
    }

    filters = [Brand.org_id == auth.org_id]
    if scoped_brand_ids:
        filters.append(Brand.id.in_(scoped_brand_ids))
    if not include_hidden and hidden_brand_ids:
        filters.append(~Brand.id.in_(hidden_brand_ids))
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                Brand.canonical_name.ilike(pattern),
                Brand.normalized_name.ilike(pattern),
                Brand.primary_domain.ilike(pattern),
                Brand.primary_website_url.ilike(pattern),
            )
        )

    brand_stats = (
        select(
            Ad.brand_id.label("brand_id"),
            func.count().label("ad_count"),
            func.count().filter(Ad.ad_status == AdStatusEnum.active).label("active_count"),
            func.count().filter(Ad.ad_status == AdStatusEnum.inactive).label("inactive_count"),
            func.count().filter(Ad.ad_status == AdStatusEnum.unknown).label("unknown_count"),
            func.max(Ad.last_seen_at).label("last_seen_at"),
            func.min(Ad.first_seen_at).label("first_seen_at"),
            func.array_agg(func.distinct(Ad.channel)).label("channels"),
        )
        .join(Brand, Brand.id == Ad.brand_id)
        .where(*filters)
        .group_by(Ad.brand_id)
        .subquery()
    )

    hidden_expr = Brand.id.in_(hidden_brand_ids) if hidden_brand_ids else literal(False)

    base_query = (
        select(
            Brand.id.label("brand_id"),
            Brand.canonical_name.label("brand_name"),
            Brand.primary_domain.label("primary_domain"),
            Brand.primary_website_url.label("primary_website_url"),
            func.coalesce(brand_stats.c.ad_count, 0).label("ad_count"),
            func.coalesce(brand_stats.c.active_count, 0).label("active_count"),
            func.coalesce(brand_stats.c.inactive_count, 0).label("inactive_count"),
            func.coalesce(brand_stats.c.unknown_count, 0).label("unknown_count"),
            brand_stats.c.channels.label("channels"),
            brand_stats.c.first_seen_at.label("first_seen_at"),
            brand_stats.c.last_seen_at.label("last_seen_at"),
            hidden_expr.label("hidden"),
        )
        .select_from(Brand)
        .outerjoin(brand_stats, brand_stats.c.brand_id == Brand.id)
        .where(*filters)
    )

    direction = (direction or "desc").lower()
    desc_first = direction != "asc"

    def order(col):
        return col.desc().nulls_last() if desc_first else col.asc().nulls_last()

    if sort in ("ad_count", "ads"):
        order_expr = order(brand_stats.c.ad_count)
    elif sort in ("active", "active_count"):
        order_expr = order(brand_stats.c.active_count)
    elif sort in ("first_seen", "first_seen_at"):
        order_expr = order(brand_stats.c.first_seen_at)
    elif sort == "name":
        order_expr = order(Brand.canonical_name)
    else:
        order_expr = order(brand_stats.c.last_seen_at)

    total_count = session.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()

    rows = (
        session.execute(
            base_query.order_by(order_expr, Brand.canonical_name.asc()).limit(limit).offset(offset)
        ).all()
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        channels = [getattr(c, "value", str(c)) for c in (row.channels or [])]
        items.append(
            {
                "brand_id": str(row.brand_id),
                "brand_name": row.brand_name,
                "primary_domain": row.primary_domain,
                "primary_website_url": row.primary_website_url,
                "ad_count": row.ad_count or 0,
                "active_count": row.active_count or 0,
                "inactive_count": row.inactive_count or 0,
                "unknown_count": row.unknown_count or 0,
                "channels": channels,
                "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "hidden": bool(row.hidden),
            }
        )

    return jsonable_encoder({"items": items, "count": total_count, "limit": limit, "offset": offset})


def _order_clauses(
    sort: str,
    direction: str,
    *,
    last_seen_col,
    start_date_col,
    days_active_col,
    started_col,
    ad_id_col,
    has_media_col=None,
    performance_col=None,
    winning_col=None,
    confidence_col=None,
):
    direction = (direction or "desc").lower()
    desc_first = direction != "asc"

    def apply(col):
        return col.desc().nulls_last() if desc_first else col.asc().nulls_last()

    clauses = []
    if has_media_col is not None:
        clauses.append(has_media_col.desc().nulls_last())
    if sort in ("performance_score", "performance"):
        primary = performance_col or last_seen_col
    elif sort in ("winning_score", "winning"):
        primary = winning_col or last_seen_col
    elif sort in ("confidence",):
        primary = confidence_col or last_seen_col
    elif sort == "start_date":
        primary = start_date_col
    elif sort == "days_active":
        primary = days_active_col
    elif sort in ("started", "started_running_at"):
        primary = started_col
    else:
        primary = last_seen_col
    clauses.extend([apply(primary), apply(last_seen_col), apply(ad_id_col)])
    return clauses


def _serialize_media_rows(ad_id: str, media_rows: list[tuple[MediaAsset, str | None]]) -> list[dict[str, Any]]:
    storage = _media_storage()
    assets: list[dict[str, Any]] = []
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


_TEMPLATE_ONLY_RE = re.compile(r"^\W*(\{\{\s*[^}]+\s*\}\}\W*)+$")


def _extract_text(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        # Meta Ads Library snapshots may represent body text as {"text": "..."}.
        for key in ("text", "value", "content"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                text = candidate.strip()
                if text:
                    return text
    return None


def _is_template_only_text(value: Any) -> bool:
    text = _extract_text(value)
    if not text:
        return False
    return bool(_TEMPLATE_ONLY_RE.match(text))


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _summarize_texts(values: list[str], *, limit: int = 3) -> str | None:
    values = _unique_preserve_order(values)
    if not values:
        return None
    if len(values) <= limit:
        return " | ".join(values)
    head = " | ".join(values[:limit])
    return f"{head} (+{len(values) - limit} more)"


def _extract_snapshot_card_texts(snapshot: Any, keys: tuple[str, ...]) -> list[str]:
    if not isinstance(snapshot, dict):
        return []
    cards = snapshot.get("cards") or []
    if not isinstance(cards, list):
        return []

    out: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        for key in keys:
            candidate = _extract_text(card.get(key))
            if not candidate:
                continue
            if _is_template_only_text(candidate):
                continue
            out.append(candidate)
            break
    return out


def _derive_explore_ad_copy(ad: Ad) -> tuple[str | None, str | None]:
    """Return display-ready (headline, body_text) for explore ads.

    Some dynamic/catalog ads come through with placeholder-only template strings like
    `{{product.title}}`. Those are not useful in the UI, so we derive a better display
    headline/body from the ad raw snapshot (e.g. card titles) when available.

    This function intentionally avoids guessing values; it only uses fields present
    in the stored raw payload.
    """

    headline = _extract_text(ad.headline)
    body_text = _extract_text(ad.body_text)
    needs_headline = (not headline) or _is_template_only_text(headline)
    needs_body = (not body_text) or _is_template_only_text(body_text)
    if not (needs_headline or needs_body):
        return headline, body_text

    raw = getattr(ad, "raw_json", None) or {}
    snapshot = raw.get("snapshot") if isinstance(raw, dict) else None
    snapshot = snapshot if isinstance(snapshot, dict) else {}

    derived_headline = headline
    derived_body = body_text

    if needs_headline:
        # Prefer card titles for carousel/catalog ads.
        title_candidates: list[str] = []
        snapshot_title = _extract_text(snapshot.get("title"))
        if snapshot_title and not _is_template_only_text(snapshot_title):
            title_candidates.append(snapshot_title)
        title_candidates.extend(
            _extract_snapshot_card_texts(snapshot, ("title", "headline", "name"))
        )
        derived_headline = _summarize_texts(title_candidates)

    if needs_body:
        body_candidates: list[str] = []
        snapshot_body = _extract_text(snapshot.get("body"))
        if snapshot_body and not _is_template_only_text(snapshot_body):
            body_candidates.append(snapshot_body)
        body_candidates.extend(_extract_snapshot_card_texts(snapshot, ("body", "description")))
        derived_body = body_candidates[0] if body_candidates else None

    return derived_headline, derived_body


@router.get("/ads")
def explore_ads(
    q: str | None = None,
    channels: list[AdChannelEnum] = Query(default_factory=list),
    status: list[AdStatusEnum] = Query(default_factory=list),
    brand_ids: list[str] = Query(default_factory=list, alias="brandIds"),
    client_id: str | None = Query(default=None, alias="clientId"),
    product_id: str | None = Query(default=None, alias="productId"),
    research_run_id: str | None = Query(default=None, alias="researchRunId"),
    country_codes: list[str] = Query(default_factory=list, alias="countryCodes"),
    language_codes: list[str] = Query(default_factory=list, alias="languageCodes"),
    media_types: list[str] = Query(default_factory=list, alias="mediaTypes"),
    min_days_active: int | None = Query(default=None, ge=0),
    max_days_active: int | None = Query(default=None, ge=0),
    start_date_from: date | None = Query(default=None),
    start_date_to: date | None = Query(default=None),
    min_video_length: int | None = Query(default=None, ge=0),
    max_video_length: int | None = Query(default=None, ge=0),
    limit_per_brand: int | None = Query(default=None, ge=1, le=50),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="last_seen"),
    direction: str = Query(default="desc"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = AdsRepository(session)

    scoped_brand_ids: set[str] | None = None
    run: ResearchRun | None = None
    if research_run_id:
        run = session.get(ResearchRun, research_run_id)
        if not run or str(run.org_id) != auth.org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found")
    elif client_id or product_id:
        if not (client_id and product_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="clientId and productId are required together unless researchRunId is provided",
            )
        run = repo.latest_research_run_for_product(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
        )
        if not run:
            return jsonable_encoder({"items": [], "count": 0, "limit": limit, "offset": offset})

    if run:
        scoped_brand_ids = {
            str(row[0])
            for row in session.execute(
                select(ResearchRunBrand.brand_id).where(ResearchRunBrand.research_run_id == run.id)
            ).all()
        }
        if not scoped_brand_ids:
            return jsonable_encoder({"items": [], "count": 0, "limit": limit, "offset": offset})

    hidden_brand_ids = {
        str(row[0])
        for row in session.execute(
            select(BrandUserPreference.brand_id).where(
                BrandUserPreference.org_id == auth.org_id,
                BrandUserPreference.user_external_id == auth.user_id,
                BrandUserPreference.hidden.is_(True),
            )
        ).all()
    }

    filters = [Brand.org_id == auth.org_id]
    if scoped_brand_ids:
        filters.append(Brand.id.in_(scoped_brand_ids))
    if hidden_brand_ids:
        filters.append(~Ad.brand_id.in_(hidden_brand_ids))
    if brand_ids:
        filters.append(Ad.brand_id.in_(brand_ids))
    if q:
        pattern = f"%{q}%"
        filters.append(
            or_(
                Ad.headline.ilike(pattern),
                Ad.body_text.ilike(pattern),
                Ad.destination_domain.ilike(pattern),
                Brand.canonical_name.ilike(pattern),
            )
        )
    if channels:
        filters.append(Ad.channel.in_(channels))
    if status:
        filters.append(AdFacts.status.in_(status))
    country_codes = [c.upper() for c in country_codes if c]
    if country_codes:
        filters.append(AdFacts.country_codes.overlap(country_codes))
    language_codes = [l.upper() for l in language_codes if l]
    if language_codes:
        filters.append(AdFacts.language_codes.overlap(language_codes))
    normalized_media_types = [value.strip().upper() for value in media_types if value and value.strip()]
    if normalized_media_types:
        unique_media_types = list(dict.fromkeys(normalized_media_types))
        unsupported_media_types = sorted(set(unique_media_types) - _ALLOWED_AD_MEDIA_TYPES)
        if unsupported_media_types:
            allowed = ", ".join(sorted(_ALLOWED_AD_MEDIA_TYPES))
            invalid = ", ".join(unsupported_media_types)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported mediaTypes values: {invalid}. Allowed values: {allowed}",
            )
        filters.append(AdFacts.media_types.overlap(unique_media_types))
    if min_days_active is not None:
        filters.append(AdFacts.days_active >= min_days_active)
    if max_days_active is not None:
        filters.append(AdFacts.days_active <= max_days_active)
    if start_date_from is not None:
        filters.append(AdFacts.start_date >= start_date_from)
    if start_date_to is not None:
        filters.append(AdFacts.start_date <= start_date_to)
    if min_video_length is not None:
        filters.append(AdFacts.video_length_seconds >= min_video_length)
    if max_video_length is not None:
        filters.append(AdFacts.video_length_seconds <= max_video_length)

    media_counts = (
        select(AdAssetLink.ad_id, func.count().label("media_count"))
        .group_by(AdAssetLink.ad_id)
        .subquery()
    )
    media_count_col = func.coalesce(media_counts.c.media_count, 0)

    base_columns = [
        Ad.id.label("ad_id"),
        Ad.brand_id.label("brand_id"),
        Ad.last_seen_at.label("last_seen_at"),
        Ad.started_running_at.label("started_running_at"),
        Ad.first_seen_at.label("first_seen_at"),
        Ad.ended_running_at.label("ended_running_at"),
        AdFacts.start_date.label("fact_start_date"),
        AdFacts.days_active.label("fact_days_active"),
        media_count_col.label("media_count"),
        AdScore.performance_score.label("performance_score"),
        AdScore.performance_stars.label("performance_stars"),
        AdScore.winning_score.label("winning_score"),
        AdScore.confidence.label("score_confidence"),
        AdScore.score_breakdown.label("score_breakdown"),
        AdScore.score_version.label("score_version"),
    ]

    order_exprs_base = _order_clauses(
        sort,
        direction,
        last_seen_col=Ad.last_seen_at,
        start_date_col=AdFacts.start_date,
        days_active_col=AdFacts.days_active,
        started_col=Ad.started_running_at,
        ad_id_col=Ad.id,
        has_media_col=media_count_col,
        performance_col=AdScore.performance_score,
        winning_col=AdScore.winning_score,
        confidence_col=AdScore.confidence,
    )

    base_select = (
        select(*base_columns)
        .join(AdFacts, AdFacts.ad_id == Ad.id)
        .join(Brand, Brand.id == Ad.brand_id)
        .outerjoin(media_counts, media_counts.c.ad_id == Ad.id)
        .outerjoin(AdScore, AdScore.ad_id == Ad.id)
        .where(*filters)
    )

    if limit_per_brand:
        base_select = base_select.add_columns(
            func.row_number()
            .over(partition_by=Ad.brand_id, order_by=order_exprs_base)
            .label("rn")
        )

    ranked = base_select.subquery()

    filtered = select(ranked.c.ad_id).select_from(ranked)
    if limit_per_brand:
        filtered = filtered.where(ranked.c.rn <= limit_per_brand)

    order_exprs_ranked = _order_clauses(
        sort,
        direction,
        last_seen_col=ranked.c.last_seen_at,
        start_date_col=ranked.c.fact_start_date,
        days_active_col=ranked.c.fact_days_active,
        started_col=ranked.c.started_running_at,
        ad_id_col=ranked.c.ad_id,
        has_media_col=ranked.c.media_count,
        performance_col=ranked.c.performance_score,
        winning_col=ranked.c.winning_score,
        confidence_col=ranked.c.score_confidence,
    )

    total_count = session.execute(
        select(func.count()).select_from(filtered.subquery())
    ).scalar_one()

    id_rows = session.execute(
        filtered.order_by(*order_exprs_ranked).limit(limit).offset(offset)
    ).all()
    ad_ids = [str(row[0]) for row in id_rows]
    if not ad_ids:
        return jsonable_encoder({"items": [], "count": 0, "limit": limit, "offset": offset})

    ads = session.query(Ad).filter(Ad.id.in_(ad_ids)).all()
    facts = session.query(AdFacts).filter(AdFacts.ad_id.in_(ad_ids)).all()
    scores = session.query(AdScore).filter(AdScore.ad_id.in_(ad_ids)).all()
    brands = session.query(Brand).filter(Brand.id.in_({ad.brand_id for ad in ads})).all()

    media_rows = (
        session.query(MediaAsset, AdAssetLink.role, AdAssetLink.ad_id)
        .join(AdAssetLink, MediaAsset.id == AdAssetLink.media_asset_id)
        .filter(AdAssetLink.ad_id.in_(ad_ids))
        .all()
    )
    media_map: dict[str, list[tuple[MediaAsset, str | None]]] = defaultdict(list)
    for media, role, ad_id in media_rows:
        media_map[str(ad_id)].append((media, role))

    ad_map = {str(ad.id): ad for ad in ads}
    fact_map = {str(f.ad_id): f for f in facts}
    score_map = {str(s.ad_id): s for s in scores}
    brand_map = {str(b.id): b for b in brands}
    order_lookup = {ad_id: idx for idx, ad_id in enumerate(ad_ids)}

    results: list[dict[str, Any]] = []
    for ad_id in sorted(ad_ids, key=lambda x: order_lookup.get(x, 0)):
        ad = ad_map.get(ad_id)
        fact = fact_map.get(ad_id)
        if not ad or not fact:
            continue
        brand = brand_map.get(str(ad.brand_id))
        media_assets = _serialize_media_rows(ad_id, media_map.get(ad_id, []))
        score = score_map.get(ad_id)
        headline, primary_text = _derive_explore_ad_copy(ad)
        results.append(
            {
                "ad_id": ad_id,
                "brand_id": ad.brand_id,
                "brand_name": getattr(brand, "canonical_name", None) or getattr(brand, "normalized_name", None),
                "brand_hidden": str(ad.brand_id) in hidden_brand_ids,
                "channel": getattr(ad.channel, "value", str(ad.channel)),
                "ad_status": getattr(ad.ad_status, "value", str(ad.ad_status)),
                "cta_type": ad.cta_type,
                "cta_text": ad.cta_text,
                "landing_url": ad.landing_url,
                "destination_domain": ad.destination_domain,
                "headline": headline,
                "primary_text": primary_text,
                "start_date": ad.started_running_at.isoformat() if ad.started_running_at else None,
                "end_date": ad.ended_running_at.isoformat() if ad.ended_running_at else None,
                "first_seen_at": ad.first_seen_at.isoformat() if ad.first_seen_at else None,
                "last_seen_at": ad.last_seen_at.isoformat() if ad.last_seen_at else None,
                "media_assets": media_assets,
                "facts": {
                    "display_format": fact.display_format,
                    "media_types": fact.media_types,
                    "language_codes": fact.language_codes,
                    "country_codes": fact.country_codes,
                    "start_date": fact.start_date.isoformat() if fact.start_date else None,
                    "days_active": fact.days_active,
                    "video_length_seconds": fact.video_length_seconds,
                },
                "scores": {
                    "performance_score": getattr(score, "performance_score", None),
                    "performance_stars": getattr(score, "performance_stars", None),
                    "winning_score": getattr(score, "winning_score", None),
                    "confidence": getattr(score, "confidence", None),
                    "score_breakdown": getattr(score, "score_breakdown", None),
                    "score_version": getattr(score, "score_version", None),
                }
                if score
                else None,
            }
        )

    return jsonable_encoder({"items": results, "count": total_count, "limit": limit, "offset": offset})


@router.post("/brands/{brand_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
def hide_brand(
    brand_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    brand = session.get(Brand, brand_id)
    if not brand or str(brand.org_id) != auth.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    existing = session.scalar(
        select(BrandUserPreference).where(
            BrandUserPreference.org_id == auth.org_id,
            BrandUserPreference.user_external_id == auth.user_id,
            BrandUserPreference.brand_id == brand_id,
        )
    )
    if existing:
        existing.hidden = True
        existing.updated_at = func.now()
    else:
        session.add(
            BrandUserPreference(
                org_id=auth.org_id,
                brand_id=brand_id,
                user_external_id=auth.user_id,
                hidden=True,
            )
        )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/brands/{brand_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
def unhide_brand(
    brand_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    brand = session.get(Brand, brand_id)
    if not brand or str(brand.org_id) != auth.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")

    pref = session.scalar(
        select(BrandUserPreference).where(
            BrandUserPreference.org_id == auth.org_id,
            BrandUserPreference.user_external_id == auth.user_id,
            BrandUserPreference.brand_id == brand_id,
        )
    )
    if pref:
        pref.hidden = False
        pref.updated_at = func.now()
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
