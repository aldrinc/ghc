"""Medusa Admin API catalog operations.

This module provides product and variant management operations for Medusa backends.
It makes direct HTTP calls to the Medusa Admin API using workspace-entered credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ClientMedusaConfig, Product, ProductVariant
from app.services.medusa_connection import (
    get_client_medusa_config,
    _make_medusa_admin_request,
    medusa_create_product,
    medusa_create_variant,
    medusa_get_product,
    medusa_get_product_options,
    medusa_update_variant,
)


@dataclass(frozen=True)
class MedusaProduct:
    id: str
    title: str
    handle: str | None
    status: str
    variants: list[dict[str, Any]]


@dataclass(frozen=True)
class MedusaVariant:
    id: str
    product_id: str
    title: str
    prices: list[dict[str, Any]]
    sku: str | None
    barcode: str | None
    inventory_quantity: int | None
    options: dict[str, str] | None


def _normalize_currency_code(value: str) -> str:
    """Normalize and validate a currency code."""
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Currency must be a valid 3-letter ISO code.",
        )
    return cleaned


def _require_medusa_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> ClientMedusaConfig:
    """Get Medusa config or raise an error if not configured."""
    config = get_client_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa connection is not configured for this workspace.",
        )
    if not config.admin_api_key_encrypted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa admin API key is not set.",
        )
    if config.connection_status != "connected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Medusa connection is not ready: {config.last_connection_error or 'Connection not tested.'}",
        )
    # At this point, admin_api_key_encrypted is guaranteed to be non-None
    return config


def _get_api_key(config: ClientMedusaConfig) -> str:
    """Get the API key from config, raising if not set."""
    key = config.admin_api_key_encrypted
    assert key is not None, "Medusa admin API key is not set."
    return key


def ensure_medusa_product(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
    default_variant_title: str,
    option_values: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """Ensure a Medusa product exists for the given mOS product.

    Returns:
        tuple of (medusa_product_id, was_created)
    """
    config = _require_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    # Check if product already has a Medusa mapping
    existing_medusa_id = getattr(product, "medusa_product_id", None)
    if existing_medusa_id:
        return existing_medusa_id, False

    # Create new Medusa product via Admin API
    api_key = _get_api_key(config)
    normalized_option_values = {
        str(k).strip(): str(v).strip()
        for k, v in (option_values or {}).items()
        if str(k).strip() and str(v).strip()
    }
    product_options = (
        [{"title": key, "values": [value]} for key, value in normalized_option_values.items()]
        if normalized_option_values
        else [{"title": "Variant", "values": [default_variant_title]}]
    )

    medusa_product = medusa_create_product(
        base_url=config.base_url,
        api_key=api_key,
        title=product.title,
        description=product.description or "",
        handle=product.handle,
        options=product_options,
        product_status="published" if product.published_at else "draft",
    )

    medusa_product_id = medusa_product.get("id")
    if not isinstance(medusa_product_id, str) or not medusa_product_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid product ID.",
        )

    return medusa_product_id, True


def create_medusa_variant(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
    title: str,
    price_cents: int,
    currency: str,
    compare_at_price_cents: int | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    inventory_quantity: int | None = None,
    inventory_policy: str | None = None,
    option_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a Medusa variant and return the variant data with external ID.

    This function:
    1. Ensures the product exists in Medusa (creates if needed)
    2. Creates the variant in Medusa
    3. Returns the variant data with the Medusa variant ID
    """
    config = _require_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    # Validate inputs
    cleaned_title = title.strip()
    if not cleaned_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant title cannot be empty.",
        )

    if price_cents < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price must be a non-negative integer (in cents).",
        )

    cleaned_currency = _normalize_currency_code(currency)

    if compare_at_price_cents is not None and compare_at_price_cents < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Compare-at price must be a non-negative integer (in cents).",
        )
    if compare_at_price_cents is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Medusa compare-at price sync is not supported in this flow yet. Leave compare-at blank.",
        )

    if inventory_quantity is not None and inventory_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inventory quantity must be a non-negative integer.",
        )

    if inventory_policy is not None:
        normalized_policy = inventory_policy.strip().lower()
        if normalized_policy not in ("deny", "continue"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inventory policy must be 'deny' or 'continue'.",
            )

    # Ensure product exists in Medusa
    medusa_product_id, product_created = ensure_medusa_product(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product=product,
        default_variant_title=cleaned_title,
        option_values=option_values,
    )

    normalized_option_values = {
        str(k).strip(): str(v).strip()
        for k, v in (option_values or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if not normalized_option_values:
        existing_options = []
        if not product_created:
            existing_options = medusa_get_product_options(
                base_url=config.base_url,
                api_key=_get_api_key(config),
                product_id=medusa_product_id,
            )
        if existing_options:
            if len(existing_options) == 1 and isinstance(existing_options[0], dict):
                option_title = existing_options[0].get("title") or "Variant"
                normalized_option_values = {str(option_title): cleaned_title}
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Existing Medusa product options require explicit option values for this new variant.",
                )
        else:
            normalized_option_values = {"Variant": cleaned_title}

    # Build Medusa price payload
    # Medusa v2 expects prices as an array with amount (in cents) and currency_code
    prices: list[dict[str, Any]] = [
        {
            "amount": price_cents,
            "currency_code": cleaned_currency.lower(),
        }
    ]

    if compare_at_price_cents is not None:
        prices[0]["original_amount"] = compare_at_price_cents

    # Create variant in Medusa via Admin API
    api_key = _get_api_key(config)
    medusa_variant = medusa_create_variant(
        base_url=config.base_url,
        api_key=api_key,
        product_id=medusa_product_id,
        title=cleaned_title,
        prices=prices,
        sku=sku.strip() if sku else None,
        barcode=barcode.strip() if barcode else None,
        inventory_quantity=inventory_quantity,
        inventory_policy=inventory_policy,
        options=normalized_option_values,
    )

    variant_id = medusa_variant.get("id")
    if not isinstance(variant_id, str) or not variant_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant ID.",
        )

    return {
        "id": variant_id,
        "productId": medusa_product_id,
        "title": cleaned_title,
        "priceCents": price_cents,
        "currency": cleaned_currency,
        "compareAtPriceCents": compare_at_price_cents,
        "sku": sku,
        "barcode": barcode,
        "inventoryQuantity": inventory_quantity,
        "inventoryPolicy": inventory_policy,
        "optionValues": option_values,
    }


def create_medusa_variant_from_mos_variant(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product: Product,
    variant: ProductVariant,
) -> dict[str, Any]:
    """Create a Medusa variant from an existing mOS variant.

    This creates the variant in Medusa and returns the data.
    Note: The caller is responsible for updating the local variant with external_price_id.
    """
    return create_medusa_variant(
        session=session,
        org_id=org_id,
        client_id=client_id,
        product=product,
        title=variant.title,
        price_cents=variant.price,
        currency=variant.currency,
        compare_at_price_cents=variant.compare_at_price,
        sku=variant.sku,
        barcode=variant.barcode,
        inventory_quantity=variant.inventory_quantity,
        inventory_policy=variant.inventory_policy,
        option_values=variant.option_values if variant.option_values else None,
    )


def get_medusa_product(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    medusa_product_id: str,
) -> dict[str, Any]:
    """Fetch a product from Medusa by ID."""
    config = _require_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )
    api_key = _get_api_key(config)

    return medusa_get_product(
        base_url=config.base_url,
        api_key=api_key,
        product_id=medusa_product_id,
    )


def get_medusa_variant(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
    variant_id: str,
) -> dict[str, Any]:
    """Fetch a variant from Medusa by ID."""
    config = _require_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )
    api_key = _get_api_key(config)

    path = f"/admin/products/{product_id}/variants/{variant_id}"

    result = _make_medusa_admin_request(
        base_url=config.base_url,
        api_key=api_key,
        method="GET",
        path=path,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant response.",
        )

    variant = result.get("variant") or result
    if not isinstance(variant, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa API returned invalid variant data.",
        )

    return variant


def update_medusa_variant(
    *,
    session: Session,
    org_id: str,
    client_id: str,
    product_id: str,
    variant_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Update a variant in Medusa."""
    config = _require_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )

    # Map mOS field names to Medusa API field names
    medusa_fields: dict[str, Any] = {}

    if "title" in fields:
        cleaned_title = str(fields["title"]).strip()
        if not cleaned_title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant title cannot be empty.",
            )
        medusa_fields["title"] = cleaned_title

    if "priceCents" in fields or "currency" in fields:
        # Need to rebuild prices array
        price_cents = fields.get("priceCents")
        currency = fields.get("currency")
        if price_cents is not None:
            if not isinstance(price_cents, int) or price_cents < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Price must be a non-negative integer (in cents).",
                )
        if currency is not None:
            currency = _normalize_currency_code(currency)

        # For updates, we need to fetch existing prices and modify
        # This is a simplified version - in production you'd want more sophisticated handling
        if price_cents is not None and currency is not None:
            medusa_fields["prices"] = [
                {
                    "amount": price_cents,
                    "currency_code": currency.lower(),
                }
            ]

    if "compareAtPriceCents" in fields:
        compare_at = fields["compareAtPriceCents"]
        if compare_at is not None and (not isinstance(compare_at, int) or compare_at < 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Compare-at price must be null or a non-negative integer (in cents).",
            )
        # Note: Medusa handles compare_at_price differently - would need to update prices array

    if "sku" in fields:
        sku = fields["sku"]
        medusa_fields["sku"] = sku.strip() if isinstance(sku, str) and sku.strip() else None

    if "barcode" in fields:
        barcode = fields["barcode"]
        medusa_fields["barcode"] = (
            barcode.strip() if isinstance(barcode, str) and barcode.strip() else None
        )

    if "inventoryQuantity" in fields:
        qty = fields["inventoryQuantity"]
        if qty is not None and (not isinstance(qty, int) or qty < 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inventory quantity must be null or a non-negative integer.",
            )
        medusa_fields["inventory_quantity"] = qty

    if "inventoryPolicy" in fields:
        policy = fields["inventoryPolicy"]
        if policy is not None:
            normalized = str(policy).strip().lower()
            if normalized not in ("deny", "continue"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Inventory policy must be 'deny' or 'continue'.",
                )
            medusa_fields["inventory_policy"] = normalized
        else:
            medusa_fields["inventory_policy"] = None

    api_key = _get_api_key(config)
    return medusa_update_variant(
        base_url=config.base_url,
        api_key=api_key,
        product_id=product_id,
        variant_id=variant_id,
        fields=medusa_fields,
    )
