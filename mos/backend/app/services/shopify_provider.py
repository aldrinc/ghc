from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.shopify_catalog import verify_shopify_product_exists
from app.services.shopify_checkout import create_shopify_checkout
from app.services.shopify_collection_sync import sync_workspace_shopify_catalog_collection
from app.services.shopify_connection import get_client_shopify_connection_status


class ShopifyCommerceProvider:
    name = "shopify"

    def create_checkout(
        self,
        *,
        client_id: str,
        external_variant_id: str,
        quantity: int,
        metadata: dict[str, Any],
        shopify_selling_plan_id: str | None = None,
    ) -> dict[str, str]:
        return create_shopify_checkout(
            client_id=client_id,
            variant_gid=external_variant_id,
            quantity=quantity,
            metadata=metadata,
            selling_plan_id=shopify_selling_plan_id,
        )

    def get_connection_status(
        self,
        *,
        client_id: str,
        selected_shop_domain: str | None = None,
    ) -> dict[str, Any]:
        return get_client_shopify_connection_status(
            client_id=client_id,
            selected_shop_domain=selected_shop_domain,
        )

    def verify_product_exists(self, *, client_id: str, external_product_id: str) -> None:
        verify_shopify_product_exists(client_id=client_id, product_gid=external_product_id)

    def sync_workspace_catalog_collection(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        shop_domain: str | None = None,
        extra_product_ids: list[str] | None = None,
    ) -> dict[str, str | int] | None:
        return sync_workspace_shopify_catalog_collection(
            session=session,
            org_id=org_id,
            client_id=client_id,
            shop_domain=shop_domain,
            extra_product_gids=extra_product_ids,
        )
