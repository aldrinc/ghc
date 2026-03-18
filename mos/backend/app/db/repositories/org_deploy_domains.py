from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import OrgDeployDomain


LEGACY_DEPLOY_DOMAIN_SCOPE_ERROR = (
    "Legacy org-scoped deploy domains exist. Re-save deploy domains from the owning workspace "
    "before continuing."
)


def _normalize_hostnames(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError("Deploy domains must be strings.")
        hostname = raw.strip().lower()
        if not hostname or hostname in seen:
            continue
        seen.add(hostname)
        normalized.append(hostname)
    return normalized


def _normalize_client_id(*, client_id: str) -> str:
    normalized = str(client_id or "").strip()
    if not normalized:
        raise ValueError("Deploy domains require a workspace client_id.")
    return normalized


class OrgDeployDomainsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def has_legacy_unscoped_hostnames(self, *, org_id: str) -> bool:
        stmt = (
            select(OrgDeployDomain.id)
            .where(OrgDeployDomain.org_id == org_id, OrgDeployDomain.client_id.is_(None))
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def list_hostnames(self, *, org_id: str, client_id: str, strict: bool = True) -> list[str]:
        normalized_client_id = _normalize_client_id(client_id=client_id)
        stmt = (
            select(OrgDeployDomain.hostname)
            .where(
                OrgDeployDomain.org_id == org_id,
                OrgDeployDomain.client_id == normalized_client_id,
            )
            .order_by(OrgDeployDomain.hostname.asc())
        )
        values = self.session.scalars(stmt).all()
        normalized = [str(value).strip().lower() for value in values if str(value).strip()]
        if normalized:
            return normalized
        if strict and self.has_legacy_unscoped_hostnames(org_id=org_id):
            raise ValueError(LEGACY_DEPLOY_DOMAIN_SCOPE_ERROR)
        return []

    def replace_hostnames(self, *, org_id: str, client_id: str, hostnames: list[str]) -> list[str]:
        normalized_client_id = _normalize_client_id(client_id=client_id)
        normalized = _normalize_hostnames(hostnames)
        self.session.execute(
            delete(OrgDeployDomain).where(
                OrgDeployDomain.org_id == org_id,
                OrgDeployDomain.client_id == normalized_client_id,
            )
        )
        for hostname in normalized:
            self.session.add(
                OrgDeployDomain(
                    org_id=org_id,
                    client_id=normalized_client_id,
                    hostname=hostname,
                )
            )
        self.session.commit()
        return normalized
