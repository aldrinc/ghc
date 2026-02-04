from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Client, DesignSystem, Funnel, FunnelPage


def resolve_design_system_tokens(
    *,
    session: Session,
    org_id: str,
    client_id: Optional[str] = None,
    funnel: Optional[Funnel] = None,
    page: Optional[FunnelPage] = None,
) -> Optional[dict[str, Any]]:
    design_system_id: Optional[str] = None

    if page and page.design_system_id:
        design_system_id = str(page.design_system_id)
    if not design_system_id and funnel and funnel.design_system_id:
        design_system_id = str(funnel.design_system_id)
    if not design_system_id and client_id:
        client = session.scalars(
            select(Client).where(Client.org_id == org_id, Client.id == client_id)
        ).first()
        if client and client.design_system_id:
            design_system_id = str(client.design_system_id)

    if not design_system_id:
        return None

    design_system = session.scalars(
        select(DesignSystem).where(DesignSystem.org_id == org_id, DesignSystem.id == design_system_id)
    ).first()
    if not design_system:
        return None
    return design_system.tokens
