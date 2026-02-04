from dataclasses import dataclass
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.clerk import verify_clerk_token
from app.db.deps import get_session
from app.db.repositories.orgs import OrgsRepository


bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger("auth.deps")


@dataclass
class AuthContext:
    user_id: str
    org_id: str


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
    return AuthContext(user_id=user_id, org_id=str(org.id))
