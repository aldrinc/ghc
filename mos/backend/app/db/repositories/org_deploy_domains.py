from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import OrgDeployDomain


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


class OrgDeployDomainsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_hostnames(self, *, org_id: str) -> list[str]:
        stmt = (
            select(OrgDeployDomain.hostname)
            .where(OrgDeployDomain.org_id == org_id)
            .order_by(OrgDeployDomain.hostname.asc())
        )
        values = self.session.scalars(stmt).all()
        return [str(value).strip().lower() for value in values if str(value).strip()]

    def replace_hostnames(self, *, org_id: str, hostnames: list[str]) -> list[str]:
        normalized = _normalize_hostnames(hostnames)
        self.session.execute(delete(OrgDeployDomain).where(OrgDeployDomain.org_id == org_id))
        for hostname in normalized:
            self.session.add(OrgDeployDomain(org_id=org_id, hostname=hostname))
        self.session.commit()
        return normalized
