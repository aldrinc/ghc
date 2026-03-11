from __future__ import annotations

import ipaddress
import time
from typing import Any, Dict, Optional
import logging
from urllib.parse import urlparse

import httpx
from jose import jwk, jwt
from jose.exceptions import JWTError, JWSError
from jose.utils import base64url_decode
from fastapi import HTTPException, status

from app.config import settings


logger = logging.getLogger("auth.clerk")
_LOCAL_DEV_ALLOWED_PORTS = {5173, 5275}
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


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


def _is_local_dev_origin(value: str) -> bool:
    if settings.ENVIRONMENT.strip().lower() != "development":
        return False

    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = parsed.hostname
    if not hostname or parsed.port not in _LOCAL_DEV_ALLOWED_PORTS:
        return False

    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True

    try:
        address = ipaddress.ip_address(hostname)
        return address.is_private or address in _SHARED_ADDRESS_SPACE
    except ValueError:
        return False


def _audience_value_allowed(value: Any, allowed_audiences: list[str]) -> bool:
    return isinstance(value, str) and (value in allowed_audiences or _is_local_dev_origin(value))


def _audience_claim_allowed(aud_claim: Any, azp_claim: Any, allowed_audiences: list[str]) -> bool:
    if isinstance(aud_claim, str):
        return _audience_value_allowed(aud_claim, allowed_audiences)
    if isinstance(aud_claim, list):
        return any(_audience_value_allowed(aud, allowed_audiences) for aud in aud_claim)
    if aud_claim is None and isinstance(azp_claim, str):
        return _audience_value_allowed(azp_claim, allowed_audiences)
    return False


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
            audience=None,
            issuer=settings.CLERK_JWT_ISSUER,
            options={"verify_aud": False},
        )
        aud_claim = claims.get("aud")
        azp_claim = claims.get("azp")
        allowed_audiences = settings.CLERK_AUDIENCE
        aud_type_valid = isinstance(aud_claim, (str, list)) or (aud_claim is None and isinstance(azp_claim, str))
        if not aud_type_valid:
            logger.warning(
                "Invalid token audience type",
                extra={"aud": aud_claim, "azp": azp_claim, "allowed": allowed_audiences},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token audience (aud={aud_claim}, azp={azp_claim}, allowed={allowed_audiences})",
            )
        aud_ok = _audience_claim_allowed(aud_claim, azp_claim, allowed_audiences)
        if not aud_ok:
            logger.warning(
                "Token audience rejected",
                extra={"aud": aud_claim, "azp": azp_claim, "allowed": allowed_audiences},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token audience (aud={aud_claim}, azp={azp_claim}, allowed={allowed_audiences})",
            )
        logger.debug(
            "Verified Clerk token",
            extra={
                "kid": public_key.get("kid"),
                "aud": aud_claim,
                "azp": azp_claim,
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
