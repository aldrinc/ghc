from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, status

from app.config import settings

_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
_STOREFRONT_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
_SHOPIFY_PRODUCT_GID_PREFIX = "gid://shopify/Product/"
_SHOPIFY_VARIANT_GID_PREFIX = "gid://shopify/ProductVariant/"
_SHOPIFY_THEME_GID_PREFIX = "gid://shopify/OnlineStoreTheme/"
_SHOP_DOMAIN_RESOLUTION_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SHOP_DOMAIN_RESOLUTION_MAX_REDIRECTS = 5
_SHOP_DOMAIN_RESOLUTION_TIMEOUT_SECONDS = 10.0
_SHOPIFY_STOREFRONT_HTML_SHOP_PATTERNS = (
    re.compile(
        r"""Shopify\.shop\s*=\s*["'](?P<shop>[a-z0-9][a-z0-9-]*\.myshopify\.com)["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""["']myshopifyDomain["']\s*:\s*["'](?P<shop>[a-z0-9][a-z0-9-]*\.myshopify\.com)["']""",
        re.IGNORECASE,
    ),
)
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
    base_url = settings.SHOPIFY_APP_BASE_URL
    internal_token = settings.SHOPIFY_INTERNAL_API_TOKEN
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Shopify app bridge is not configured in mos/backend. "
                "Set SHOPIFY_APP_BASE_URL and restart backend."
            ),
        )
    if not internal_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Shopify app bridge token is not configured in mos/backend. "
                "Set SHOPIFY_INTERNAL_API_TOKEN and restart backend."
            ),
        )
    return base_url.rstrip("/"), internal_token


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


def _shop_domain_input_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def _normalize_storefront_url(raw_value: str) -> tuple[str, str]:
    if not isinstance(raw_value, str):
        raise _shop_domain_input_error("shopDomain must be a string.")

    raw = raw_value.strip()
    if not raw:
        raise _shop_domain_input_error("shopDomain cannot be empty.")
    if any(char.isspace() for char in raw):
        raise _shop_domain_input_error(
            "shopDomain must not contain whitespace characters."
        )

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise _shop_domain_input_error(
            "shopDomain must be a *.myshopify.com domain or an http(s) storefront URL."
        )

    if parsed.username or parsed.password or parsed.port is not None:
        raise _shop_domain_input_error(
            "shopDomain must not include credentials or a port."
        )

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise _shop_domain_input_error(
            "shopDomain must be a valid *.myshopify.com domain or custom storefront domain."
        )
    if not (
        _SHOP_DOMAIN_RE.fullmatch(host) or _STOREFRONT_DOMAIN_RE.fullmatch(host)
    ):
        raise _shop_domain_input_error(
            "shopDomain must be a valid *.myshopify.com domain or custom storefront domain."
        )

    normalized_url = urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))
    return host, normalized_url


def _extract_shopify_shop_domain_from_storefront_response(
    response: httpx.Response,
) -> str | None:
    response_text = response.text if isinstance(response.text, str) else ""
    if not response_text:
        return None

    for pattern in _SHOPIFY_STOREFRONT_HTML_SHOP_PATTERNS:
        match = pattern.search(response_text)
        if not match:
            continue
        shop_domain = str(match.group("shop")).strip().lower()
        if _SHOP_DOMAIN_RE.fullmatch(shop_domain):
            return shop_domain
    return None


def _resolve_redirected_shop_domain(*, source_host: str, start_url: str) -> str:
    timeout = httpx.Timeout(
        timeout=_SHOP_DOMAIN_RESOLUTION_TIMEOUT_SECONDS,
        connect=min(_SHOP_DOMAIN_RESOLUTION_TIMEOUT_SECONDS, 5.0),
    )

    current_url = start_url
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for _ in range(_SHOP_DOMAIN_RESOLUTION_MAX_REDIRECTS + 1):
                response = client.get(
                    current_url,
                    headers={"User-Agent": "mOS Shopify domain resolver"},
                )
                resolved_host, _ = _normalize_storefront_url(str(response.url))
                if _SHOP_DOMAIN_RE.fullmatch(resolved_host):
                    return resolved_host

                storefront_shop_domain = (
                    _extract_shopify_shop_domain_from_storefront_response(response)
                )
                if storefront_shop_domain is not None:
                    return storefront_shop_domain

                if response.status_code not in _SHOP_DOMAIN_RESOLUTION_REDIRECT_STATUSES:
                    break

                location = response.headers.get("location")
                if not isinstance(location, str) or not location.strip():
                    break

                next_url = urljoin(current_url, location.strip())
                next_host, normalized_next_url = _normalize_storefront_url(next_url)
                if _SHOP_DOMAIN_RE.fullmatch(next_host):
                    return next_host
                current_url = normalized_next_url
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Timed out while resolving Shopify storefront domain. "
                f"Enter the store *.myshopify.com domain directly if this keeps happening. sourceHost={source_host}"
            ),
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Failed to resolve Shopify storefront domain. "
                f"Enter the store *.myshopify.com domain directly if the custom domain is not redirecting correctly. sourceHost={source_host}"
            ),
        ) from exc

    raise _shop_domain_input_error(
        "Custom storefront domain did not resolve to a Shopify *.myshopify.com domain. "
        f"Enter the store *.myshopify.com domain directly or use a storefront domain that redirects to it. sourceHost={source_host}"
    )


def _bridge_request(
    *,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    base_url, internal_token = _require_checkout_service_config()
    headers = {
        "Authorization": f"Bearer {internal_token}",
        "Content-Type": "application/json",
    }
    resolved_timeout_seconds = (
        timeout_seconds
        if isinstance(timeout_seconds, (int, float)) and timeout_seconds > 0
        else settings.SHOPIFY_CHECKOUT_REQUEST_TIMEOUT_SECONDS
    )
    request_timeout = httpx.Timeout(
        timeout=resolved_timeout_seconds,
        connect=min(resolved_timeout_seconds, 10.0),
    )

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.request(
                method, f"{base_url}{path}", headers=headers, json=json_body
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Shopify checkout app request timed out "
                f"after {resolved_timeout_seconds:.1f}s ({method} {path})."
            ),
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify checkout app request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail = _error_detail_from_response(response)
        status_code = (
            response.status_code
            if response.status_code < 500
            else status.HTTP_502_BAD_GATEWAY
        )
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
    host, normalized_url = _normalize_storefront_url(value)
    if _SHOP_DOMAIN_RE.fullmatch(host):
        return host
    return _resolve_redirected_shop_domain(source_host=host, start_url=normalized_url)


def normalize_shop_storefront_domain(value: str) -> str:
    host, _ = _normalize_storefront_url(value)
    return host


def _normalize_currency_code(value: str) -> str:
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Variant currency must be a valid 3-letter ISO code.",
        )
    return cleaned


def _validate_shopify_variant_gid(value: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith(_SHOPIFY_VARIANT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variantGid must be a Shopify variant GID.",
        )
    return cleaned


def update_client_shopify_variant(
    *,
    client_id: str,
    variant_gid: str,
    fields: dict[str, Any],
    shop_domain: str | None = None,
) -> dict[str, str]:
    cleaned_variant_gid = variant_gid.strip()
    if not cleaned_variant_gid.startswith(_SHOPIFY_VARIANT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variantGid must be a Shopify variant GID.",
        )
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one variant update field is required.",
        )

    supported_fields = {
        "title",
        "priceCents",
        "compareAtPriceCents",
        "sku",
        "barcode",
        "inventoryPolicy",
        "inventoryManagement",
    }
    unsupported_fields = sorted(
        name for name in fields.keys() if name not in supported_fields
    )
    if unsupported_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported Shopify variant update fields: {', '.join(unsupported_fields)}.",
        )

    request_payload: dict[str, Any] = {"variantGid": cleaned_variant_gid}
    if "title" in fields:
        raw_title = fields["title"]
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="title must be a non-empty string.",
            )
        request_payload["title"] = raw_title.strip()

    if "priceCents" in fields:
        raw_price_cents = fields["priceCents"]
        if not isinstance(raw_price_cents, int) or raw_price_cents < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="priceCents must be a non-negative integer.",
            )
        request_payload["priceCents"] = raw_price_cents

    if "compareAtPriceCents" in fields:
        raw_compare_at_price_cents = fields["compareAtPriceCents"]
        if raw_compare_at_price_cents is not None and (
            not isinstance(raw_compare_at_price_cents, int)
            or raw_compare_at_price_cents < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="compareAtPriceCents must be null or a non-negative integer.",
            )
        request_payload["compareAtPriceCents"] = raw_compare_at_price_cents

    if "sku" in fields:
        raw_sku = fields["sku"]
        if raw_sku is not None and (
            not isinstance(raw_sku, str) or not raw_sku.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="sku must be null or a non-empty string.",
            )
        request_payload["sku"] = raw_sku.strip() if isinstance(raw_sku, str) else None

    if "barcode" in fields:
        raw_barcode = fields["barcode"]
        if raw_barcode is not None and (
            not isinstance(raw_barcode, str) or not raw_barcode.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="barcode must be null or a non-empty string.",
            )
        request_payload["barcode"] = (
            raw_barcode.strip() if isinstance(raw_barcode, str) else None
        )

    if "inventoryPolicy" in fields:
        raw_inventory_policy = fields["inventoryPolicy"]
        if (
            not isinstance(raw_inventory_policy, str)
            or not raw_inventory_policy.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inventoryPolicy must be one of: deny, continue.",
            )
        normalized_inventory_policy = raw_inventory_policy.strip().lower()
        if normalized_inventory_policy not in {"deny", "continue"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="inventoryPolicy must be one of: deny, continue.",
            )
        request_payload["inventoryPolicy"] = normalized_inventory_policy

    if "inventoryManagement" in fields:
        raw_inventory_management = fields["inventoryManagement"]
        if raw_inventory_management is not None:
            if (
                not isinstance(raw_inventory_management, str)
                or not raw_inventory_management.strip()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="inventoryManagement must be null or 'shopify'.",
                )
            normalized_inventory_management = raw_inventory_management.strip().lower()
            if normalized_inventory_management != "shopify":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="inventoryManagement must be null or 'shopify'.",
                )
            request_payload["inventoryManagement"] = normalized_inventory_management
        else:
            request_payload["inventoryManagement"] = None

    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="PATCH",
        path="/v1/catalog/variants",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid update-variant payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for updated variant.",
        )

    response_product_gid = payload.get("productGid")
    if not isinstance(response_product_gid, str) or not response_product_gid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid productGid for updated variant.",
        )

    response_variant_gid = payload.get("variantGid")
    if not isinstance(response_variant_gid, str) or not response_variant_gid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid variantGid for updated variant.",
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "productGid": response_product_gid.strip(),
        "variantGid": response_variant_gid.strip(),
    }


def list_shopify_installations() -> list[ShopifyInstallation]:
    payload = _bridge_request(
        method="GET",
        path="/admin/installations",
    )
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
        if not isinstance(scopes, list) or any(
            not isinstance(scope, str) for scope in scopes
        ):
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


def get_client_shopify_connection_status(
    *, client_id: str, selected_shop_domain: str | None = None
) -> dict[str, Any]:
    normalized_selected_shop: str | None = None
    if selected_shop_domain is not None:
        normalized_selected_shop = normalize_shop_domain(selected_shop_domain)

    def _resolve_status(
        *,
        installations: list[ShopifyInstallation],
        require_storefront_token: bool,
        enforce_required_scopes: bool,
    ) -> dict[str, Any]:
        active_for_client = [
            installation
            for installation in installations
            if installation.client_id == client_id and installation.uninstalled_at is None
        ]
        active_shop_domains = sorted(
            {installation.shop_domain for installation in active_for_client}
        )
        if not active_for_client:
            return {
                "state": "not_installed",
                "message": "Shopify is not installed for this workspace.",
                "installation": None,
                "shopDomains": active_shop_domains,
                "missingScopes": [],
            }

        selected_installation = None
        if normalized_selected_shop is not None:
            selected_installation = next(
                (
                    installation
                    for installation in active_for_client
                    if installation.shop_domain == normalized_selected_shop
                ),
                None,
            )

        if normalized_selected_shop is not None and selected_installation is None:
            return {
                "state": "conflict",
                "message": (
                    f"Selected default Shopify store ({normalized_selected_shop}) is not active "
                    "for this workspace. Choose one store explicitly."
                ),
                "installation": None,
                "shopDomains": active_shop_domains,
                "missingScopes": [],
            }

        if len(active_for_client) > 1 and selected_installation is None:
            return {
                "state": "conflict",
                "message": (
                    "Multiple active Shopify stores are linked to this workspace. "
                    "Choose one store explicitly."
                ),
                "installation": None,
                "shopDomains": active_shop_domains,
                "missingScopes": [],
            }

        installation = selected_installation or active_for_client[0]
        missing_scopes: list[str] = []
        if enforce_required_scopes:
            effective_scopes = _effective_shopify_scopes(installation.scopes)
            missing_scopes = sorted(_REQUIRED_SHOPIFY_SCOPES.difference(effective_scopes))
            if missing_scopes:
                return {
                    "state": "error",
                    "message": (
                        "Shopify app install is missing required Admin API scopes. "
                        "If scopes were recently changed, reconnect/reinstall the app for this store."
                    ),
                    "installation": installation,
                    "shopDomains": active_shop_domains,
                    "missingScopes": missing_scopes,
                }

        if require_storefront_token and not installation.has_storefront_access_token:
            return {
                "state": "installed_missing_storefront_token",
                "message": "Shopify is installed but missing storefront access token.",
                "installation": installation,
                "shopDomains": active_shop_domains,
                "missingScopes": missing_scopes,
            }

        return {
            "state": "installed",
            "message": "Shopify installation is active.",
            "installation": installation,
            "shopDomains": active_shop_domains,
            "missingScopes": missing_scopes,
        }

    installations = list_shopify_installations()
    resolved_status = _resolve_status(
        installations=installations,
        require_storefront_token=True,
        enforce_required_scopes=True,
    )

    resolved_state = resolved_status["state"]
    if resolved_state == "not_installed":
        state = "not_connected"
        message = "Shopify app is not connected for this workspace."
    elif resolved_state == "conflict":
        state = "multiple_installations_conflict"
        message = str(resolved_status["message"])
    elif resolved_state == "installed_missing_storefront_token":
        state = "installed_missing_storefront_token"
        message = str(resolved_status["message"])
    elif resolved_state == "error":
        state = "error"
        message = str(resolved_status["message"])
    else:
        state = "ready"
        message = "Shopify connection is ready."

    installation: ShopifyInstallation | None = resolved_status["installation"]

    return {
        "state": state,
        "message": message,
        "shopDomain": installation.shop_domain if installation else None,
        "shopDomains": resolved_status["shopDomains"],
        "selectedShopDomain": normalized_selected_shop,
        "hasStorefrontAccessToken": (
            installation.has_storefront_access_token
            if installation is not None
            else False
        ),
        "missingScopes": resolved_status["missingScopes"],
        "installationState": resolved_state,
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


def get_client_shopify_product(
    *,
    client_id: str,
    product_gid: str,
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_product_gid = product_gid.strip()
    if not cleaned_product_gid.startswith(_SHOPIFY_PRODUCT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productGid must be a Shopify product GID.",
        )

    request_payload: dict[str, Any] = {"productGid": cleaned_product_gid}
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/catalog/products/get",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product shopDomain.",
        )

    response_product_gid = payload.get("productGid")
    if not isinstance(response_product_gid, str) or not response_product_gid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid productGid.",
        )

    response_title = payload.get("title")
    if not isinstance(response_title, str) or not response_title.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product title.",
        )

    response_handle = payload.get("handle")
    if not isinstance(response_handle, str) or not response_handle.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product handle.",
        )

    response_status = payload.get("status")
    if not isinstance(response_status, str) or not response_status.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product status.",
        )
    response_product_type_raw = payload.get("productType")
    response_product_type = None
    if response_product_type_raw is not None:
        if not isinstance(response_product_type_raw, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid productType.",
            )
        cleaned_product_type = response_product_type_raw.strip()
        response_product_type = cleaned_product_type or None

    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid product variants list.",
        )

    parsed_variants: list[dict[str, Any]] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid product variant object.",
            )

        variant_gid = raw_variant.get("variantGid")
        title = raw_variant.get("title")
        price_cents = raw_variant.get("priceCents")
        currency = raw_variant.get("currency")
        compare_at_price_cents = raw_variant.get("compareAtPriceCents")
        sku = raw_variant.get("sku")
        barcode = raw_variant.get("barcode")
        taxable = raw_variant.get("taxable")
        requires_shipping = raw_variant.get("requiresShipping")
        inventory_policy = raw_variant.get("inventoryPolicy")
        inventory_management = raw_variant.get("inventoryManagement")
        inventory_quantity = raw_variant.get("inventoryQuantity")
        option_values = raw_variant.get("optionValues")

        if not isinstance(variant_gid, str) or not variant_gid.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variantGid in product payload.",
            )
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant title in product payload.",
            )
        if not isinstance(price_cents, int) or price_cents < 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant priceCents in product payload.",
            )
        if not isinstance(currency, str) or not currency.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant currency in product payload.",
            )
        if compare_at_price_cents is not None and (
            not isinstance(compare_at_price_cents, int) or compare_at_price_cents < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid compareAtPriceCents in product payload.",
            )
        if sku is not None and not isinstance(sku, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid sku in product payload.",
            )
        if barcode is not None and not isinstance(barcode, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid barcode in product payload.",
            )
        if not isinstance(taxable, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid taxable flag in product payload.",
            )
        if not isinstance(requires_shipping, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid requiresShipping flag in product payload.",
            )
        if inventory_policy is not None and not isinstance(inventory_policy, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryPolicy in product payload.",
            )
        if inventory_management is not None and not isinstance(
            inventory_management, str
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryManagement in product payload.",
            )
        if inventory_quantity is not None and not isinstance(inventory_quantity, int):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryQuantity in product payload.",
            )
        if not isinstance(option_values, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid optionValues in product payload.",
            )
        for option_key, option_value in option_values.items():
            if (
                not isinstance(option_key, str)
                or not option_key.strip()
                or not isinstance(option_value, str)
            ):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Shopify checkout app returned non-string optionValues in product payload.",
                )

        parsed_variants.append(
            {
                "variantGid": variant_gid.strip(),
                "title": title.strip(),
                "priceCents": price_cents,
                "currency": _normalize_currency_code(currency),
                "compareAtPriceCents": compare_at_price_cents,
                "sku": sku.strip() if isinstance(sku, str) else None,
                "barcode": barcode.strip() if isinstance(barcode, str) else None,
                "taxable": taxable,
                "requiresShipping": requires_shipping,
                "inventoryPolicy": (
                    inventory_policy.strip().lower()
                    if isinstance(inventory_policy, str)
                    else None
                ),
                "inventoryManagement": (
                    inventory_management.strip().lower()
                    if isinstance(inventory_management, str)
                    else None
                ),
                "inventoryQuantity": inventory_quantity,
                "optionValues": {
                    key.strip(): value for key, value in option_values.items()
                },
            }
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "productGid": response_product_gid.strip(),
        "title": response_title.strip(),
        "handle": response_handle.strip(),
        "status": response_status.strip(),
        "productType": response_product_type,
        "variants": parsed_variants,
    }


def sync_client_shopify_catalog_collection(
    *,
    client_id: str,
    product_gids: list[str],
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_product_gids: list[str] = []
    seen_product_gids: set[str] = set()
    for raw_product_gid in product_gids:
        if not isinstance(raw_product_gid, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="productGids must contain only Shopify product GIDs.",
            )
        cleaned_product_gid = raw_product_gid.strip()
        if not cleaned_product_gid.startswith(_SHOPIFY_PRODUCT_GID_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="productGids must contain only Shopify product GIDs.",
            )
        if cleaned_product_gid in seen_product_gids:
            continue
        seen_product_gids.add(cleaned_product_gid)
        cleaned_product_gids.append(cleaned_product_gid)

    request_payload: dict[str, Any] = {"productGids": cleaned_product_gids}
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/catalog/collection/sync",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid catalog collection sync payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid catalog collection sync shopDomain.",
        )

    response_collection_id = payload.get("collectionId")
    if not isinstance(response_collection_id, str) or not response_collection_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid catalog collection id.",
        )

    response_collection_handle = payload.get("collectionHandle")
    if (
        not isinstance(response_collection_handle, str)
        or not response_collection_handle.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid catalog collection handle.",
        )

    response_collection_title = payload.get("collectionTitle")
    if (
        not isinstance(response_collection_title, str)
        or not response_collection_title.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid catalog collection title.",
        )

    requested_product_count = payload.get("requestedProductCount")
    if not isinstance(requested_product_count, int) or requested_product_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid requestedProductCount.",
        )

    added_product_count = payload.get("addedProductCount")
    if not isinstance(added_product_count, int) or added_product_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid addedProductCount.",
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "collectionId": response_collection_id.strip(),
        "collectionHandle": response_collection_handle.strip(),
        "collectionTitle": response_collection_title.strip(),
        "requestedProductCount": requested_product_count,
        "addedProductCount": added_product_count,
    }


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="title is required."
        )

    cleaned_status = status_text.strip().upper()
    if cleaned_status not in {"ACTIVE", "DRAFT"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='status must be "ACTIVE" or "DRAFT".',
        )

    if not variants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variants must contain at least one item.",
        )

    cleaned_variants: list[dict[str, Any]] = []
    seen_variant_titles: set[str] = set()
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant must be an object.",
            )
        raw_title = raw_variant.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires a non-empty title.",
            )
        normalized_title = raw_title.strip()
        lower_title = normalized_title.lower()
        if lower_title in seen_variant_titles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant titles must be unique.",
            )
        seen_variant_titles.add(lower_title)

        raw_price = raw_variant.get("priceCents")
        if not isinstance(raw_price, int) or raw_price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires a non-negative integer priceCents.",
            )

        raw_currency = raw_variant.get("currency")
        if not isinstance(raw_currency, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires currency.",
            )
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags must contain only strings.",
            )
        cleaned_tag = raw_tag.strip()
        if not cleaned_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags cannot contain empty values.",
            )
        cleaned_tags.append(cleaned_tag)

    request_payload: dict[str, Any] = {
        "title": cleaned_title,
        "description": (
            description.strip()
            if isinstance(description, str) and description.strip()
            else None
        ),
        "handle": (
            handle.strip() if isinstance(handle, str) and handle.strip() else None
        ),
        "vendor": (
            vendor.strip() if isinstance(vendor, str) and vendor.strip() else None
        ),
        "productType": (
            product_type.strip()
            if isinstance(product_type, str) and product_type.strip()
            else None
        ),
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


def sync_client_shopify_product(
    *,
    client_id: str,
    product_gid: str,
    title: str,
    variants: list[dict[str, Any]],
    source_of_truth_payload: dict[str, Any],
    description: str | None = None,
    handle: str | None = None,
    vendor: str | None = None,
    product_type: str | None = None,
    tags: list[str] | None = None,
    status_text: str = "DRAFT",
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_product_gid = product_gid.strip()
    if not cleaned_product_gid.startswith(_SHOPIFY_PRODUCT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="productGid must be a Shopify product GID.",
        )

    cleaned_title = title.strip()
    if not cleaned_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="title is required.",
        )

    if not isinstance(source_of_truth_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sourceOfTruthPayload must be an object.",
        )

    cleaned_status = status_text.strip().upper()
    if cleaned_status not in {"ACTIVE", "DRAFT"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='status must be "ACTIVE" or "DRAFT".',
        )

    if not variants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="variants must contain at least one item.",
        )

    cleaned_variants: list[dict[str, Any]] = []
    seen_variant_titles: set[str] = set()
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant must be an object.",
            )

        raw_source_variant_id = raw_variant.get("sourceVariantId")
        if not isinstance(raw_source_variant_id, str) or not raw_source_variant_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires sourceVariantId.",
            )
        source_variant_id = raw_source_variant_id.strip()

        raw_title = raw_variant.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires a non-empty title.",
            )
        normalized_title = raw_title.strip()
        lower_title = normalized_title.lower()
        if lower_title in seen_variant_titles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant titles must be unique.",
            )
        seen_variant_titles.add(lower_title)

        raw_price = raw_variant.get("priceCents")
        if not isinstance(raw_price, int) or raw_price < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires a non-negative integer priceCents.",
            )

        raw_currency = raw_variant.get("currency")
        if not isinstance(raw_currency, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each variant requires currency.",
            )
        cleaned_currency = _normalize_currency_code(raw_currency)

        cleaned_variant_gid: str | None = None
        raw_variant_gid = raw_variant.get("variantGid")
        if raw_variant_gid is not None:
            if not isinstance(raw_variant_gid, str) or not raw_variant_gid.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="variantGid must be null or a non-empty Shopify variant GID.",
                )
            cleaned_variant_gid = _validate_shopify_variant_gid(raw_variant_gid)

        raw_compare_at_price = raw_variant.get("compareAtPriceCents")
        if raw_compare_at_price is not None and (
            not isinstance(raw_compare_at_price, int) or raw_compare_at_price < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="compareAtPriceCents must be null or a non-negative integer.",
            )

        cleaned_sku: str | None = None
        raw_sku = raw_variant.get("sku")
        if raw_sku is not None:
            if not isinstance(raw_sku, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="sku must be null or a string.",
                )
            cleaned_sku = raw_sku.strip() or None

        cleaned_barcode: str | None = None
        raw_barcode = raw_variant.get("barcode")
        if raw_barcode is not None:
            if not isinstance(raw_barcode, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="barcode must be null or a string.",
                )
            cleaned_barcode = raw_barcode.strip() or None

        raw_taxable = raw_variant.get("taxable")
        if raw_taxable is not None and not isinstance(raw_taxable, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="taxable must be null or a boolean.",
            )

        raw_requires_shipping = raw_variant.get("requiresShipping")
        if raw_requires_shipping is not None and not isinstance(raw_requires_shipping, bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="requiresShipping must be null or a boolean.",
            )

        raw_inventory_policy = raw_variant.get("inventoryPolicy")
        cleaned_inventory_policy: str | None = None
        if raw_inventory_policy is not None:
            if not isinstance(raw_inventory_policy, str) or not raw_inventory_policy.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="inventoryPolicy must be null or one of: deny, continue.",
                )
            cleaned_inventory_policy = raw_inventory_policy.strip().lower()
            if cleaned_inventory_policy not in {"deny", "continue"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="inventoryPolicy must be null or one of: deny, continue.",
                )

        raw_inventory_management = raw_variant.get("inventoryManagement")
        cleaned_inventory_management: str | None = None
        if raw_inventory_management is not None:
            if isinstance(raw_inventory_management, str) and raw_inventory_management.strip():
                cleaned_inventory_management = raw_inventory_management.strip().lower()
                if cleaned_inventory_management != "shopify":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="inventoryManagement must be null or 'shopify'.",
                    )

        raw_weight = raw_variant.get("weight")
        if raw_weight is not None and not isinstance(raw_weight, (int, float)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="weight must be null or a number.",
            )

        raw_weight_unit = raw_variant.get("weightUnit")
        cleaned_weight_unit: str | None = None
        if raw_weight_unit is not None:
            if not isinstance(raw_weight_unit, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="weightUnit must be null or a string.",
                )
            cleaned_weight_unit = raw_weight_unit.strip() or None

        cleaned_variants.append(
            {
                "sourceVariantId": source_variant_id,
                "variantGid": cleaned_variant_gid,
                "title": normalized_title,
                "priceCents": raw_price,
                "currency": cleaned_currency,
                "compareAtPriceCents": raw_compare_at_price,
                "sku": cleaned_sku,
                "barcode": cleaned_barcode,
                "taxable": raw_taxable,
                "requiresShipping": raw_requires_shipping,
                "inventoryPolicy": cleaned_inventory_policy,
                "inventoryManagement": cleaned_inventory_management,
                "weight": float(raw_weight) if isinstance(raw_weight, (int, float)) else None,
                "weightUnit": cleaned_weight_unit,
            }
        )

    first_currency = cleaned_variants[0]["currency"]
    if any(item["currency"] != first_currency for item in cleaned_variants):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All variants must use the same currency for Shopify product sync.",
        )

    cleaned_tags: list[str] = []
    for raw_tag in tags or []:
        if not isinstance(raw_tag, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags must contain only strings.",
            )
        cleaned_tag = raw_tag.strip()
        if not cleaned_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tags cannot contain empty values.",
            )
        cleaned_tags.append(cleaned_tag)

    request_payload: dict[str, Any] = {
        "productGid": cleaned_product_gid,
        "title": cleaned_title,
        "description": description.strip() if isinstance(description, str) else None,
        "handle": handle.strip() if isinstance(handle, str) and handle.strip() else None,
        "vendor": vendor.strip() if isinstance(vendor, str) and vendor.strip() else None,
        "productType": (
            product_type.strip()
            if isinstance(product_type, str) and product_type.strip()
            else None
        ),
        "tags": cleaned_tags,
        "status": cleaned_status,
        "variants": cleaned_variants,
        "sourceOfTruthPayload": source_of_truth_payload,
    }
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/catalog/products/sync",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid sync-product payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for synced product.",
        )

    response_product_gid = payload.get("productGid")
    if not isinstance(response_product_gid, str) or not response_product_gid.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid productGid for synced product.",
        )

    response_title = payload.get("title")
    if not isinstance(response_title, str) or not response_title.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid title for synced product.",
        )

    response_handle = payload.get("handle")
    if not isinstance(response_handle, str) or not response_handle.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid handle for synced product.",
        )

    response_status = payload.get("status")
    if not isinstance(response_status, str) or not response_status.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid status for synced product.",
        )

    created_count = payload.get("createdVariantCount")
    if not isinstance(created_count, int) or created_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid createdVariantCount.",
        )

    updated_count = payload.get("updatedVariantCount")
    if not isinstance(updated_count, int) or updated_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid updatedVariantCount.",
        )

    deleted_count = payload.get("deletedVariantCount")
    if not isinstance(deleted_count, int) or deleted_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid deletedVariantCount.",
        )

    offer_count = payload.get("offerCount")
    if not isinstance(offer_count, int) or offer_count < 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid offerCount.",
        )

    metafield_namespace = payload.get("metafieldNamespace")
    if not isinstance(metafield_namespace, str) or not metafield_namespace.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid metafieldNamespace.",
        )

    metafield_key = payload.get("metafieldKey")
    if not isinstance(metafield_key, str) or not metafield_key.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid metafieldKey.",
        )

    raw_variants = payload.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid variants for synced product.",
        )

    response_variants: list[dict[str, Any]] = []
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid synced variant object.",
            )

        variant_gid = raw_variant.get("variantGid")
        title = raw_variant.get("title")
        price_cents = raw_variant.get("priceCents")
        currency = raw_variant.get("currency")
        compare_at_price_cents = raw_variant.get("compareAtPriceCents")
        sku = raw_variant.get("sku")
        barcode = raw_variant.get("barcode")
        taxable = raw_variant.get("taxable")
        requires_shipping = raw_variant.get("requiresShipping")
        inventory_policy = raw_variant.get("inventoryPolicy")
        inventory_management = raw_variant.get("inventoryManagement")
        inventory_quantity = raw_variant.get("inventoryQuantity")
        option_values = raw_variant.get("optionValues")

        if not isinstance(variant_gid, str) or not variant_gid.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variantGid in synced payload.",
            )
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant title in synced payload.",
            )
        if not isinstance(price_cents, int) or price_cents < 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant priceCents in synced payload.",
            )
        if not isinstance(currency, str) or not currency.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid variant currency in synced payload.",
            )
        if compare_at_price_cents is not None and (
            not isinstance(compare_at_price_cents, int) or compare_at_price_cents < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid compareAtPriceCents in synced payload.",
            )
        if sku is not None and not isinstance(sku, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid sku in synced payload.",
            )
        if barcode is not None and not isinstance(barcode, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid barcode in synced payload.",
            )
        if not isinstance(taxable, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid taxable in synced payload.",
            )
        if not isinstance(requires_shipping, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid requiresShipping in synced payload.",
            )
        if inventory_policy is not None and not isinstance(inventory_policy, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryPolicy in synced payload.",
            )
        if inventory_management is not None and not isinstance(inventory_management, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryManagement in synced payload.",
            )
        if inventory_quantity is not None and not isinstance(inventory_quantity, int):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid inventoryQuantity in synced payload.",
            )
        if not isinstance(option_values, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid optionValues in synced payload.",
            )

        cleaned_option_values: dict[str, str] = {}
        for raw_key, raw_value in option_values.items():
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Shopify checkout app returned invalid optionValues entry in synced payload.",
                )
            cleaned_option_values[raw_key] = raw_value

        response_variants.append(
            {
                "variantGid": variant_gid.strip(),
                "title": title.strip(),
                "priceCents": price_cents,
                "currency": _normalize_currency_code(currency),
                "compareAtPriceCents": compare_at_price_cents,
                "sku": sku.strip() if isinstance(sku, str) and sku.strip() else None,
                "barcode": barcode.strip() if isinstance(barcode, str) and barcode.strip() else None,
                "taxable": taxable,
                "requiresShipping": requires_shipping,
                "inventoryPolicy": inventory_policy.strip().lower() if isinstance(inventory_policy, str) and inventory_policy.strip() else None,
                "inventoryManagement": inventory_management.strip().lower() if isinstance(inventory_management, str) and inventory_management.strip() else None,
                "inventoryQuantity": inventory_quantity,
                "optionValues": cleaned_option_values,
            }
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "productGid": response_product_gid.strip(),
        "title": response_title.strip(),
        "handle": response_handle.strip(),
        "status": response_status.strip(),
        "createdVariantCount": created_count,
        "updatedVariantCount": updated_count,
        "deletedVariantCount": deleted_count,
        "offerCount": offer_count,
        "metafieldNamespace": metafield_namespace.strip(),
        "metafieldKey": metafield_key.strip(),
        "variants": response_variants,
    }


def upsert_client_shopify_policy_pages(
    *,
    client_id: str,
    pages: list[dict[str, Any]],
    shop_domain: str | None = None,
) -> dict[str, Any]:
    if not pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pages must contain at least one policy page.",
        )

    cleaned_pages: list[dict[str, str]] = []
    seen_page_keys: set[str] = set()
    for raw_page in pages:
        if not isinstance(raw_page, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each page must be an object.",
            )

        raw_page_key = raw_page.get("pageKey")
        if not isinstance(raw_page_key, str) or not raw_page_key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each page requires a non-empty pageKey.",
            )
        page_key = raw_page_key.strip()
        if page_key in seen_page_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate pageKey provided: {page_key}",
            )
        seen_page_keys.add(page_key)

        raw_title = raw_page.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Policy page '{page_key}' requires a non-empty title.",
            )
        title = raw_title.strip()

        raw_handle = raw_page.get("handle")
        if not isinstance(raw_handle, str) or not raw_handle.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Policy page '{page_key}' requires a non-empty handle.",
            )
        handle = raw_handle.strip().lower()

        raw_body_html = raw_page.get("bodyHtml")
        if not isinstance(raw_body_html, str) or not raw_body_html.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Policy page '{page_key}' requires non-empty bodyHtml.",
            )
        body_html = raw_body_html.strip()

        cleaned_pages.append(
            {
                "pageKey": page_key,
                "title": title,
                "handle": handle,
                "bodyHtml": body_html,
            }
        )

    request_payload: dict[str, Any] = {"pages": cleaned_pages}
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/policies/pages/upsert",
        json_body=request_payload,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid policy-page sync payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for policy-page sync.",
        )

    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid pages list for policy-page sync.",
        )

    response_pages: list[dict[str, str]] = []
    for raw_page in raw_pages:
        if not isinstance(raw_page, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy-page object.",
            )
        page_key = raw_page.get("pageKey")
        page_id = raw_page.get("pageId")
        title = raw_page.get("title")
        handle = raw_page.get("handle")
        url = raw_page.get("url")
        operation = raw_page.get("operation")

        if not isinstance(page_key, str) or not page_key.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy pageKey.",
            )
        if not isinstance(page_id, str) or not page_id.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy pageId.",
            )
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy page title.",
            )
        if not isinstance(handle, str) or not handle.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy page handle.",
            )
        if not isinstance(url, str) or not url.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy page URL.",
            )
        if operation not in {"created", "updated"}:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid policy page operation.",
            )

        response_pages.append(
            {
                "pageKey": page_key.strip(),
                "pageId": page_id.strip(),
                "title": title.strip(),
                "handle": handle.strip(),
                "url": url.strip(),
                "operation": operation,
            }
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "pages": response_pages,
    }


def sync_client_shopify_theme_brand(
    *,
    client_id: str,
    workspace_name: str,
    brand_name: str,
    logo_url: str,
    css_vars: dict[str, str],
    font_urls: list[str] | None = None,
    data_theme: str | None = None,
    component_image_urls: dict[str, str] | None = None,
    component_text_values: dict[str, str] | None = None,
    auto_component_image_urls: list[str] | None = None,
    theme_id: str | None = None,
    theme_name: str | None = None,
    shop_domain: str | None = None,
    export_files: bool = False,
) -> dict[str, Any]:
    cleaned_workspace_name = workspace_name.strip()
    if not cleaned_workspace_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspaceName is required.",
        )

    cleaned_brand_name = brand_name.strip()
    if not cleaned_brand_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="brandName is required.",
        )

    cleaned_logo_url = logo_url.strip()
    if not cleaned_logo_url or not (
        cleaned_logo_url.startswith("https://")
        or cleaned_logo_url.startswith("http://")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="logoUrl must be an absolute http(s) URL.",
        )
    if any(char in cleaned_logo_url for char in ('"', "'", "<", ">", "\n", "\r")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="logoUrl contains unsupported characters.",
        )

    if not isinstance(css_vars, dict) or not css_vars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cssVars must be a non-empty object.",
        )

    normalized_css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars.items():
        if not isinstance(raw_key, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars keys must be strings.",
            )
        key = raw_key.strip()
        if not re.fullmatch(r"--[A-Za-z0-9_-]+", key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars keys must be valid CSS custom properties (for example: --color-brand).",
            )
        if key in normalized_css_vars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate cssVars key after normalization: {key}",
            )

        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars values must be strings.",
            )
        value = raw_value.strip()
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"cssVars[{key}] cannot be empty.",
            )
        if any(char in value for char in ("\n", "\r", "{", "}", ";")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"cssVars[{key}] contains unsupported characters.",
            )
        normalized_css_vars[key] = value

    normalized_font_urls: list[str] = []
    seen_font_urls: set[str] = set()
    for raw_url in font_urls or []:
        if not isinstance(raw_url, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fontUrls entries must be strings.",
            )
        url = raw_url.strip()
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="fontUrls entries cannot be empty.",
            )
        if not (url.startswith("https://") or url.startswith("http://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"fontUrls entry must be an absolute http(s) URL: {url}",
            )
        if any(char in url for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"fontUrls entry contains unsupported characters: {url}",
            )
        if url in seen_font_urls:
            continue
        seen_font_urls.add(url)
        normalized_font_urls.append(url)

    normalized_component_image_urls: dict[str, str] = {}
    for raw_setting_path, raw_url in (component_image_urls or {}).items():
        if not isinstance(raw_setting_path, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="componentImageUrls keys must be strings.",
            )
        setting_path = raw_setting_path.strip()
        if not setting_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="componentImageUrls keys must be non-empty setting paths.",
            )
        if not (
            setting_path.startswith("templates/")
            or setting_path.startswith("sections/")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "componentImageUrls keys must target template or section JSON files "
                    "(for example: templates/index.json.sections.hero.settings.image)."
                ),
            )
        if ".json." not in setting_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "componentImageUrls keys must include a JSON path suffix after filename "
                    "(for example: templates/index.json.sections.hero.settings.image)."
                ),
            )
        if any(char in setting_path for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentImageUrls path contains unsupported characters: {setting_path}",
            )
        if setting_path in normalized_component_image_urls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate componentImageUrls path after normalization: {setting_path}",
            )

        if not isinstance(raw_url, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentImageUrls[{setting_path}] must be a string URL.",
            )
        image_url = raw_url.strip()
        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentImageUrls[{setting_path}] cannot be empty.",
            )
        if not (
            image_url.startswith("https://")
            or image_url.startswith("http://")
            or image_url.startswith("shopify://")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"componentImageUrls[{setting_path}] must be an absolute http(s) URL "
                    "or a shopify:// URL."
                ),
            )
        if any(char in image_url for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentImageUrls[{setting_path}] contains unsupported characters.",
            )
        if any(char.isspace() for char in image_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentImageUrls[{setting_path}] must not include whitespace characters.",
            )
        normalized_component_image_urls[setting_path] = image_url

    normalized_component_text_values: dict[str, str] = {}
    for raw_setting_path, raw_value in (component_text_values or {}).items():
        if not isinstance(raw_setting_path, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="componentTextValues keys must be strings.",
            )
        setting_path = raw_setting_path.strip()
        if not setting_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="componentTextValues keys must be non-empty setting paths.",
            )
        if not (
            setting_path.startswith("templates/")
            or setting_path.startswith("sections/")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "componentTextValues keys must target template or section JSON files "
                    "(for example: templates/index.json.sections.hero.settings.heading)."
                ),
            )
        if ".json." not in setting_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "componentTextValues keys must include a JSON path suffix after filename "
                    "(for example: templates/index.json.sections.hero.settings.heading)."
                ),
            )
        if any(char in setting_path for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentTextValues path contains unsupported characters: {setting_path}",
            )
        if setting_path in normalized_component_text_values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate componentTextValues path after normalization: {setting_path}",
            )

        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentTextValues[{setting_path}] must be a string value.",
            )
        text_value = raw_value.strip()
        if not text_value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentTextValues[{setting_path}] cannot be empty.",
            )
        if any(char in text_value for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"componentTextValues[{setting_path}] contains unsupported characters.",
            )
        normalized_component_text_values[setting_path] = text_value

    normalized_auto_component_image_urls: list[str] = []
    seen_auto_component_image_urls: set[str] = set()
    for raw_url in auto_component_image_urls or []:
        if not isinstance(raw_url, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="autoComponentImageUrls entries must be strings.",
            )
        image_url = raw_url.strip()
        if not image_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="autoComponentImageUrls entries cannot be empty.",
            )
        if not (
            image_url.startswith("https://")
            or image_url.startswith("http://")
            or image_url.startswith("shopify://")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "autoComponentImageUrls entries must be absolute http(s) URLs "
                    "or shopify:// URLs."
                ),
            )
        if any(char in image_url for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"autoComponentImageUrls entry contains unsupported characters: {image_url}",
            )
        if any(char.isspace() for char in image_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"autoComponentImageUrls entry must not include whitespace characters: {image_url}",
            )
        if image_url in seen_auto_component_image_urls:
            continue
        seen_auto_component_image_urls.add(image_url)
        normalized_auto_component_image_urls.append(image_url)

    cleaned_data_theme: str | None = None
    if data_theme is not None:
        cleaned_data_theme = data_theme.strip()
        if not cleaned_data_theme:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dataTheme cannot be empty when provided.",
            )
        if any(char in cleaned_data_theme for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dataTheme contains unsupported characters.",
            )

    cleaned_theme_id: str | None = None
    if theme_id is not None:
        cleaned_theme_id = theme_id.strip()
        if not cleaned_theme_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId cannot be empty when provided.",
            )
        if not cleaned_theme_id.startswith(_SHOPIFY_THEME_GID_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId must be a Shopify OnlineStoreTheme GID.",
            )
    cleaned_theme_name: str | None = None
    if theme_name is not None:
        cleaned_theme_name = theme_name.strip()
        if not cleaned_theme_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeName cannot be empty when provided.",
            )
    if bool(cleaned_theme_id) == bool(cleaned_theme_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of themeId or themeName is required.",
        )

    base_request_payload: dict[str, Any] = {
        "workspaceName": cleaned_workspace_name,
        "brandName": cleaned_brand_name,
        "logoUrl": cleaned_logo_url,
        "cssVars": normalized_css_vars,
        "fontUrls": normalized_font_urls,
    }
    if cleaned_data_theme is not None:
        base_request_payload["dataTheme"] = cleaned_data_theme
    if cleaned_theme_id is not None:
        base_request_payload["themeId"] = cleaned_theme_id
    if cleaned_theme_name is not None:
        base_request_payload["themeName"] = cleaned_theme_name
    if shop_domain is not None:
        base_request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        base_request_payload["clientId"] = client_id

    configured_image_batch_size = settings.SHOPIFY_THEME_COMPONENT_IMAGE_BATCH_SIZE
    if configured_image_batch_size <= 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SHOPIFY_THEME_COMPONENT_IMAGE_BATCH_SIZE must be a positive integer.",
        )

    component_image_items = list(normalized_component_image_urls.items())
    image_batch_size = configured_image_batch_size
    if export_files and component_image_items:
        image_batch_size = max(image_batch_size, len(component_image_items))
    resolved_theme_operation_timeout = (
        settings.SHOPIFY_THEME_EXPORT_TIMEOUT_SECONDS
        if export_files
        else settings.SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS
    )
    if not isinstance(resolved_theme_operation_timeout, (int, float)) or (
        resolved_theme_operation_timeout <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SHOPIFY_THEME_EXPORT_TIMEOUT_SECONDS must be a positive number."
                if export_files
                else "SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS must be a positive number."
            ),
        )

    def _sync_theme_brand_request(*, request_payload: dict[str, Any]) -> dict[str, Any]:
        payload = _bridge_request(
            method="POST",
            path="/v1/themes/brand/export" if export_files else "/v1/themes/brand/sync",
            json_body=request_payload,
            timeout_seconds=float(resolved_theme_operation_timeout),
        )
        if export_files:
            return _parse_theme_brand_export_response_payload(payload=payload)
        return _parse_theme_brand_sync_response_payload(payload=payload)

    if len(component_image_items) > image_batch_size:
        final_response: dict[str, Any] | None = None
        for chunk_start in range(
            0, len(component_image_items), image_batch_size
        ):
            chunk_items = component_image_items[
                chunk_start : chunk_start + image_batch_size
            ]
            chunk_request_payload = dict(base_request_payload)
            chunk_request_payload["componentImageUrls"] = dict(chunk_items)
            if chunk_start == 0 and normalized_component_text_values:
                chunk_request_payload["componentTextValues"] = (
                    normalized_component_text_values
                )
            if chunk_start == 0 and normalized_auto_component_image_urls:
                chunk_request_payload["autoComponentImageUrls"] = (
                    normalized_auto_component_image_urls
                )
            final_response = _sync_theme_brand_request(
                request_payload=chunk_request_payload
            )
        if final_response is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to execute chunked Shopify theme sync requests.",
            )
        return final_response

    request_payload = dict(base_request_payload)
    if normalized_component_image_urls:
        request_payload["componentImageUrls"] = normalized_component_image_urls
    if normalized_component_text_values:
        request_payload["componentTextValues"] = normalized_component_text_values
    if normalized_auto_component_image_urls:
        request_payload["autoComponentImageUrls"] = normalized_auto_component_image_urls
    return _sync_theme_brand_request(request_payload=request_payload)


def export_client_shopify_theme_brand(
    *,
    client_id: str,
    workspace_name: str,
    brand_name: str,
    logo_url: str,
    css_vars: dict[str, str],
    font_urls: list[str] | None = None,
    data_theme: str | None = None,
    component_image_urls: dict[str, str] | None = None,
    component_text_values: dict[str, str] | None = None,
    auto_component_image_urls: list[str] | None = None,
    theme_id: str | None = None,
    theme_name: str | None = None,
    shop_domain: str | None = None,
) -> dict[str, Any]:
    return sync_client_shopify_theme_brand(
        client_id=client_id,
        workspace_name=workspace_name,
        brand_name=brand_name,
        logo_url=logo_url,
        css_vars=css_vars,
        font_urls=font_urls,
        data_theme=data_theme,
        component_image_urls=component_image_urls,
        component_text_values=component_text_values,
        auto_component_image_urls=auto_component_image_urls,
        theme_id=theme_id,
        theme_name=theme_name,
        shop_domain=shop_domain,
        export_files=True,
    )


def resolve_client_shopify_image_urls_to_files(
    *,
    client_id: str,
    image_urls_by_key: dict[str, str],
    shop_domain: str | None = None,
) -> dict[str, Any]:
    if not isinstance(image_urls_by_key, dict) or not image_urls_by_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="imageUrls must be a non-empty object.",
        )

    normalized_image_urls: dict[str, str] = {}
    for raw_key, raw_value in image_urls_by_key.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="imageUrls keys must be non-empty strings.",
            )
        key = raw_key.strip()
        if key in normalized_image_urls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate imageUrls key after normalization: {key}",
            )
        if any(char in key for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"imageUrls key contains unsupported characters: {key}",
            )

        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"imageUrls[{key}] must be a string URL.",
            )
        value = raw_value.strip()
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"imageUrls[{key}] cannot be empty.",
            )
        if any(char.isspace() for char in value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"imageUrls[{key}] must not include whitespace characters.",
            )
        if any(char in value for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"imageUrls[{key}] contains unsupported characters.",
            )
        if not (
            value.startswith("https://")
            or value.startswith("http://")
            or value.startswith("shopify://")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"imageUrls[{key}] must be an absolute http(s) URL "
                    "or a shopify:// URL."
                ),
            )
        normalized_image_urls[key] = value

    request_payload: dict[str, Any] = {"imageUrls": normalized_image_urls}
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/files/images/resolve",
        json_body=request_payload,
        timeout_seconds=settings.SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid image URL resolve payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for image URL resolve.",
        )
    raw_resolved_urls = payload.get("resolvedImageUrls")
    if not isinstance(raw_resolved_urls, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid resolvedImageUrls payload.",
        )

    resolved_image_urls: dict[str, str] = {}
    for key, value in raw_resolved_urls.items():
        if not isinstance(key, str) or key not in normalized_image_urls:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned unexpected resolvedImageUrls keys.",
            )
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify checkout app returned invalid resolved image URL "
                    f"for key={key}."
                ),
            )
        resolved_value = value.strip()
        if not resolved_value.startswith("shopify://"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify checkout app did not return a Shopify file reference "
                    f"for key={key}."
                ),
            )
        resolved_image_urls[key] = resolved_value

    expected_keys = set(normalized_image_urls.keys())
    actual_keys = set(resolved_image_urls.keys())
    if expected_keys != actual_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Shopify checkout app returned an incomplete resolvedImageUrls payload. "
                f"expected={sorted(expected_keys)} got={sorted(actual_keys)}"
            ),
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "resolvedImageUrls": resolved_image_urls,
    }


def _parse_theme_brand_sync_response_payload(*, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid theme brand sync payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for theme brand sync.",
        )
    response_theme_id = payload.get("themeId")
    if not isinstance(response_theme_id, str) or not response_theme_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeId for theme brand sync.",
        )
    response_theme_name = payload.get("themeName")
    if not isinstance(response_theme_name, str) or not response_theme_name.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeName for theme brand sync.",
        )
    response_theme_role = payload.get("themeRole")
    if not isinstance(response_theme_role, str) or not response_theme_role.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeRole for theme brand sync.",
        )
    response_layout_filename = payload.get("layoutFilename")
    if (
        not isinstance(response_layout_filename, str)
        or not response_layout_filename.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid layoutFilename for theme brand sync.",
        )
    response_css_filename = payload.get("cssFilename")
    if not isinstance(response_css_filename, str) or not response_css_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid cssFilename for theme brand sync.",
        )
    response_settings_filename = payload.get("settingsFilename")
    normalized_settings_filename: str | None
    if response_settings_filename is None:
        normalized_settings_filename = None
    else:
        if (
            not isinstance(response_settings_filename, str)
            or not response_settings_filename.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid settingsFilename for theme brand sync.",
            )
        normalized_settings_filename = response_settings_filename.strip()

    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid coverage for theme brand sync.",
        )
    required_source_vars = coverage.get("requiredSourceVars")
    required_theme_vars = coverage.get("requiredThemeVars")
    missing_source_vars = coverage.get("missingSourceVars")
    missing_theme_vars = coverage.get("missingThemeVars")
    for list_name, value in (
        ("requiredSourceVars", required_source_vars),
        ("requiredThemeVars", required_theme_vars),
        ("missingSourceVars", missing_source_vars),
        ("missingThemeVars", missing_theme_vars),
    ):
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shopify checkout app returned invalid coverage.{list_name} for theme brand sync.",
            )

    settings_sync = payload.get("settingsSync")
    if not isinstance(settings_sync, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid settingsSync for theme brand sync.",
        )
    settings_sync_filename = settings_sync.get("settingsFilename")
    if settings_sync_filename is not None and (
        not isinstance(settings_sync_filename, str)
        or not settings_sync_filename.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid settingsSync.settingsFilename for theme brand sync.",
        )
    expected_paths = settings_sync.get("expectedPaths")
    updated_paths = settings_sync.get("updatedPaths")
    missing_paths = settings_sync.get("missingPaths")
    required_missing_paths = settings_sync.get("requiredMissingPaths")
    semantic_updated_paths = settings_sync.get("semanticUpdatedPaths")
    unmapped_color_paths = settings_sync.get("unmappedColorPaths")
    semantic_typography_updated_paths = settings_sync.get(
        "semanticTypographyUpdatedPaths"
    )
    unmapped_typography_paths = settings_sync.get("unmappedTypographyPaths")
    for list_name, value in (
        ("expectedPaths", expected_paths),
        ("updatedPaths", updated_paths),
        ("missingPaths", missing_paths),
        ("requiredMissingPaths", required_missing_paths),
        ("semanticUpdatedPaths", semantic_updated_paths),
        ("unmappedColorPaths", unmapped_color_paths),
        ("semanticTypographyUpdatedPaths", semantic_typography_updated_paths),
        ("unmappedTypographyPaths", unmapped_typography_paths),
    ):
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shopify checkout app returned invalid settingsSync.{list_name} for theme brand sync.",
            )

    response_job_id = payload.get("jobId")
    if response_job_id is None:
        normalized_job_id = None
    else:
        if not isinstance(response_job_id, str) or not response_job_id.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid jobId for theme brand sync.",
            )
        normalized_job_id = response_job_id.strip()

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "themeId": response_theme_id.strip(),
        "themeName": response_theme_name.strip(),
        "themeRole": response_theme_role.strip(),
        "layoutFilename": response_layout_filename.strip(),
        "cssFilename": response_css_filename.strip(),
        "settingsFilename": normalized_settings_filename,
        "jobId": normalized_job_id,
        "coverage": {
            "requiredSourceVars": required_source_vars,
            "requiredThemeVars": required_theme_vars,
            "missingSourceVars": missing_source_vars,
            "missingThemeVars": missing_theme_vars,
        },
        "settingsSync": {
            "settingsFilename": (
                settings_sync_filename.strip()
                if isinstance(settings_sync_filename, str)
                else None
            ),
            "expectedPaths": expected_paths,
            "updatedPaths": updated_paths,
            "missingPaths": missing_paths,
            "requiredMissingPaths": required_missing_paths,
            "semanticUpdatedPaths": semantic_updated_paths,
            "unmappedColorPaths": unmapped_color_paths,
            "semanticTypographyUpdatedPaths": semantic_typography_updated_paths,
            "unmappedTypographyPaths": unmapped_typography_paths,
        },
    }


def _parse_theme_brand_export_response_payload(*, payload: Any) -> dict[str, Any]:
    parsed_sync_payload = _parse_theme_brand_sync_response_payload(payload=payload)

    files_payload = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files_payload, list) or not files_payload:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid files for theme brand export.",
        )

    parsed_files: list[dict[str, str]] = []
    seen_filenames: set[str] = set()
    for item in files_payload:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid file entry for theme brand export.",
            )
        filename = item.get("filename")
        content = item.get("content")
        content_base64 = item.get("contentBase64")
        if not isinstance(filename, str) or not filename.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid filename for theme brand export.",
            )
        has_text_content = isinstance(content, str)
        has_base64_content = isinstance(content_base64, str)
        if has_text_content == has_base64_content:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify checkout app returned invalid file content for theme brand export. "
                    "Expected exactly one of content or contentBase64."
                ),
            )
        cleaned_filename = filename.strip()
        if cleaned_filename in seen_filenames:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shopify checkout app returned duplicate export filename: {cleaned_filename}",
            )
        seen_filenames.add(cleaned_filename)
        if has_text_content:
            parsed_files.append({"filename": cleaned_filename, "content": content})
            continue

        cleaned_content_base64 = content_base64.strip()
        if not cleaned_content_base64:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned empty contentBase64 for theme brand export.",
            )
        try:
            base64.b64decode(cleaned_content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Shopify checkout app returned malformed contentBase64 for theme brand export."
                ),
            ) from exc
        parsed_files.append(
            {
                "filename": cleaned_filename,
                "contentBase64": cleaned_content_base64,
            }
        )

    parsed_sync_payload["files"] = parsed_files
    return parsed_sync_payload


def list_client_shopify_theme_template_slots(
    *,
    client_id: str,
    theme_id: str | None = None,
    theme_name: str | None = None,
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_theme_id: str | None = None
    if theme_id is not None:
        cleaned_theme_id = theme_id.strip()
        if not cleaned_theme_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId cannot be empty when provided.",
            )
        if not cleaned_theme_id.startswith(_SHOPIFY_THEME_GID_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId must be a Shopify OnlineStoreTheme GID.",
            )
    cleaned_theme_name: str | None = None
    if theme_name is not None:
        cleaned_theme_name = theme_name.strip()
        if not cleaned_theme_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeName cannot be empty when provided.",
            )
    if cleaned_theme_id is not None and cleaned_theme_name is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at most one of themeId or themeName.",
        )

    request_payload: dict[str, Any] = {}
    if cleaned_theme_id is not None:
        request_payload["themeId"] = cleaned_theme_id
    if cleaned_theme_name is not None:
        request_payload["themeName"] = cleaned_theme_name
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/themes/brand/template-slots",
        json_body=request_payload,
        timeout_seconds=settings.SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid theme template slots payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for theme template slots.",
        )
    response_theme_id = payload.get("themeId")
    if not isinstance(response_theme_id, str) or not response_theme_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeId for theme template slots.",
        )
    response_theme_name = payload.get("themeName")
    if not isinstance(response_theme_name, str) or not response_theme_name.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeName for theme template slots.",
        )
    response_theme_role = payload.get("themeRole")
    if not isinstance(response_theme_role, str) or not response_theme_role.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeRole for theme template slots.",
        )

    raw_image_slots = payload.get("imageSlots")
    if not isinstance(raw_image_slots, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid imageSlots for theme template slots.",
        )
    image_slots: list[dict[str, Any]] = []
    for item in raw_image_slots:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid imageSlots entry for theme template slots.",
            )
        path = item.get("path")
        key = item.get("key")
        role = item.get("role")
        recommended_aspect = item.get("recommendedAspect")
        current_value = item.get("currentValue")
        if not isinstance(path, str) or not path.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid image slot path.",
            )
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid image slot key.",
            )
        if not isinstance(role, str) or not role.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid image slot role.",
            )
        if not isinstance(recommended_aspect, str) or recommended_aspect not in {
            "landscape",
            "portrait",
            "square",
            "any",
        }:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid image slot recommendedAspect.",
            )
        if current_value is not None and not isinstance(current_value, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid image slot currentValue.",
            )
        image_slots.append(
            {
                "path": path.strip(),
                "key": key.strip(),
                "currentValue": (
                    current_value.strip() if isinstance(current_value, str) else None
                ),
                "role": role.strip(),
                "recommendedAspect": recommended_aspect,
            }
        )

    raw_text_slots = payload.get("textSlots")
    if not isinstance(raw_text_slots, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid textSlots for theme template slots.",
        )
    text_slots: list[dict[str, Any]] = []
    for item in raw_text_slots:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid textSlots entry for theme template slots.",
            )
        path = item.get("path")
        key = item.get("key")
        role = item.get("role")
        max_length = item.get("maxLength")
        current_value = item.get("currentValue")
        if not isinstance(path, str) or not path.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid text slot path.",
            )
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid text slot key.",
            )
        if not isinstance(role, str) or not role.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid text slot role.",
            )
        if not isinstance(max_length, int) or max_length <= 0:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid text slot maxLength.",
            )
        if current_value is not None and not isinstance(current_value, str):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Shopify checkout app returned invalid text slot currentValue.",
            )
        text_slots.append(
            {
                "path": path.strip(),
                "key": key.strip(),
                "currentValue": (
                    current_value.strip() if isinstance(current_value, str) else None
                ),
                "role": role.strip(),
                "maxLength": max_length,
            }
        )

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "themeId": response_theme_id.strip(),
        "themeName": response_theme_name.strip(),
        "themeRole": response_theme_role.strip(),
        "imageSlots": image_slots,
        "textSlots": text_slots,
    }


def audit_client_shopify_theme_brand(
    *,
    client_id: str,
    workspace_name: str,
    css_vars: dict[str, str],
    data_theme: str | None = None,
    theme_id: str | None = None,
    theme_name: str | None = None,
    shop_domain: str | None = None,
) -> dict[str, Any]:
    cleaned_workspace_name = workspace_name.strip()
    if not cleaned_workspace_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workspaceName is required.",
        )

    if not isinstance(css_vars, dict) or not css_vars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cssVars must be a non-empty object.",
        )

    normalized_css_vars: dict[str, str] = {}
    for raw_key, raw_value in css_vars.items():
        if not isinstance(raw_key, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars keys must be strings.",
            )
        key = raw_key.strip()
        if not re.fullmatch(r"--[A-Za-z0-9_-]+", key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars keys must be valid CSS custom properties (for example: --color-brand).",
            )
        if key in normalized_css_vars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate cssVars key after normalization: {key}",
            )
        if not isinstance(raw_value, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cssVars values must be strings.",
            )
        value = raw_value.strip()
        if not value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"cssVars[{key}] cannot be empty.",
            )
        if any(char in value for char in ("\n", "\r", "{", "}", ";")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"cssVars[{key}] contains unsupported characters.",
            )
        normalized_css_vars[key] = value

    cleaned_data_theme: str | None = None
    if data_theme is not None:
        cleaned_data_theme = data_theme.strip()
        if not cleaned_data_theme:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dataTheme cannot be empty when provided.",
            )
        if any(char in cleaned_data_theme for char in ('"', "'", "<", ">", "\n", "\r")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dataTheme contains unsupported characters.",
            )

    cleaned_theme_id: str | None = None
    if theme_id is not None:
        cleaned_theme_id = theme_id.strip()
        if not cleaned_theme_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId cannot be empty when provided.",
            )
        if not cleaned_theme_id.startswith(_SHOPIFY_THEME_GID_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeId must be a Shopify OnlineStoreTheme GID.",
            )
    cleaned_theme_name: str | None = None
    if theme_name is not None:
        cleaned_theme_name = theme_name.strip()
        if not cleaned_theme_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="themeName cannot be empty when provided.",
            )
    if bool(cleaned_theme_id) == bool(cleaned_theme_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly one of themeId or themeName is required.",
        )

    request_payload: dict[str, Any] = {
        "workspaceName": cleaned_workspace_name,
        "cssVars": normalized_css_vars,
    }
    if cleaned_data_theme is not None:
        request_payload["dataTheme"] = cleaned_data_theme
    if cleaned_theme_id is not None:
        request_payload["themeId"] = cleaned_theme_id
    if cleaned_theme_name is not None:
        request_payload["themeName"] = cleaned_theme_name
    if shop_domain is not None:
        request_payload["shopDomain"] = normalize_shop_domain(shop_domain)
    else:
        request_payload["clientId"] = client_id

    payload = _bridge_request(
        method="POST",
        path="/v1/themes/brand/audit",
        json_body=request_payload,
        timeout_seconds=settings.SHOPIFY_THEME_OPERATIONS_TIMEOUT_SECONDS,
    )
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid theme brand audit payload.",
        )

    response_shop_domain = payload.get("shopDomain")
    if not isinstance(response_shop_domain, str) or not response_shop_domain.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid shopDomain for theme brand audit.",
        )
    response_theme_id = payload.get("themeId")
    if not isinstance(response_theme_id, str) or not response_theme_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeId for theme brand audit.",
        )
    response_theme_name = payload.get("themeName")
    if not isinstance(response_theme_name, str) or not response_theme_name.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeName for theme brand audit.",
        )
    response_theme_role = payload.get("themeRole")
    if not isinstance(response_theme_role, str) or not response_theme_role.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid themeRole for theme brand audit.",
        )
    response_layout_filename = payload.get("layoutFilename")
    if (
        not isinstance(response_layout_filename, str)
        or not response_layout_filename.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid layoutFilename for theme brand audit.",
        )
    response_css_filename = payload.get("cssFilename")
    if not isinstance(response_css_filename, str) or not response_css_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid cssFilename for theme brand audit.",
        )
    response_settings_filename = payload.get("settingsFilename")
    if response_settings_filename is not None and (
        not isinstance(response_settings_filename, str)
        or not response_settings_filename.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid settingsFilename for theme brand audit.",
        )

    def _require_bool(name: str) -> bool:
        value = payload.get(name)
        if not isinstance(value, bool):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shopify checkout app returned invalid {name} for theme brand audit.",
            )
        return value

    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid coverage for theme brand audit.",
        )
    settings_audit = payload.get("settingsAudit")
    if not isinstance(settings_audit, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid settingsAudit for theme brand audit.",
        )
    is_ready = payload.get("isReady")
    if not isinstance(is_ready, bool):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid isReady for theme brand audit.",
        )

    def _require_string_list(
        obj: dict[str, Any], key: str, container_name: str
    ) -> list[str]:
        value = obj.get(key)
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Shopify checkout app returned invalid {container_name}.{key} for theme brand audit.",
            )
        return value

    parsed_coverage = {
        "requiredSourceVars": _require_string_list(
            coverage, "requiredSourceVars", "coverage"
        ),
        "requiredThemeVars": _require_string_list(
            coverage, "requiredThemeVars", "coverage"
        ),
        "missingSourceVars": _require_string_list(
            coverage, "missingSourceVars", "coverage"
        ),
        "missingThemeVars": _require_string_list(
            coverage, "missingThemeVars", "coverage"
        ),
    }
    settings_audit_filename = settings_audit.get("settingsFilename")
    if settings_audit_filename is not None and (
        not isinstance(settings_audit_filename, str)
        or not settings_audit_filename.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid settingsAudit.settingsFilename for theme brand audit.",
        )
    parsed_settings_audit = {
        "settingsFilename": (
            settings_audit_filename.strip()
            if isinstance(settings_audit_filename, str)
            else None
        ),
        "expectedPaths": _require_string_list(
            settings_audit, "expectedPaths", "settingsAudit"
        ),
        "syncedPaths": _require_string_list(
            settings_audit, "syncedPaths", "settingsAudit"
        ),
        "mismatchedPaths": _require_string_list(
            settings_audit, "mismatchedPaths", "settingsAudit"
        ),
        "missingPaths": _require_string_list(
            settings_audit, "missingPaths", "settingsAudit"
        ),
        "requiredMissingPaths": _require_string_list(
            settings_audit, "requiredMissingPaths", "settingsAudit"
        ),
        "requiredMismatchedPaths": _require_string_list(
            settings_audit, "requiredMismatchedPaths", "settingsAudit"
        ),
        "semanticSyncedPaths": _require_string_list(
            settings_audit, "semanticSyncedPaths", "settingsAudit"
        ),
        "semanticMismatchedPaths": _require_string_list(
            settings_audit, "semanticMismatchedPaths", "settingsAudit"
        ),
        "unmappedColorPaths": _require_string_list(
            settings_audit, "unmappedColorPaths", "settingsAudit"
        ),
        "semanticTypographySyncedPaths": _require_string_list(
            settings_audit,
            "semanticTypographySyncedPaths",
            "settingsAudit",
        ),
        "semanticTypographyMismatchedPaths": _require_string_list(
            settings_audit,
            "semanticTypographyMismatchedPaths",
            "settingsAudit",
        ),
        "unmappedTypographyPaths": _require_string_list(
            settings_audit, "unmappedTypographyPaths", "settingsAudit"
        ),
    }

    return {
        "shopDomain": response_shop_domain.strip().lower(),
        "themeId": response_theme_id.strip(),
        "themeName": response_theme_name.strip(),
        "themeRole": response_theme_role.strip(),
        "layoutFilename": response_layout_filename.strip(),
        "cssFilename": response_css_filename.strip(),
        "settingsFilename": (
            response_settings_filename.strip()
            if isinstance(response_settings_filename, str)
            else None
        ),
        "hasManagedMarkerBlock": _require_bool("hasManagedMarkerBlock"),
        "layoutIncludesManagedCssAsset": _require_bool("layoutIncludesManagedCssAsset"),
        "managedCssAssetExists": _require_bool("managedCssAssetExists"),
        "coverage": parsed_coverage,
        "settingsAudit": parsed_settings_audit,
        "isReady": is_ready,
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


def build_client_shopify_install_urls(*, client_id: str, shop_domain: str) -> dict[str, str]:
    install_url = build_client_shopify_install_url(
        client_id=client_id,
        shop_domain=shop_domain,
    )
    return {
        "installUrl": install_url,
    }


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
            if installation.shop_domain == normalized_shop
            and installation.uninstalled_at is None
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


def auto_provision_client_shopify_storefront_token(
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
            if installation.shop_domain == normalized_shop
            and installation.uninstalled_at is None
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
        method="POST",
        path=f"/admin/installations/{normalized_shop}/storefront-token/auto",
        json_body={"clientId": client_id},
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
            if installation.shop_domain == normalized_shop
            and installation.uninstalled_at is None
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
