from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MetaAdAccountConnection, MetaWorkspaceAdConfig


class MetaAccountConfigsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_connections(self, *, org_id: str, include_archived: bool = False) -> list[MetaAdAccountConnection]:
        stmt = select(MetaAdAccountConnection).where(MetaAdAccountConnection.org_id == org_id)
        if not include_archived:
            stmt = stmt.where(MetaAdAccountConnection.status != "archived")
        stmt = stmt.order_by(MetaAdAccountConnection.name.asc(), MetaAdAccountConnection.created_at.asc())
        return list(self.session.scalars(stmt).all())

    def get_connection(self, *, org_id: str, connection_id: str) -> Optional[MetaAdAccountConnection]:
        stmt = select(MetaAdAccountConnection).where(
            MetaAdAccountConnection.org_id == org_id,
            MetaAdAccountConnection.id == connection_id,
        )
        return self.session.scalars(stmt).first()

    def get_connection_by_ad_account_id(
        self,
        *,
        org_id: str,
        ad_account_id: str,
    ) -> Optional[MetaAdAccountConnection]:
        stmt = select(MetaAdAccountConnection).where(
            MetaAdAccountConnection.org_id == org_id,
            MetaAdAccountConnection.ad_account_id == ad_account_id,
        )
        return self.session.scalars(stmt).first()

    def create_connection(self, **fields) -> MetaAdAccountConnection:
        record = MetaAdAccountConnection(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_connection(self, record: MetaAdAccountConnection, **fields) -> MetaAdAccountConnection:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_workspace_configs(
        self,
        *,
        org_id: str,
        client_id: str,
        include_archived: bool = False,
    ) -> list[MetaWorkspaceAdConfig]:
        stmt = select(MetaWorkspaceAdConfig).where(
            MetaWorkspaceAdConfig.org_id == org_id,
            MetaWorkspaceAdConfig.client_id == client_id,
        )
        if not include_archived:
            stmt = stmt.where(MetaWorkspaceAdConfig.status != "archived")
        stmt = stmt.order_by(MetaWorkspaceAdConfig.is_default.desc(), MetaWorkspaceAdConfig.name.asc())
        return list(self.session.scalars(stmt).all())

    def list_configs_for_connection(self, *, org_id: str, connection_id: str) -> list[MetaWorkspaceAdConfig]:
        stmt = (
            select(MetaWorkspaceAdConfig)
            .where(
                MetaWorkspaceAdConfig.org_id == org_id,
                MetaWorkspaceAdConfig.meta_connection_id == connection_id,
                MetaWorkspaceAdConfig.status != "archived",
            )
            .order_by(MetaWorkspaceAdConfig.client_id.asc(), MetaWorkspaceAdConfig.name.asc())
        )
        return list(self.session.scalars(stmt).all())

    def get_workspace_config(
        self,
        *,
        org_id: str,
        client_id: str,
        config_id: str,
    ) -> Optional[MetaWorkspaceAdConfig]:
        stmt = select(MetaWorkspaceAdConfig).where(
            MetaWorkspaceAdConfig.org_id == org_id,
            MetaWorkspaceAdConfig.client_id == client_id,
            MetaWorkspaceAdConfig.id == config_id,
        )
        return self.session.scalars(stmt).first()

    def get_workspace_config_by_id(self, *, org_id: str, config_id: str) -> Optional[MetaWorkspaceAdConfig]:
        stmt = select(MetaWorkspaceAdConfig).where(
            MetaWorkspaceAdConfig.org_id == org_id,
            MetaWorkspaceAdConfig.id == config_id,
        )
        return self.session.scalars(stmt).first()

    def get_default_workspace_config(self, *, org_id: str, client_id: str) -> Optional[MetaWorkspaceAdConfig]:
        stmt = select(MetaWorkspaceAdConfig).where(
            MetaWorkspaceAdConfig.org_id == org_id,
            MetaWorkspaceAdConfig.client_id == client_id,
            MetaWorkspaceAdConfig.is_default.is_(True),
            MetaWorkspaceAdConfig.status != "archived",
        )
        return self.session.scalars(stmt).first()

    def create_workspace_config(self, **fields) -> MetaWorkspaceAdConfig:
        record = MetaWorkspaceAdConfig(**fields)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_workspace_config(self, record: MetaWorkspaceAdConfig, **fields) -> MetaWorkspaceAdConfig:
        for key, value in fields.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(timezone.utc)
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def clear_default_workspace_config(self, *, org_id: str, client_id: str) -> None:
        records = self.list_workspace_configs(org_id=org_id, client_id=client_id, include_archived=True)
        changed = False
        for record in records:
            if record.is_default:
                record.is_default = False
                record.updated_at = datetime.now(timezone.utc)
                self.session.add(record)
                changed = True
        if changed:
            self.session.commit()

