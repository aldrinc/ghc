from __future__ import annotations

from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from app.db.models import ClientCompliancePolicyOverride


class ClientCompliancePolicyOverridesRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(
        self, *, org_id: str, client_id: str, page_key: str
    ) -> Optional[ClientCompliancePolicyOverride]:
        stmt = select(ClientCompliancePolicyOverride).where(
            ClientCompliancePolicyOverride.org_id == org_id,
            ClientCompliancePolicyOverride.client_id == client_id,
            ClientCompliancePolicyOverride.page_key == page_key,
        )
        return self.session.scalars(stmt).first()

    def list_for_client(
        self, *, org_id: str, client_id: str
    ) -> list[ClientCompliancePolicyOverride]:
        stmt = (
            select(ClientCompliancePolicyOverride)
            .where(
                ClientCompliancePolicyOverride.org_id == org_id,
                ClientCompliancePolicyOverride.client_id == client_id,
            )
            .order_by(ClientCompliancePolicyOverride.page_key.asc())
        )
        return list(self.session.scalars(stmt).all())

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        page_key: str,
        markdown: str,
    ) -> ClientCompliancePolicyOverride:
        record = self.get(org_id=org_id, client_id=client_id, page_key=page_key)
        if record is None:
            record = ClientCompliancePolicyOverride(
                org_id=org_id,
                client_id=client_id,
                page_key=page_key,
                markdown=markdown,
            )
            self.session.add(record)
            self.session.commit()
            self.session.refresh(record)
            return record

        record.markdown = markdown
        record.updated_at = func.now()
        self.session.commit()
        self.session.refresh(record)
        return record

    def delete(self, *, org_id: str, client_id: str, page_key: str) -> bool:
        stmt = delete(ClientCompliancePolicyOverride).where(
            ClientCompliancePolicyOverride.org_id == org_id,
            ClientCompliancePolicyOverride.client_id == client_id,
            ClientCompliancePolicyOverride.page_key == page_key,
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return bool(result.rowcount)
