from dataclasses import dataclass, field
import logging
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.clerk import verify_clerk_token
from app.db.deps import get_session
from app.db.models import User
from app.db.repositories.orgs import OrgsRepository


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger("auth.deps")


@dataclass
class AuthContext:
    user_id: str
    org_id: str
    email: Optional[str] = None
    org_role: Optional[str] = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)


def _normalize_authz_values(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    values: list[str]
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list | tuple | set):
        values = [str(item) for item in raw if item is not None]
    else:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in value.replace(",", " ").split():
            clean = token.strip().lower()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            normalized.append(clean)
    return tuple(normalized)


def _auth_role_tokens(auth: AuthContext) -> set[str]:
    tokens = set(_normalize_authz_values(auth.roles))
    if auth.org_role:
        tokens.update(_normalize_authz_values(auth.org_role))
    return tokens


def auth_has_any_role(auth: AuthContext, allowed_roles: set[str]) -> bool:
    normalized_allowed = {role.strip().lower() for role in allowed_roles if role.strip()}
    return bool(_auth_role_tokens(auth) & normalized_allowed)


def auth_has_any_permission(auth: AuthContext, allowed_permissions: set[str]) -> bool:
    normalized_allowed = {
        permission.strip().lower()
        for permission in allowed_permissions
        if permission.strip()
    }
    return bool(set(_normalize_authz_values(auth.permissions)) & normalized_allowed)


_DEPLOY_OPERATOR_ROLES = {
    "admin",
    "org:admin",
    "ops",
    "org:ops",
    "operator",
    "org:operator",
    "deploy_operator",
    "org:deploy_operator",
}
_DEPLOY_OPERATOR_PERMISSIONS = {
    "deploy:read",
    "deploy:write",
    "deploy:apply",
    "deploy:*",
}
_DEPLOY_APPLY_PERMISSIONS = {
    "deploy:apply",
    "deploy:*",
}


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> AuthContext:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    claims = verify_clerk_token(credentials.credentials)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
    external_org_id = (
        claims.get("org_id")
        or claims.get("organization_id")
        or (claims.get("orgs") or [{}])[0].get("id")
    )
    if not external_org_id:
        logger.warning(
            "Missing organization in token",
            extra={"sub": user_id, "claims_keys": list(claims.keys()), "orgs": claims.get("orgs")},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing organization context in token",
        )

    orgs_repo = OrgsRepository(session)
    org = orgs_repo.get_by_external_id(external_org_id)
    if not org:
        logger.info("Creating org from Clerk external_id", extra={"external_org_id": external_org_id, "sub": user_id})
        org = orgs_repo.create(name=f"Clerk org {external_org_id}", external_id=external_org_id)
    else:
        logger.debug(
            "Resolved org from Clerk token",
            extra={"external_org_id": external_org_id, "org_id": str(org.id), "sub": user_id},
        )

    logger.debug("AuthContext built", extra={"sub": user_id, "org_id": str(org.id)})
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        stmt = select(User.email).where(User.org_id == org.id, User.clerk_user_id == user_id)
        email = session.execute(stmt).scalar_one_or_none()

    return AuthContext(
        user_id=user_id,
        org_id=str(org.id),
        email=email.strip() if isinstance(email, str) else None,
        org_role=claims.get("org_role") if isinstance(claims.get("org_role"), str) else None,
        roles=_normalize_authz_values(claims.get("roles")),
        permissions=_normalize_authz_values(claims.get("org_permissions")),
    )


def require_deploy_operator(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    if auth_has_any_role(auth, _DEPLOY_OPERATOR_ROLES) or auth_has_any_permission(
        auth,
        _DEPLOY_OPERATOR_PERMISSIONS,
    ):
        return auth
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Deploy access requires an admin, ops, operator, or deploy permission.",
    )


def require_deploy_apply_operator(auth: AuthContext = Depends(get_current_user)) -> AuthContext:
    if auth_has_any_role(auth, {"admin", "org:admin"}) or auth_has_any_permission(
        auth,
        _DEPLOY_APPLY_PERMISSIONS,
    ):
        return auth
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Deploy apply requires an admin role or deploy:apply permission.",
    )
