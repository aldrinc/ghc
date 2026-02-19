from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import AgentArtifact


class AgentArtifactsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        run_id: str,
        kind: str,
        key: Optional[str] = None,
        data_json: Optional[dict[str, Any]] = None,
    ) -> AgentArtifact:
        artifact = AgentArtifact(
            run_id=run_id,
            kind=kind,
            key=key,
            data_json=data_json or {},
        )
        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)
        return artifact

    def list_for_run(
        self,
        *,
        run_id: str,
        kind: Optional[str] = None,
        key: Optional[str] = None,
        limit: int = 200,
        newest_first: bool = False,
    ) -> list[AgentArtifact]:
        stmt = select(AgentArtifact).where(AgentArtifact.run_id == run_id)
        if kind:
            stmt = stmt.where(AgentArtifact.kind == kind)
        if key:
            stmt = stmt.where(AgentArtifact.key == key)
        order = desc(AgentArtifact.created_at) if newest_first else AgentArtifact.created_at.asc()
        stmt = stmt.order_by(order).limit(limit)
        return list(self.session.scalars(stmt).all())

