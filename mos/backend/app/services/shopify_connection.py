from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.config import settings

_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
_REQUIRED_SHOPIFY_SCOPES = {
    "read_orders",
    "write_orders",
    "unauthenticated_read_product_listings",
    "read_products",
    "write_products",
    "read_discounts",
    "write_discounts",
}
_IMPLIED_SHOPIFY_SCOPES: dict[str, set[str]] = {
    "write_orders": {"read_orders"},
    "write_products": {"read_products"},
    "write_discounts": {"read_discounts"},
}


@dataclass(frozen=True)
class ShopifyInstallation:
    shop_domain: str
    client_id: str | None
    has_storefront_access_token: bool
    scopes: list[str]
    uninstalled_at: str | None


def _effective_shopify_scopes(scopes: list[str]) -> set[str]:
    normalized = {scope.strip().lower() for scope in scopes if scope and scope.strip()}
    effective = set(normalized)
    for scope in list(normalized):
        effective.update(_IMPLIED_SHOPIFY_SCOPES.get(scope, set()))
    return effective


def _require_checkout_service_config() -> tuple[str, str]:
    if not settings.SHOPIFY_APP_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Shopify checkout bridge is not configured in mos/backend. "
                "Set SHOPIFY_APP_BASE_URL and restart backend."
            ),
        )
    if not settings.SHOPIFY_INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Shopify checkout bridge auth is not configured in mos/backend. "
                "Set SHOPIFY_INTERNAL_API_TOKEN (must match the bridge token configured "
                "in shopify-funnel-app) and restart backend."
            ),
        )
    return settings.SHOPIFY_APP_BASE_URL.rstrip("/"), settings.SHOPIFY_INTERNAL_API_TOKEN


def _error_detail_from_response(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text or response.reason_phrase

    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
    return str(body)


def _bridge_request(*, method: str, path: str, json_body: dict[str, Any] | None = None) -> Any:
    base_url, internal_token = _require_checkout_service_config()
    headers = {
        "Authorization": f"Bearer {internal_token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(method, f"{base_url}{path}", headers=headers, json=json_body)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify checkout app request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = _error_detail_from_response(response)
        status_code = response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=status_code,
            detail=f"Shopify checkout app error: {detail}",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid JSON.",
        ) from exc


def normalize_shop_domain(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned or not _SHOP_DOMAIN_RE.fullmatch(cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shopDomain must be a valid *.myshopify.com domain.",
        )
    return cleaned


def _normalize_currency_code(value: str) -> str:
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant currency must be a valid 3-letter ISO code.",
        )
    return cleaned


def list_shopify_installations() -> list[ShopifyInstallation]:
    payload = _bridge_request(method="GET", path="/admin/installations")
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid installations payload.",
        )

    installations: list[ShopifyInstallation] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        shop_domain = item.get("shopDomain")
        if not isinstance(shop_domain, str) or not shop_domain.strip():
            continue

        client_id = item.get("clientId")
        if client_id is not None and not isinstance(client_id, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid installation clientId.",
            )

        has_storefront = item.get("hasStorefrontAccessToken")
        if not isinstance(has_storefront, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid installation token flag.",
            )

        scopes = item.get("scopes")
        if not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid installation scopes.",
            )

        uninstalled_at = item.get("uninstalledAt")
        if uninstalled_at is not None and not isinstance(uninstalled_at, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid installation uninstalledAt value.",
            )

        installations.append(
            ShopifyInstallation(
                shop_domain=shop_domain.strip().lower(),
                client_id=client_id,
                has_storefront_access_token=has_storefront,
                scopes=[scope.strip() for scope in scopes if scope.strip()],
                uninstalled_at=uninstalled_at,
            )
        )

    return installations


def get_client_shopify_connection_status(*, client_id: str, selected_shop_domain: str | None = None) -> dict[str, Any]:
    installations = list_shopify_installations()
    active_for_client = [
        installation
        for installation in installations
        if installation.client_id == client_id and installation.uninstalled_at is None
    ]
    normalized_selected_shop: str | None = None
    if selected_shop_domain is not None:
        normalized_selected_shop = normalize_shop_domain(selected_shop_domain)

    if not active_for_client:
        return {
            "state": "not_connected",
            "message": "Shopify is not connected for this workspace.",
            "shopDomain": None,
            "shopDomains": [],
            "selectedShopDomain": normalized_selected_shop,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    selected_installation = None
    if normalized_selected_shop is not None:
        selected_installation = next(
            (installation for installation in active_for_client if installation.shop_domain == normalized_selected_shop),
            None,
        )

    if len(active_for_client) > 1 and selected_installation is None:
        detail = "Multiple active Shopify stores are linked to this workspace. Choose one store explicitly."
        if normalized_selected_shop is not None:
            detail = (
                f"Selected default Shopify store ({normalized_selected_shop}) is not active for this workspace. "
                "Choose one store explicitly."
            )
        return {
            "state": "multiple_installations_conflict",
            "message": detail,
            "shopDomain": None,
            "shopDomains": sorted(installation.shop_domain for installation in active_for_client),
            "selectedShopDomain": normalized_selected_shop,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    installation = selected_installation or active_for_client[0]
    effective_scopes = _effective_shopify_scopes(installation.scopes)
    missing_scopes = sorted(_REQUIRED_SHOPIFY_SCOPES.difference(effective_scopes))
    if missing_scopes:
        return {
            "state": "error",
            "message": (
                "Shopify app install is missing required Admin API scopes. "
                "If scopes were recently changed, reconnect/reinstall the app for this store."
            ),
            "shopDomain": installation.shop_domain,
            "shopDomains": [],
            "selectedShopDomain": normalized_selected_shop,
            "hasStorefrontAccessToken": installation.has_storefront_access_token,
            "missingScopes": missing_scopes,
        }

    if not installation.has_storefront_access_token:
        return {
            "state": "installed_missing_storefront_token",
            "message": "Shopify is installed but missing storefront access token.",
            "shopDomain": installation.shop_domain,
            "shopDomains": [],
            "selectedShopDomain": normalized_selected_shop,
            "hasStorefrontAccessToken": False,
            "missingScopes": [],
        }

    return {
        "state": "ready",
        "message": "Shopify connection is ready.",
        "shopDomain": installation.shop_domain,
        "shopDomains": [],
        "selectedShopDomain": normalized_selected_shop,
        "hasStorefrontAccessToken": True,
        "missingScopes": [],
    }


def list_client_shopify_products(
    *,
    client_id: str,
    query: str | None = None,
    limit: int = 20,
    shop_domain: str | None = None,
) -> dict[str, Any]:
    trimmed_query = (query or "").strip()
    if len(trimmed_query) > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query is too long (max 120 characters).",
        )
    if limit < 1 or limit > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be between 1 and 50.",
        )

    request_payload: dict[str, Any] = {"query": trimmed_query or None, "limit": limit}
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/catalog/products/list",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid products payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid products shopDomain.",
        )

    raw_products = payload.get("products")
    if not isinstance(raw_products, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid products list.",
        )

    products: list[dict[str, str]] = []
    for item in raw_products:
        if not isinstance(item, dict):
            continue
        product_gid = item.get("productGid")
        title = item.get("title")
        handle = item.get("handle")
        product_status = item.get("status")
        if not isinstance(product_gid, str) or not product_gid:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned product without productGid.",
            )
        if not isinstance(title, str) or not title:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned product without title.",
            )
        if not isinstance(handle, str) or not handle:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned product without handle.",
            )
        if not isinstance(product_status, str) or not product_status:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned product without status.",
            )

        products.append(
            {
                "productGid": product_gid,
                "title": title,
                "handle": handle,
                "status": product_status,
            }
        )

    return {"shopDomain": response_shop_domain.strip().lower(), "products": products}


def create_client_shopify_product(
    *,
    client_id: str,
    title: str,
    variants: list[dict[str, Any]],
    description: str | None = None,
    handle: str | None = None,
    vendor: str | None = None,
    product_type: str | None = None,
    tags: list[str] | None = None,
    status_text: str = "DRAFT",
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_title = title.strip()
    if not cleaned_title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required.")

    cleaned_status = status_text.strip().upper()
    if cleaned_status not in {"ACTIVE", "DRAFT"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='status must be "ACTIVE" or "DRAFT".')

    if not variants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="variants must contain at least one item.")

    cleaned_variants: list[dict[str, Any]] = []
    seen_variant_titles: set[str] = set()
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each variant must be an object.")
        raw_title = raw_variant.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each variant requires a non-empty title.")
        normalized_title = raw_title.strip()
        lower_title = normalized_title.lower()
        if lower_title in seen_variant_titles:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variant titles must be unique.")
        seen_variant_titles.add(lower_title)

        raw_price = raw_variant.get("priceCents")
        if not isinstance(raw_price, int) or raw_price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires a non-negative integer priceCents.",
            )

        raw_currency = raw_variant.get("currency")
        if not isinstance(raw_currency, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each variant requires currency.")
        cleaned_currency = _normalize_currency_code(raw_currency)

        cleaned_variants.append(
            {
                "title": normalized_title,
                "priceCents": raw_price,
                "currency": cleaned_currency,
            }
        )

    first_currency = cleaned_variants[0]["currency"]
    if any(item["currency"] != first_currency for item in cleaned_variants):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All variants must use the same currency for Shopify product creation.",
        )

    cleaned_tags: list[str] = []
    for raw_tag in tags or []:
        if not isinstance(raw_tag, str):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tags must contain only strings.")
        cleaned_tag = raw_tag.strip()
        if not cleaned_tag:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tags cannot contain empty values.")
        cleaned_tags.append(cleaned_tag)

    request_payload: dict[str, Any] = {
        "title": cleaned_title,
        "description": description.strip() if isinstance(description, str) and description.strip() else None,
        "handle": handle.strip() if isinstance(handle, str) and handle.strip() else None,
        "vendor": vendor.strip() if isinstance(vendor, str) and vendor.strip() else None,
        "productType": product_type.strip() if isinstance(product_type, str) and product_type.strip() else None,
        "tags": cleaned_tags,
        "status": cleaned_status,
        "variants": cleaned_variants,
    }
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/catalog/products/create",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid create-product payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for created product.",
        )

    product_gid = payload.get("productGid")
    if not isinstance(product_gid, str) or not product_gid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid productGid for created product.",
        )

    product_title = payload.get("title")
    if not isinstance(product_title, str) or not product_title.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid title for created product.",
        )

    product_handle = payload.get("handle")
    if not isinstance(product_handle, str) or not product_handle.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid handle for created product.",
        )

    product_status = payload.get("status")
    if not isinstance(product_status, str) or not product_status.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid status for created product.",
        )

    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid variants for created product.",
        )

    response_variants: list[dict[str, Any]] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant object.",
            )
        variant_gid = raw_variant.get("variantGid")
        variant_title = raw_variant.get("title")
        variant_price_cents = raw_variant.get("priceCents")
        variant_currency = raw_variant.get("currency")

        if not isinstance(variant_gid, str) or not variant_gid.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variantGid.",
            )
        if not isinstance(variant_title, str) or not variant_title.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant title.",
            )
        if not isinstance(variant_price_cents, int) or variant_price_cents < 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant priceCents.",
            )
        if not isinstance(variant_currency, str) or not variant_currency.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant currency.",
            )

        response_variants.append(
            {
                "variantGid": variant_gid.strip(),
                "title": variant_title.strip(),
                "priceCents": variant_price_cents,
                "currency": _normalize_currency_code(variant_currency),
            }
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "productGid": product_gid.strip(),
        "title": product_title.strip(),
        "handle": product_handle.strip(),
        "status": product_status.strip(),
        "variants": response_variants,
    }


def build_client_shopify_install_url(*, client_id: str, shop_domain: str) -> str:
    normalized_shop = normalize_shop_domain(shop_domain)
    installations = list_shopify_installations()

    for installation in installations:
        if installation.uninstalled_at is not None:
            continue
        if installation.shop_domain != normalized_shop:
            continue
        if installation.client_id and installation.client_id != client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This Shopify store is already connected to a different workspace. "
                    f"connectedWorkspaceId={installation.client_id}"
                ),
            )

    base_url, _ = _require_checkout_service_config()
    query = urlencode({"shop": normalized_shop, "client_id": client_id})
    return f"{base_url}/auth/install?{query}"


def set_client_shopify_storefront_token(
    *,
    client_id: str,
    shop_domain: str,
    storefront_access_token: str,
) -> None:
    normalized_shop = normalize_shop_domain(shop_domain)
    token = storefront_access_token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="storefrontAccessToken cannot be empty.",
        )

    installations = list_shopify_installations()
    active_installation = next(
        (
            installation
            for installation in installations
            if installation.shop_domain == normalized_shop and installation.uninstalled_at is None
        ),
        None,
    )
    if not active_installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify installation not found for this store.",
        )

    if active_installation.client_id and active_installation.client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Shopify store is already connected to a different workspace.",
        )

    _bridge_request(
        method="PATCH",
        path=f"/admin/installations/{normalized_shop}",
        json_body={
            "clientId": client_id,
            "storefrontAccessToken": token,
        },
    )


def disconnect_client_shopify_store(
    *,
    client_id: str,
    shop_domain: str,
) -> None:
    normalized_shop = normalize_shop_domain(shop_domain)

    installations = list_shopify_installations()
    active_installation = next(
        (
            installation
            for installation in installations
            if installation.shop_domain == normalized_shop and installation.uninstalled_at is None
        ),
        None,
    )
    if not active_installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopify installation not found for this store.",
        )

    if active_installation.client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This Shopify store is not connected to this workspace. "
                f"connectedWorkspaceId={active_installation.client_id}"
            ),
        )

    _bridge_request(
        method="PATCH",
        path=f"/admin/installations/{normalized_shop}",
        json_body={"clientId": None},
    )
