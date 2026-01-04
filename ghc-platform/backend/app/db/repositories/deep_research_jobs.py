from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import ResearchJobStatusEnum
from app.db.models import DeepResearchJob
from app.db.repositories.base import Repository


class DeepResearchJobsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def create_job(
        self,
        *,
        org_id: str,
        client_id: str,
        prompt: str,
        model: str,
        prompt_sha256: str | None = None,
        use_web_search: bool = False,
        max_output_tokens: int | None = None,
        step_key: str = "04",
        workflow_run_id: str | None = None,
        onboarding_payload_id: str | None = None,
        temporal_workflow_id: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
        status: ResearchJobStatusEnum = ResearchJobStatusEnum.created,
    ) -> DeepResearchJob:
        job = DeepResearchJob(
            org_id=org_id,
            client_id=client_id,
            workflow_run_id=workflow_run_id,
            onboarding_payload_id=onboarding_payload_id,
            temporal_workflow_id=temporal_workflow_id,
            step_key=step_key,
            model=model,
            prompt=prompt,
            prompt_sha256=prompt_sha256,
            use_web_search=use_web_search,
            max_output_tokens=max_output_tokens,
            metadata_json=metadata,
            status=status,
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def get(self, *, job_id: str, org_id: str | None = None) -> Optional[DeepResearchJob]:
        stmt = select(DeepResearchJob).where(DeepResearchJob.id == job_id)
        if org_id:
            stmt = stmt.where(DeepResearchJob.org_id == org_id)
        return self.session.scalars(stmt).first()

    def get_by_response_id(self, *, response_id: str) -> Optional[DeepResearchJob]:
        stmt = select(DeepResearchJob).where(DeepResearchJob.response_id == response_id)
        return self.session.scalars(stmt).first()

    def mark_response(
        self,
        *,
        job_id: str,
        response_id: str,
        status: ResearchJobStatusEnum | str | None,
    ) -> Optional[DeepResearchJob]:
        job = self.get(job_id=job_id)
        if not job:
            return None
        job.response_id = response_id
        normalized_status = self._normalize_status(status)
        if normalized_status:
            job.status = normalized_status
        job.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(job)
        return job

    def update_job(
        self,
        *,
        job_id: str,
        org_id: str | None = None,
        status: ResearchJobStatusEnum | str | None = None,
        output_text: str | None = None,
        full_response_json: dict[str, Any] | None = None,
        error: str | None = None,
        incomplete_details: dict[str, Any] | None = None,
        last_webhook_id: str | None = None,
        finished_at: datetime | None = None,
    ) -> Optional[DeepResearchJob]:
        job = self.get(job_id=job_id, org_id=org_id)
        if not job:
            return None
        normalized_status = self._normalize_status(status)
        if normalized_status:
            job.status = normalized_status
        if output_text is not None:
            job.output_text = output_text
        if full_response_json is not None:
            job.full_response_json = full_response_json
        if error is not None:
            job.error = error
        if incomplete_details is not None:
            job.incomplete_details = incomplete_details
        if last_webhook_id is not None:
            job.last_webhook_id = last_webhook_id
        if finished_at is not None:
            job.finished_at = finished_at
        job.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(job)
        return job

    def _normalize_status(self, status: ResearchJobStatusEnum | str | None) -> ResearchJobStatusEnum | None:
        if status is None:
            return None
        if isinstance(status, ResearchJobStatusEnum):
            return status
        try:
            return ResearchJobStatusEnum(status)
        except Exception:
            return ResearchJobStatusEnum.errored
