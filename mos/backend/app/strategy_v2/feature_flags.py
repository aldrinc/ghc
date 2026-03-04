from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Client, Org


def is_strategy_v2_enabled(*, session: Session, org_id: str, client_id: str | None = None) -> bool:
    if client_id:
        client_row = session.scalar(
            select(Client.strategy_v2_enabled).where(
                Client.org_id == org_id,
                Client.id == client_id,
            )
        )
        if isinstance(client_row, bool) and client_row:
            return True

    org_row = session.scalar(
        select(Org.strategy_v2_enabled).where(
            Org.id == org_id,
        )
    )
    if isinstance(org_row, bool) and org_row:
        return True

    return bool(settings.STRATEGY_V2_DEFAULT_ENABLED)
