from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.enums import ClaudeContextFileStatusEnum
from app.db.models import ClaudeContextFile
from app.db.repositories.base import Repository


class ClaudeContextFilesRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get_by_doc_key_hash(
        self, *, org_id: str, idea_workspace_id: str, doc_key: str, sha256: str
    ) -> Optional[ClaudeContextFile]:
        stmt = select(ClaudeContextFile).where(
            ClaudeContextFile.org_id == org_id,
            ClaudeContextFile.idea_workspace_id == idea_workspace_id,
            ClaudeContextFile.doc_key == doc_key,
            ClaudeContextFile.sha256 == sha256,
        )
        return self.session.scalars(stmt).first()

    def upsert_ready(
        self,
        *,
        org_id: str,
        idea_workspace_id: str,
        client_id: Optional[str],
        campaign_id: Optional[str],
        doc_key: str,
        doc_title: Optional[str],
        source_kind: str,
        step_key: Optional[str],
        sha256: str,
        claude_file_id: str,
        filename: str,
        mime_type: str,
        size_bytes: Optional[int],
        drive_doc_id: Optional[str],
        drive_url: Optional[str],
    ) -> ClaudeContextFile:
        record = self.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
        )
        now = datetime.now(timezone.utc)
        if record:
            record.claude_file_id = claude_file_id
            record.filename = filename
            record.mime_type = mime_type
            record.size_bytes = size_bytes
            record.drive_doc_id = drive_doc_id
            record.drive_url = drive_url
            record.status = ClaudeContextFileStatusEnum.ready
            record.error = None
            record.doc_title = doc_title
            record.source_kind = source_kind
            record.step_key = step_key
            record.updated_at = now
        else:
            record = ClaudeContextFile(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=step_key,
                sha256=sha256,
                claude_file_id=claude_file_id,
                filename=filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
                status=ClaudeContextFileStatusEnum.ready,
            )
            self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def upsert_failed(
        self,
        *,
        org_id: str,
        idea_workspace_id: str,
        client_id: Optional[str],
        campaign_id: Optional[str],
        doc_key: str,
        doc_title: Optional[str],
        source_kind: str,
        step_key: Optional[str],
        sha256: str,
        filename: str,
        mime_type: str,
        error: str,
        drive_doc_id: Optional[str],
        drive_url: Optional[str],
    ) -> ClaudeContextFile:
        record = self.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
        )
        now = datetime.now(timezone.utc)
        if record:
            record.status = ClaudeContextFileStatusEnum.failed
            record.error = error
            record.updated_at = now
            record.filename = filename
            record.mime_type = mime_type
            record.drive_doc_id = drive_doc_id
            record.drive_url = drive_url
        else:
            record = ClaudeContextFile(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=step_key,
                sha256=sha256,
                claude_file_id=None,
                filename=filename,
                mime_type=mime_type,
                size_bytes=None,
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
                status=ClaudeContextFileStatusEnum.failed,
                error=error,
            )
            self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_for_workspace(self, *, org_id: str, idea_workspace_id: str) -> List[ClaudeContextFile]:
        stmt = (
            select(ClaudeContextFile)
            .where(
                ClaudeContextFile.org_id == org_id,
                ClaudeContextFile.idea_workspace_id == idea_workspace_id,
                ClaudeContextFile.status == ClaudeContextFileStatusEnum.ready,
            )
            .order_by(ClaudeContextFile.created_at)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_generation_context(
        self,
        *,
        org_id: str,
        idea_workspace_id: str,
        client_id: Optional[str],
        campaign_id: Optional[str],
    ) -> List[ClaudeContextFile]:
        stmt = (
            select(ClaudeContextFile)
            .where(
                ClaudeContextFile.org_id == org_id,
                ClaudeContextFile.idea_workspace_id == idea_workspace_id,
                ClaudeContextFile.status == ClaudeContextFileStatusEnum.ready,
            )
            .order_by(ClaudeContextFile.created_at)
        )
        if client_id:
            stmt = stmt.where(
                (ClaudeContextFile.client_id == client_id) | (ClaudeContextFile.client_id.is_(None))
            )
        if campaign_id:
            stmt = stmt.where(
                (ClaudeContextFile.campaign_id == campaign_id) | (ClaudeContextFile.campaign_id.is_(None))
            )
        return list(self.session.scalars(stmt).all())

    def list_for_workspace_or_client(
        self,
        *,
        org_id: str,
        idea_workspace_id: Optional[str],
        client_id: Optional[str],
        campaign_id: Optional[str],
    ) -> List[ClaudeContextFile]:
        """
        Broader fetch used for UI: return ready Claude files that match the workspace id
        OR the client/campaign when legacy records used workflow ids as idea_workspace_id.
        """
        clauses = []
        if idea_workspace_id:
            clauses.append(ClaudeContextFile.idea_workspace_id == idea_workspace_id)
        if client_id:
            clauses.append(ClaudeContextFile.client_id == client_id)
        if campaign_id:
            clauses.append(ClaudeContextFile.campaign_id == campaign_id)
        if not clauses:
            return []

        stmt = (
            select(ClaudeContextFile)
            .where(
                ClaudeContextFile.org_id == org_id,
                ClaudeContextFile.status == ClaudeContextFileStatusEnum.ready,
                or_(*clauses),
            )
            .order_by(ClaudeContextFile.created_at)
        )
        return list(self.session.scalars(stmt).all())
