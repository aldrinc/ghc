from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.db.deps import get_session
from app.db.enums import AdStatusEnum, ProductBrandRelationshipTypeEnum
from app.db.models import Ad, Brand, BrandUserPreference, ProductBrandRelationship


router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("/relationships")
def list_brand_relationships(
    q: str | None = None,
    client_id: str = Query(alias="clientId"),
    product_id: str = Query(alias="productId"),
    relationship_type: str | None = Query(default=None, alias="relationshipType"),
    include_hidden: bool = Query(default=False, alias="includeHidden"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="last_seen"),
    direction: str = Query(default="desc"),
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not client_id or not product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="clientId and productId are required.",
        )

    relationship_enum: ProductBrandRelationshipTypeEnum | None = None
    if relationship_type:
        try:
            relationship_enum = ProductBrandRelationshipTypeEnum(relationship_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid relationshipType: {relationship_type}",
            ) from exc

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

    filters = [
        ProductBrandRelationship.org_id == auth.org_id,
        ProductBrandRelationship.client_id == client_id,
        ProductBrandRelationship.product_id == product_id,
    ]
    if relationship_enum:
        filters.append(ProductBrandRelationship.relationship_type == relationship_enum)

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
        .where(Brand.org_id == auth.org_id)
        .group_by(Ad.brand_id)
        .subquery()
    )

    hidden_expr = Brand.id.in_(hidden_brand_ids) if hidden_brand_ids else literal(False)

    base_query = (
        select(
            ProductBrandRelationship.id.label("relationship_id"),
            ProductBrandRelationship.relationship_type.label("relationship_type"),
            ProductBrandRelationship.source_type.label("source_type"),
            ProductBrandRelationship.source_id.label("source_id"),
            ProductBrandRelationship.created_at.label("created_at"),
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
        .select_from(ProductBrandRelationship)
        .join(Brand, Brand.id == ProductBrandRelationship.brand_id)
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
                "relationship_id": str(row.relationship_id),
                "relationship_type": getattr(row.relationship_type, "value", str(row.relationship_type)),
                "source_type": getattr(row.source_type, "value", str(row.source_type)),
                "source_id": row.source_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
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
