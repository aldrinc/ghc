from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.config import settings

_PRODUCT_GID_PREFIX = "gid://shopify/Product/"


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


def verify_shopify_product_exists(*, client_id: str, product_gid: str) -> None:
    cleaned_gid = product_gid.strip()
    if not cleaned_gid.startswith(_PRODUCT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify product GID is invalid for this product.",
        )

    base_url, internal_token = _require_checkout_service_config()
    headers = {
        "Authorization": f"Bearer {internal_token}",
        "Content-Type": "application/json",
    }
    payload = {"clientId": client_id, "productGid": cleaned_gid}
    timeout_seconds = settings.SHOPIFY_CHECKOUT_REQUEST_TIMEOUT_SECONDS
    request_timeout = httpx.Timeout(
        timeout=timeout_seconds,
        connect=min(timeout_seconds, 10.0),
    )

    try:
        with httpx.Client(timeout=request_timeout) as client:
            response = client.post(f"{base_url}/v1/catalog/products/verify", json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Shopify checkout app request timed out "
                f"after {timeout_seconds:.1f}s (POST /v1/catalog/products/verify)."
            ),
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify checkout app request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail: str
        try:
            body = response.json()
        except ValueError:
            detail = response.text.strip() or response.reason_phrase
        else:
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
            else:
                detail = str(body)
        status_code = response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=status_code,
            detail=f"Shopify checkout app error: {detail}",
        )
