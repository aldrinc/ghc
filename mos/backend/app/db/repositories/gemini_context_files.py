from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.enums import GeminiContextFileStatusEnum
from app.db.models import GeminiContextFile
from app.db.repositories.base import Repository


class GeminiContextFilesRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get_by_doc_key_hash(
        self,
        *,
        org_id: str,
        idea_workspace_id: str,
        doc_key: str,
        sha256: str,
        product_id: Optional[str],
    ) -> Optional[GeminiContextFile]:
        stmt = select(GeminiContextFile).where(
            GeminiContextFile.org_id == org_id,
            GeminiContextFile.idea_workspace_id == idea_workspace_id,
            GeminiContextFile.doc_key == doc_key,
            GeminiContextFile.sha256 == sha256,
        )
        if product_id is None:
            stmt = stmt.where(GeminiContextFile.product_id.is_(None))
        else:
            stmt = stmt.where(GeminiContextFile.product_id == product_id)
        return self.session.scalars(stmt).first()

    def upsert_ready(
        self,
        *,
        org_id: str,
        idea_workspace_id: str,
        client_id: Optional[str],
        product_id: Optional[str],
        campaign_id: Optional[str],
        doc_key: str,
        doc_title: Optional[str],
        source_kind: str,
        step_key: Optional[str],
        sha256: str,
        gemini_store_name: str,
        gemini_file_name: Optional[str],
        gemini_document_name: Optional[str],
        filename: str,
        mime_type: str,
        size_bytes: Optional[int],
        drive_doc_id: Optional[str],
        drive_url: Optional[str],
    ) -> GeminiContextFile:
        record = self.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
            product_id=product_id,
        )
        now = datetime.now(timezone.utc)
        if record:
            record.gemini_store_name = gemini_store_name
            record.gemini_file_name = gemini_file_name
            record.gemini_document_name = gemini_document_name
            record.filename = filename
            record.mime_type = mime_type
            record.size_bytes = size_bytes
            record.drive_doc_id = drive_doc_id
            record.drive_url = drive_url
            record.status = GeminiContextFileStatusEnum.ready
            record.error = None
            record.doc_title = doc_title
            record.source_kind = source_kind
            record.step_key = step_key
            record.product_id = product_id
            record.updated_at = now
        else:
            record = GeminiContextFile(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=step_key,
                sha256=sha256,
                gemini_store_name=gemini_store_name,
                gemini_file_name=gemini_file_name,
                gemini_document_name=gemini_document_name,
                filename=filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
                status=GeminiContextFileStatusEnum.ready,
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
        product_id: Optional[str],
        campaign_id: Optional[str],
        doc_key: str,
        doc_title: Optional[str],
        source_kind: str,
        step_key: Optional[str],
        sha256: str,
        gemini_store_name: Optional[str],
        gemini_file_name: Optional[str],
        gemini_document_name: Optional[str],
        filename: str,
        mime_type: str,
        error: str,
        drive_doc_id: Optional[str],
        drive_url: Optional[str],
    ) -> GeminiContextFile:
        record = self.get_by_doc_key_hash(
            org_id=org_id,
            idea_workspace_id=idea_workspace_id,
            doc_key=doc_key,
            sha256=sha256,
            product_id=product_id,
        )
        now = datetime.now(timezone.utc)
        if record:
            if gemini_store_name:
                record.gemini_store_name = gemini_store_name
            record.gemini_file_name = gemini_file_name
            record.gemini_document_name = gemini_document_name
            record.status = GeminiContextFileStatusEnum.failed
            record.error = error
            record.updated_at = now
            record.filename = filename
            record.mime_type = mime_type
            record.drive_doc_id = drive_doc_id
            record.drive_url = drive_url
        else:
            record = GeminiContextFile(
                org_id=org_id,
                idea_workspace_id=idea_workspace_id,
                client_id=client_id,
                product_id=product_id,
                campaign_id=campaign_id,
                doc_key=doc_key,
                doc_title=doc_title,
                source_kind=source_kind,
                step_key=step_key,
                sha256=sha256,
                gemini_store_name=gemini_store_name,
                gemini_file_name=gemini_file_name,
                gemini_document_name=gemini_document_name,
                filename=filename,
                mime_type=mime_type,
                size_bytes=None,
                drive_doc_id=drive_doc_id,
                drive_url=drive_url,
                status=GeminiContextFileStatusEnum.failed,
                error=error,
            )
            self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def list_for_workspace_or_client(
        self,
        *,
        org_id: str,
        idea_workspace_id: Optional[str],
        client_id: Optional[str],
        product_id: Optional[str],
        campaign_id: Optional[str],
    ) -> List[GeminiContextFile]:
        clauses = []
        if idea_workspace_id:
            clauses.append(GeminiContextFile.idea_workspace_id == idea_workspace_id)
        if client_id:
            clauses.append(GeminiContextFile.client_id == client_id)
        if campaign_id:
            clauses.append(GeminiContextFile.campaign_id == campaign_id)
        if not clauses:
            return []

        stmt = (
            select(GeminiContextFile)
            .where(
                GeminiContextFile.org_id == org_id,
                GeminiContextFile.status == GeminiContextFileStatusEnum.ready,
                or_(*clauses),
            )
            .order_by(GeminiContextFile.created_at)
        )
        if product_id is not None:
            stmt = stmt.where(GeminiContextFile.product_id == product_id)
        return list(self.session.scalars(stmt).all())
