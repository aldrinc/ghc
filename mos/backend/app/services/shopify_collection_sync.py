from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product
from app.services.shopify_connection import sync_client_shopify_catalog_collection


def list_workspace_shopify_product_gids(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    extra_product_gids: list[str] | None = None,
) -> list[str]:
    stored_product_gids = session.scalars(
        select(Product.shopify_product_gid)
        .where(
            Product.org_id == org_id,
            Product.client_id == client_id,
            Product.shopify_product_gid.is_not(None),
        )
        .order_by(Product.created_at.asc(), Product.id.asc())
    ).all()

    product_gids: list[str] = []
    seen_product_gids: set[str] = set()
    for raw_product_gid in [*stored_product_gids, *(extra_product_gids or [])]:
        if not isinstance(raw_product_gid, str):
            continue
        cleaned_product_gid = raw_product_gid.strip()
        if not cleaned_product_gid:
            continue
        if cleaned_product_gid in seen_product_gids:
            continue
        seen_product_gids.add(cleaned_product_gid)
        product_gids.append(cleaned_product_gid)

    return product_gids


def sync_workspace_shopify_catalog_collection(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    shop_domain: str | None = None,
    extra_product_gids: list[str] | None = None,
) -> dict[str, str | int] | None:
    product_gids = list_workspace_shopify_product_gids(
        session=session,
        org_id=org_id,
        client_id=client_id,
        extra_product_gids=extra_product_gids,
    )
    if not product_gids:
        return None

    return sync_client_shopify_catalog_collection(
        client_id=client_id,
        product_gids=product_gids,
        shop_domain=shop_domain,
    )
