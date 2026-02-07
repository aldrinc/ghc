from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResearchArtifact
from app.db.repositories.base import Repository


class ResearchArtifactsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def list_for_workflow_run(self, *, org_id: str, workflow_run_id: str) -> List[ResearchArtifact]:
        stmt = (
            select(ResearchArtifact)
            .where(
                ResearchArtifact.org_id == org_id,
                ResearchArtifact.workflow_run_id == workflow_run_id,
            )
            .order_by(ResearchArtifact.created_at)
        )
        return list(self.session.scalars(stmt).all())

    def get_for_step(
        self,
        *,
        org_id: str,
        workflow_run_id: str,
        step_key: str,
    ) -> Optional[ResearchArtifact]:
        stmt = select(ResearchArtifact).where(
            ResearchArtifact.org_id == org_id,
            ResearchArtifact.workflow_run_id == workflow_run_id,
            ResearchArtifact.step_key == step_key,
        )
        return self.session.scalars(stmt).first()

    def upsert(
        self,
        *,
        org_id: str,
        workflow_run_id: str,
        step_key: str,
        title: str | None,
        doc_id: str,
        doc_url: str,
        prompt_sha256: str | None,
        summary: str | None,
    ) -> ResearchArtifact:
        record = self.get_for_step(org_id=org_id, workflow_run_id=workflow_run_id, step_key=step_key)
        now = datetime.now(timezone.utc)
        if record:
            record.title = title
            record.doc_id = doc_id
            record.doc_url = doc_url
            record.prompt_sha256 = prompt_sha256
            record.summary = summary
            record.updated_at = now
            self.session.commit()
            self.session.refresh(record)
            return record

        record = ResearchArtifact(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            step_key=step_key,
            title=title,
            doc_id=doc_id,
            doc_url=doc_url,
            prompt_sha256=prompt_sha256,
            summary=summary,
            updated_at=now,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

