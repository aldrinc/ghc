from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DesignSystem


class DesignSystemsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, *, org_id: str, client_id: Optional[str] = None, include_shared: bool = False) -> list[DesignSystem]:
        stmt = select(DesignSystem).where(DesignSystem.org_id == org_id)
        if client_id:
            if include_shared:
                stmt = stmt.where((DesignSystem.client_id == client_id) | (DesignSystem.client_id.is_(None)))
            else:
                stmt = stmt.where(DesignSystem.client_id == client_id)
        stmt = stmt.order_by(DesignSystem.created_at.desc())
        return list(self.session.scalars(stmt).all())

    def has_client_design_systems(self, *, org_id: str, client_id: str) -> bool:
        stmt = (
            select(DesignSystem.id)
            .where(DesignSystem.org_id == org_id, DesignSystem.client_id == client_id)
            .limit(1)
        )
        return self.session.scalars(stmt).first() is not None

    def get(self, *, org_id: str, design_system_id: str) -> Optional[DesignSystem]:
        stmt = select(DesignSystem).where(
            DesignSystem.org_id == org_id,
            DesignSystem.id == design_system_id,
        )
        return self.session.scalars(stmt).first()

    def create(
        self,
        *,
        org_id: str,
        name: str,
        tokens: dict[str, Any],
        client_id: Optional[str] = None,
    ) -> DesignSystem:
        design_system = DesignSystem(
            org_id=org_id,
            client_id=client_id,
            name=name,
            tokens=tokens,
        )
        self.session.add(design_system)
        self.session.commit()
        self.session.refresh(design_system)
        return design_system

    def update(self, *, org_id: str, design_system_id: str, **fields: Any) -> Optional[DesignSystem]:
        design_system = self.get(org_id=org_id, design_system_id=design_system_id)
        if not design_system:
            return None
        for key, value in fields.items():
            setattr(design_system, key, value)
        self.session.commit()
        self.session.refresh(design_system)
        return design_system

    def delete(self, *, org_id: str, design_system_id: str) -> bool:
        design_system = self.get(org_id=org_id, design_system_id=design_system_id)
        if not design_system:
            return False
        self.session.delete(design_system)
        self.session.commit()
        return True
