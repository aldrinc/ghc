from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings

_VARIANT_GID_PREFIX = "gid://shopify/ProductVariant/"


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


def _serialize_attribute(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


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


def create_shopify_checkout(
    *,
    client_id: str,
    variant_gid: str,
    quantity: int,
    metadata: dict[str, Any],
) -> dict[str, str]:
    if not variant_gid.startswith(_VARIANT_GID_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shopify variant GID is invalid for this price point.",
        )

    base_url, internal_token = _require_checkout_service_config()
    payload = {
        "clientId": client_id,
        "lines": [{"merchandiseId": variant_gid, "quantity": quantity}],
        "attributes": {
            key: _serialize_attribute(value)
            for key, value in metadata.items()
            if value is not None
        },
    }
    headers = {
        "Authorization": f"Bearer {internal_token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(f"{base_url}/v1/checkouts", json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify checkout app request failed: {exc}",
        ) from exc

    if response.status_code >= 400:
        error_detail = _error_detail_from_response(response)
        status_code = response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(
            status_code=status_code,
            detail=f"Shopify checkout app error: {error_detail}",
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned invalid JSON.",
        ) from exc

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app returned an invalid response payload.",
        )

    checkout_url = body.get("checkoutUrl")
    cart_id = body.get("cartId")
    if not isinstance(checkout_url, str) or not checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app response is missing checkoutUrl.",
        )
    if not isinstance(cart_id, str) or not cart_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shopify checkout app response is missing cartId.",
        )

    return {"checkoutUrl": checkout_url, "cartId": cart_id}
