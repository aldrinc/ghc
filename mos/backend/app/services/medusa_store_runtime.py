"""Medusa Store API runtime for public site pages.

This module provides direct HTTP calls to the Medusa Store API using the publishable key.
It is used by public site pages to fetch real commerce data without requiring admin authentication.

The Store API is the public-facing API that customers interact with, as opposed to the Admin API
which is used for backend management operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ClientMedusaConfig
from app.services.medusa_connection import get_client_medusa_config


# Medusa Store API paths
_MEDUSA_STORE_REGIONS_PATH = "/store/regions"
_MEDUSA_STORE_PRODUCTS_PATH = "/store/products"
_MEDUSA_STORE_PRODUCT_DETAIL_PATH = "/store/products/{id}"
_MEDUSA_STORE_COLLECTIONS_PATH = "/store/collections"
_MEDUSA_STORE_CATEGORIES_PATH = "/store/product-categories"
_MEDUSA_STORE_CARTS_PATH = "/store/carts"
_MEDUSA_STORE_CART_DETAIL_PATH = "/store/carts/{cart_id}"
_MEDUSA_STORE_CART_LINE_ITEMS_PATH = "/store/carts/{cart_id}/line-items"
_MEDUSA_STORE_CART_LINE_ITEM_DETAIL_PATH = "/store/carts/{cart_id}/line-items/{line_id}"
_MEDUSA_STORE_SHIPPING_OPTIONS_PATH = "/store/shipping-options"
_MEDUSA_STORE_SHIPPING_METHODS_PATH = "/store/carts/{cart_id}/shipping-methods"
_MEDUSA_STORE_PAYMENT_PROVIDERS_PATH = "/store/payment-providers"
_MEDUSA_STORE_PAYMENT_COLLECTIONS_PATH = "/store/payment-collections"
_MEDUSA_STORE_PAYMENT_SESSIONS_PATH = "/store/payment-collections/{id}/payment-sessions"
_MEDUSA_STORE_CART_COMPLETE_PATH = "/store/carts/{cart_id}/complete"


@dataclass(frozen=True)
class MedusaStoreConfig:
    """Configuration for Medusa Store API access."""

    base_url: str
    publishable_key: str


def _error_detail_from_response(response: httpx.Response) -> str:
    """Extract error detail from HTTP response."""
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text or response.reason_phrase or f"HTTP {response.status_code}"

    if isinstance(body, dict):
        # Medusa error format
        detail = body.get("message") or body.get("detail") or body.get("error")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str):
                return message
        # Fallback to errors array
        if "errors" in body:
            errors = body["errors"]
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    return first_error.get("message", str(first_error))
                return str(first_error)
        return str(body)

    return str(body)


def _make_medusa_store_request(
    *,
    base_url: str,
    publishable_key: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> Any:
    """Make a direct HTTP request to the Medusa Store API.

    Uses the publishable key for authentication, which is safe for public-facing requests.
    """
    headers = {
        "Content-Type": "application/json",
        "x-publishable-api-key": publishable_key,
    }

    url = f"{base_url.rstrip('/')}{path}"
    request_timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 10.0),
    )

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Medusa Store API request timed out after {timeout_seconds:.1f}s ({method} {path}).",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Medusa Store API request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = _error_detail_from_response(response)
        # Map common Medusa errors to appropriate HTTP status codes
        if response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Medusa Store authentication failed: {detail}",
            )
        if response.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Medusa Store permission denied: {detail}",
            )
        if response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Medusa Store resource not found: {detail}",
            )
        if response.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Medusa Store conflict: {detail}",
            )
        if response.status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Medusa Store server error: {detail}",
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Medusa Store API error: {detail}",
        )

    # Handle empty responses
    if response.status_code == 204:
        return None

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid JSON.",
        ) from exc


def _require_medusa_store_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> MedusaStoreConfig:
    """Get Medusa Store config or raise an error if not configured."""
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
    if not config.base_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa base URL is not configured.",
        )
    if not config.publishable_key_encrypted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Medusa publishable key is not configured. A publishable key is required for Store API access.",
        )
    return MedusaStoreConfig(
        base_url=config.base_url,
        publishable_key=config.publishable_key_encrypted,
    )


# =============================================================================
# Region Operations
# =============================================================================


def medusa_list_regions(
    *,
    config: MedusaStoreConfig,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """List all regions from Medusa Store API."""
    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_REGIONS_PATH,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid regions response.",
        )

    regions = result.get("regions", [])
    if not isinstance(regions, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid regions data.",
        )

    return regions


# =============================================================================
# Product Operations
# =============================================================================


def medusa_list_products(
    *,
    config: MedusaStoreConfig,
    collection_id: str | None = None,
    category_id: str | None = None,
    handle: str | None = None,
    limit: int = 100,
    offset: int = 0,
    region_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """List products from Medusa Store API with optional filtering.

    Args:
        config: Medusa Store API configuration
        collection_id: Filter by collection ID
        category_id: Filter by category ID
        handle: Filter by product handle (exact match)
        limit: Maximum number of products to return
        offset: Pagination offset
        region_id: Region ID for price calculation (required for prices in response)
        timeout_seconds: Request timeout
    """
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        # Include variants to get pricing data for product cards
        "expand": "variants",
    }
    if collection_id:
        params["collection_id"] = collection_id
    if category_id:
        params["category_id"] = category_id
    if handle:
        params["handle"] = handle
    # Pass region_id to get region-specific pricing in the response
    if region_id:
        params["region_id"] = region_id

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_PRODUCTS_PATH,
        params=params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid products response.",
        )

    return result


def medusa_get_product(
    *,
    config: MedusaStoreConfig,
    product_id: str,
    region_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Get a single product by ID from Medusa Store API.

    Args:
        config: Medusa Store API configuration
        product_id: The product ID to fetch
        region_id: Region ID for price calculation (required for prices in response)
        timeout_seconds: Request timeout
    """
    path = _MEDUSA_STORE_PRODUCT_DETAIL_PATH.format(id=product_id)

    # Build query params - region_id is needed for price calculation
    params: dict[str, Any] = {}
    if region_id:
        params["region_id"] = region_id

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=path,
        params=params if params else None,
        # Note: Medusa Store API doesn't support the 'expand' param - variants are included by default
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid product response.",
        )

    product = result.get("product") or result
    if not isinstance(product, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid product data.",
        )

    return product


def medusa_get_product_by_handle(
    *,
    config: MedusaStoreConfig,
    handle: str,
    region_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any] | None:
    """Get a single product by handle from Medusa Store API.

    Tries exact match first, then falls back to partial match if not found.

    Args:
        config: Medusa Store API configuration
        handle: The product handle to search for
        region_id: Region ID for price calculation (required for prices in response)
        timeout_seconds: Request timeout
    """
    # Try exact match first
    result = medusa_list_products(
        config=config,
        handle=handle,
        limit=1,
        region_id=region_id,
        timeout_seconds=timeout_seconds,
    )

    products = result.get("products", [])
    if isinstance(products, list) and products:
        return products[0]

    # Fallback: try partial match (case-insensitive contains)
    # This helps when handle format differs slightly (e.g., "the-honest-herbalist-handbook" vs "honest-herbalist-handbook")
    all_result = medusa_list_products(
        config=config,
        limit=50,
        region_id=region_id,
        timeout_seconds=timeout_seconds,
    )

    all_products = all_result.get("products", [])
    if isinstance(all_products, list):
        handle_lower = handle.lower()
        for product in all_products:
            product_handle = product.get("handle", "") or ""
            product_handle_lower = product_handle.lower()
            # Check both directions: does the handle contain the search term OR does the search term contain the handle?
            # Also check the product title for additional flexibility
            product_title = product.get("title", "") or ""
            product_title_lower = product_title.lower()

            if product_handle_lower and (
                handle_lower in product_handle_lower
                or product_handle_lower in handle_lower
                or handle_lower in product_title_lower
                or product_title_lower in handle_lower
            ):
                return product

    return None


def medusa_get_products_by_ids(
    *,
    config: MedusaStoreConfig,
    product_ids: list[str],
    region_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Fetch multiple products by their IDs from Medusa Store API.

    This is used to fetch only the workspace's mapped products instead of
    the entire Medusa catalog.

    Args:
        config: Medusa Store API configuration
        product_ids: List of product IDs to fetch
        region_id: Region ID for price calculation (required for prices in response)
        timeout_seconds: Request timeout
    """
    if not product_ids:
        return []

    products = []
    # Fetch each product individually since Medusa Store API doesn't have a batch endpoint
    for product_id in product_ids:
        try:
            product = medusa_get_product(
                config=config,
                product_id=product_id,
                region_id=region_id,
                timeout_seconds=timeout_seconds,
            )
            products.append(product)
        except HTTPException:
            # Skip products that don't exist or are unavailable
            continue

    return products


# =============================================================================
# Collection Operations
# =============================================================================


def medusa_list_collections(
    *,
    config: MedusaStoreConfig,
    limit: int = 100,
    offset: int = 0,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """List collections from Medusa Store API."""
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_COLLECTIONS_PATH,
        params=params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid collections response.",
        )

    collections = result.get("collections", [])
    if not isinstance(collections, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid collections data.",
        )

    return collections


# =============================================================================
# Category Operations
# =============================================================================


def medusa_list_categories(
    *,
    config: MedusaStoreConfig,
    parent_category_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """List product categories from Medusa Store API."""
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
    }
    if parent_category_id:
        params["parent_category_id"] = parent_category_id

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_CATEGORIES_PATH,
        params=params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid categories response.",
        )

    categories = result.get("product_categories", [])
    if not isinstance(categories, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid categories data.",
        )

    return categories


# =============================================================================
# Cart Operations
# =============================================================================


def medusa_create_cart(
    *,
    config: MedusaStoreConfig,
    region_id: str,
    country_code: str | None = None,
    email: str | None = None,
    shipping_address: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Create a new cart in Medusa."""
    payload: dict[str, Any] = {
        "region_id": region_id,
    }
    if country_code:
        payload["country_code"] = country_code
    if email:
        payload["email"] = email
    if shipping_address:
        payload["shipping_address"] = shipping_address
    if items:
        payload["items"] = items

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=_MEDUSA_STORE_CARTS_PATH,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart creation response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


def medusa_get_cart(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Get a cart by ID from Medusa."""
    path = _MEDUSA_STORE_CART_DETAIL_PATH.format(cart_id=cart_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=path,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


def medusa_update_cart(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    email: str | None = None,
    shipping_address: dict[str, Any] | None = None,
    billing_address: dict[str, Any] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Update a cart in Medusa."""
    payload: dict[str, Any] = {}
    if email is not None:
        payload["email"] = email
    if shipping_address is not None:
        payload["shipping_address"] = shipping_address
    if billing_address is not None:
        payload["billing_address"] = billing_address

    if not payload:
        # Nothing to update, return current cart
        return medusa_get_cart(config=config, cart_id=cart_id, timeout_seconds=timeout_seconds)

    path = _MEDUSA_STORE_CART_DETAIL_PATH.format(cart_id=cart_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart update response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


def medusa_add_cart_line_item(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    variant_id: str,
    quantity: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Add a line item to a cart in Medusa."""
    payload = {
        "variant_id": variant_id,
        "quantity": quantity,
    }

    path = _MEDUSA_STORE_CART_LINE_ITEMS_PATH.format(cart_id=cart_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid line item response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


def medusa_update_cart_line_item(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    line_id: str,
    quantity: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Update a line item in a cart in Medusa."""
    payload = {
        "quantity": quantity,
    }

    path = _MEDUSA_STORE_CART_LINE_ITEM_DETAIL_PATH.format(cart_id=cart_id, line_id=line_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid line item update response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


def medusa_delete_cart_line_item(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    line_id: str,
    timeout_seconds: float = 30.0,
) -> None:
    """Delete a line item from a cart in Medusa."""
    path = _MEDUSA_STORE_CART_LINE_ITEM_DETAIL_PATH.format(cart_id=cart_id, line_id=line_id)

    _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="DELETE",
        path=path,
        timeout_seconds=timeout_seconds,
    )


# =============================================================================
# Shipping Operations
# =============================================================================


def medusa_list_shipping_options(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """List shipping options for a cart from Medusa."""
    params = {"cart_id": cart_id}

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_SHIPPING_OPTIONS_PATH,
        params=params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid shipping options response.",
        )

    options = result.get("shipping_options", [])
    if not isinstance(options, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid shipping options data.",
        )

    return options


def medusa_add_shipping_method(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    option_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Add a shipping method to a cart in Medusa."""
    payload = {"option_id": option_id}

    path = _MEDUSA_STORE_SHIPPING_METHODS_PATH.format(cart_id=cart_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid shipping method response.",
        )

    cart = result.get("cart") or result
    if not isinstance(cart, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart data.",
        )

    return cart


# =============================================================================
# Payment Operations
# =============================================================================


def medusa_list_payment_providers(
    *,
    config: MedusaStoreConfig,
    region_id: str,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """List payment providers for a region from Medusa."""
    params = {"region_id": region_id}

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="GET",
        path=_MEDUSA_STORE_PAYMENT_PROVIDERS_PATH,
        params=params,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment providers response.",
        )

    providers = result.get("payment_providers", [])
    if not isinstance(providers, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment providers data.",
        )

    return providers


def medusa_create_payment_collection(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Create a payment collection for a cart in Medusa."""
    payload = {"cart_id": cart_id}

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=_MEDUSA_STORE_PAYMENT_COLLECTIONS_PATH,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment collection response.",
        )

    collection = result.get("payment_collection") or result
    if not isinstance(collection, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment collection data.",
        )

    return collection


def medusa_initialize_payment_session(
    *,
    config: MedusaStoreConfig,
    payment_collection_id: str,
    provider_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Initialize a payment session for a payment collection in Medusa."""
    payload = {"provider_id": provider_id}

    path = _MEDUSA_STORE_PAYMENT_SESSIONS_PATH.format(id=payment_collection_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        json_body=payload,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment session response.",
        )

    collection = result.get("payment_collection") or result
    if not isinstance(collection, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid payment collection data.",
        )

    return collection


# =============================================================================
# Checkout Completion
# =============================================================================


def medusa_complete_cart(
    *,
    config: MedusaStoreConfig,
    cart_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Complete a cart and create an order in Medusa."""
    path = _MEDUSA_STORE_CART_COMPLETE_PATH.format(cart_id=cart_id)

    result = _make_medusa_store_request(
        base_url=config.base_url,
        publishable_key=config.publishable_key,
        method="POST",
        path=path,
        timeout_seconds=timeout_seconds,
    )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid cart completion response.",
        )

    # Medusa returns { type: "order", order: {... } } or { type: "cart", cart: {... } }
    # The latter indicates the cart is not ready for completion
    response_type = result.get("type")
    if response_type == "cart":
        # Cart is not ready for completion
        cart = result.get("cart", {})
        errors = cart.get("errors", []) if isinstance(cart, dict) else []
        error_messages = []
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict):
                    error_messages.append(error.get("message", str(error)))
                elif isinstance(error, str):
                    error_messages.append(error)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cart is not ready for completion: {'; '.join(error_messages) if error_messages else 'Unknown error'}",
        )

    order = result.get("order")
    if not isinstance(order, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Medusa Store API returned invalid order data.",
        )

    return order


# =============================================================================
# Convenience Functions
# =============================================================================


def get_medusa_store_config(
    *,
    session: Session,
    org_id: str,
    client_id: str,
) -> MedusaStoreConfig | None:
    """Get Medusa Store config if available, without raising errors."""
    config = get_client_medusa_config(
        session=session,
        org_id=org_id,
        client_id=client_id,
    )
    if not config:
        return None
    if not config.base_url or not config.publishable_key_encrypted:
        return None
    return MedusaStoreConfig(
        base_url=config.base_url,
        publishable_key=config.publishable_key_encrypted,
    )
