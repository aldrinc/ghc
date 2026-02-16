from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from app.config import settings

_PRODUCT_GID_PREFIX = "gid://shopify/Product/"


def _require_checkout_service_config() -> tuple[str, str]:
    if not settings.SHOPIFY_CHECKOUT_APP_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shopify checkout app base URL is not configured.",
        )
    if not settings.SHOPIFY_CHECKOUT_APP_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shopify checkout app API token is not configured.",
        )
    return settings.SHOPIFY_CHECKOUT_APP_BASE_URL.rstrip("/"), settings.SHOPIFY_CHECKOUT_APP_API_TOKEN


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

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(f"{base_url}/v1/catalog/products/verify", json=payload, headers=headers)
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
