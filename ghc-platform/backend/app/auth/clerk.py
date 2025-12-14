from __future__ import annotations

import time
from typing import Any, Dict, Optional
import logging

import httpx
from jose import jwk, jwt
from jose.exceptions import JWTError, JWSError
from jose.utils import base64url_decode
from fastapi import HTTPException, status

from app.config import settings


logger = logging.getLogger("auth.clerk")


class _JWKSCache:
    def __init__(self) -> None:
        self.jwks: Optional[Dict[str, Any]] = None
        self.cached_at: float = 0.0
        self.ttl_seconds: int = 300

    def get(self) -> Optional[Dict[str, Any]]:
        if self.jwks and (time.time() - self.cached_at) < self.ttl_seconds:
            return self.jwks
        return None

    def set(self, jwks: Dict[str, Any]) -> None:
        self.jwks = jwks
        self.cached_at = time.time()


_cache = _JWKSCache()


def _fetch_jwks() -> Dict[str, Any]:
    cached = _cache.get()
    if cached:
        return cached
    try:
        resp = httpx.get(settings.CLERK_JWKS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _cache.set(data)
        return data
    except httpx.HTTPError as exc:
        logger.exception("JWKS fetch failed", extra={"jwks_url": settings.CLERK_JWKS_URL})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Clerk JWKS",
        ) from exc


def _get_public_key(token: str) -> Dict[str, Any]:
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.warning("Invalid token header", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing kid in token")
    jwks = _fetch_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    # cache miss; refetch once
    _cache.set(None)  # type: ignore[arg-type]
    jwks = _fetch_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    logger.warning("Signing key not found", extra={"kid": kid})
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signing key not found")


def verify_clerk_token(token: str) -> Dict[str, Any]:
    try:
        public_key = _get_public_key(token)
        key = jwk.construct(public_key)

        message, encoded_sig = token.rsplit(".", 1)
        decoded_sig = base64url_decode(encoded_sig.encode())
        if not key.verify(message.encode(), decoded_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

        claims = jwt.decode(
            token,
            key=key.to_pem().decode(),
            algorithms=[public_key.get("alg", "RS256")],
            audience=settings.CLERK_AUDIENCE,
            issuer=settings.CLERK_JWT_ISSUER,
        )
        logger.debug(
            "Verified Clerk token",
            extra={
                "kid": public_key.get("kid"),
                "aud": claims.get("aud"),
                "iss": claims.get("iss"),
                "org_id": claims.get("org_id") or claims.get("organization_id"),
                "orgs_len": len(claims.get("orgs") or []),
                "sub": claims.get("sub"),
            },
        )
        return claims
    except (JWTError, JWSError, ValueError) as exc:
        logger.warning("Token verification failed", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
