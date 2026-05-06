from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import ClientPosthogSettings


class ClientPosthogSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, org_id: str, client_id: str) -> Optional[ClientPosthogSettings]:
        stmt = select(ClientPosthogSettings).where(
            ClientPosthogSettings.org_id == org_id,
            ClientPosthogSettings.client_id == client_id,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        client_id: str,
        enabled: bool,
        project_api_key: str | None,
        api_host: str | None,
        ui_host: str | None,
        defaults: str | None,
        person_profiles: str | None,
        source_mode: str,
        source_snippet: str | None,
        created_by_user_id: str | None,
    ) -> ClientPosthogSettings:
        existing = self.get(org_id=org_id, client_id=client_id)
        stmt = (
            insert(ClientPosthogSettings)
            .values(
                org_id=org_id,
                client_id=client_id,
                enabled=enabled,
                project_api_key=project_api_key,
                api_host=api_host,
                ui_host=ui_host,
                defaults=defaults,
                person_profiles=person_profiles,
                source_mode=source_mode,
                source_snippet=source_snippet,
                created_by_user_id=created_by_user_id,
            )
            .on_conflict_do_update(
                index_elements=["org_id", "client_id"],
                set_={
                    "enabled": enabled,
                    "project_api_key": project_api_key,
                    "api_host": api_host,
                    "ui_host": ui_host,
                    "defaults": defaults,
                    "person_profiles": person_profiles,
                    "source_mode": source_mode,
                    "source_snippet": source_snippet,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(ClientPosthogSettings)
        )
        record = self.session.execute(stmt).scalar_one()
        self.session.flush()
        self.session.refresh(record)
        if existing is None and created_by_user_id:
            record.created_by_user_id = created_by_user_id
            self.session.flush()
            self.session.refresh(record)
        return record
