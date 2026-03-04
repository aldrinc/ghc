from __future__ import annotations

import base64
import hashlib
import hmac
import re
from collections.abc import Sequence
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException, status
from jwt import InvalidTokenError

from app.config import settings

_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


def normalize_shop_domain(shop: str) -> str:
    normalized = shop.strip().lower()
    if not _SHOP_DOMAIN_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="shop must be a valid *.myshopify.com domain",
        )
    return normalized


def verify_oauth_hmac(query_items: Sequence[tuple[str, str]]) -> bool:
    supplied_hmac = None
    filtered: list[tuple[str, str]] = []
    for key, value in query_items:
        if key == "hmac":
            supplied_hmac = value
            continue
        if key == "signature":
            continue
        filtered.append((key, value))

    if not supplied_hmac:
        return False

    filtered.sort(key=lambda item: item[0])
    message = "&".join(f"{key}={value}" for key, value in filtered)
    digest = hmac.new(
        settings.SHOPIFY_APP_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, supplied_hmac)


def verify_webhook_hmac(*, body: bytes, supplied_hmac: str | None) -> bool:
    if not supplied_hmac:
        return False
    digest = hmac.new(
        settings.SHOPIFY_APP_API_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    encoded = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(encoded, supplied_hmac)


def require_internal_api_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authorization header",
        )
    token = authorization[7:].strip()
    if not hmac.compare_digest(token, settings.SHOPIFY_INTERNAL_API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API token",
        )


def require_shopify_session_shop_domain(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer session token",
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Shopify session token",
        )

    try:
        claims = jwt.decode(
            token,
            settings.SHOPIFY_APP_API_SECRET,
            algorithms=["HS256"],
            audience=settings.SHOPIFY_APP_API_KEY,
            options={
                "require": ["aud", "exp", "nbf", "iss", "dest"],
            },
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Shopify session token: {exc}",
        ) from exc

    destination = claims.get("dest")
    if not isinstance(destination, str) or not destination.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Shopify session token is missing dest claim",
        )
    parsed_destination = urlparse(destination)
    if parsed_destination.scheme != "https" or not parsed_destination.netloc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Shopify session token has invalid dest claim",
        )
    return normalize_shop_domain(parsed_destination.netloc)
