from __future__ import annotations

from typing import Any, Protocol

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.shopify_provider import ShopifyCommerceProvider
from app.services.medusa_connection import (
    get_medusa_connection_status,
    test_medusa_connection,
)
from app.services.medusa_catalog import (
    create_medusa_variant_from_mos_variant,
    ensure_medusa_product,
    get_medusa_product,
    get_medusa_variant,
    update_medusa_variant,
)


class CommerceProvider(Protocol):
    name: str

    def create_checkout(
        self,
        *,
        client_id: str,
        external_variant_id: str,
        quantity: int,
        metadata: dict[str, Any],
        shopify_selling_plan_id: str | None = None,
    ) -> dict[str, str]: ...

    def get_connection_status(
        self,
        *,
        client_id: str,
        selected_shop_domain: str | None = None,
    ) -> dict[str, Any]: ...

    def verify_product_exists(self, *, client_id: str, external_product_id: str) -> None: ...

    def sync_workspace_catalog_collection(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        shop_domain: str | None = None,
        extra_product_ids: list[str] | None = None,
    ) -> dict[str, str | int] | None: ...

    def create_variant(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        product: Any,
        variant: Any,
    ) -> dict[str, Any]: ...

    def update_variant(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        external_variant_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]: ...


def _normalize_provider(provider: str) -> str:
    cleaned = str(provider or "").strip().lower()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Commerce provider is required.",
        )
    return cleaned


class _MedusaCommerceProvider:
    name = "medusa"

    def create_checkout(
        self,
        *,
        client_id: str,
        external_variant_id: str,
        quantity: int,
        metadata: dict[str, Any],
        shopify_selling_plan_id: str | None = None,
    ) -> dict[str, str]:
        del client_id, external_variant_id, quantity, metadata, shopify_selling_plan_id
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Medusa checkout is not implemented yet.",
        )

    def get_connection_status(
        self,
        *,
        client_id: str,
        selected_shop_domain: str | None = None,
    ) -> dict[str, Any]:
        del selected_shop_domain
        # This is handled by the Medusa-specific endpoints
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Use the Medusa-specific connection status endpoint.",
        )

    def verify_product_exists(self, *, client_id: str, external_product_id: str) -> None:
        del client_id, external_product_id
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Medusa product verification is not implemented yet.",
        )

    def sync_workspace_catalog_collection(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        shop_domain: str | None = None,
        extra_product_ids: list[str] | None = None,
    ) -> dict[str, str | int] | None:
        del session, org_id, client_id, shop_domain, extra_product_ids
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Medusa catalog collection sync is not implemented yet.",
        )

    def create_variant(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        product: Any,
        variant: Any,
    ) -> dict[str, Any]:
        return create_medusa_variant_from_mos_variant(
            session=session,
            org_id=org_id,
            client_id=client_id,
            product=product,
            variant=variant,
        )

    def update_variant(
        self,
        *,
        session: Session,
        org_id: str,
        client_id: str,
        external_variant_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return update_medusa_variant(
            session=session,
            org_id=org_id,
            client_id=client_id,
            medusa_variant_id=external_variant_id,
            fields=fields,
        )


_PROVIDERS: dict[str, CommerceProvider] = {
    "shopify": ShopifyCommerceProvider(),
    "medusa": _MedusaCommerceProvider(),
}


def get_commerce_provider(provider: str) -> CommerceProvider:
    normalized_provider = _normalize_provider(provider)
    resolved = _PROVIDERS.get(normalized_provider)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unsupported commerce provider.",
        )
    return resolved


def create_managed_checkout(
    *,
    provider: str,
    client_id: str,
    external_variant_id: str,
    quantity: int,
    metadata: dict[str, Any],
    shopify_selling_plan_id: str | None = None,
) -> dict[str, str]:
    return get_commerce_provider(provider).create_checkout(
        client_id=client_id,
        external_variant_id=external_variant_id,
        quantity=quantity,
        metadata=metadata,
        shopify_selling_plan_id=shopify_selling_plan_id,
    )


def get_commerce_connection_status(
    *,
    provider: str,
    client_id: str,
    selected_shop_domain: str | None = None,
) -> dict[str, Any]:
    return get_commerce_provider(provider).get_connection_status(
        client_id=client_id,
        selected_shop_domain=selected_shop_domain,
    )


def verify_external_product_exists(
    *,
    provider: str,
    client_id: str,
    external_product_id: str,
) -> None:
    get_commerce_provider(provider).verify_product_exists(
        client_id=client_id,
        external_product_id=external_product_id,
    )


def sync_workspace_catalog_collection(
    *,
    provider: str,
    session: Session,
    org_id: str,
    client_id: str,
    shop_domain: str | None = None,
    extra_product_ids: list[str] | None = None,
) -> dict[str, str | int] | None:
    return get_commerce_provider(provider).sync_workspace_catalog_collection(
        session=session,
        org_id=org_id,
        client_id=client_id,
        shop_domain=shop_domain,
        extra_product_ids=extra_product_ids,
    )


def create_commerce_variant(
    *,
    provider: str,
    session: Session,
    org_id: str,
    client_id: str,
    product: Any,
    variant: Any,
) -> dict[str, Any]:
    return get_commerce_provider(provider).create_variant(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product=product,
        variant=variant,
    )


def update_commerce_variant(
    *,
    provider: str,
    session: Session,
    org_id: str,
    client_id: str,
    external_variant_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    return get_commerce_provider(provider).update_variant(
        session=session,
        org_id=org_id,
        client_id=client_id,
        external_variant_id=external_variant_id,
        fields=fields,
    )
