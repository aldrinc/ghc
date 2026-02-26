from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Job
from app.db.repositories.base import Repository


JOB_TYPE_ADD_CREATIVE_BREAKDOWN = "add_creative_breakdown"
SUBJECT_TYPE_AD = "ad"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_FAILED = "failed"


class JobsRepository(Repository):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get(self, job_id: str) -> Optional[Job]:
        stmt = select(Job).where(Job.id == job_id)
        return self.session.scalars(stmt).first()

    def get_by_dedupe_key(self, dedupe_key: str) -> Optional[Job]:
        stmt = select(Job).where(Job.dedupe_key == dedupe_key)
        return self.session.scalars(stmt).first()

    def get_or_create(
        self,
        *,
        org_id: str,
        client_id: Optional[str],
        research_run_id: Optional[str],
        job_type: str,
        subject_type: str,
        subject_id: str,
        dedupe_key: Optional[str],
        input_payload: Optional[dict[str, Any]] = None,
        status: str = JOB_STATUS_QUEUED,
    ) -> Tuple[Job, bool]:
        """
        Get an existing job by dedupe key or create a new one.

        Returns (job, created_flag).
        """
        if dedupe_key:
            existing = self.get_by_dedupe_key(dedupe_key)
            if existing:
                return existing, False

        job = Job(
            org_id=org_id,
            client_id=client_id,
            research_run_id=research_run_id,
            job_type=job_type,
            subject_type=subject_type,
            subject_id=subject_id,
            dedupe_key=dedupe_key,
            input=input_payload or {},
            status=status,
        )
        self.session.add(job)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            if dedupe_key:
                existing = self.get_by_dedupe_key(dedupe_key)
                if existing:
                    return existing, False
            raise
        self.session.refresh(job)
        return job, True

    def mark_running(self, job_id: str) -> Optional[Job]:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(status=JOB_STATUS_RUNNING, started_at=now, attempts=Job.attempts + 1, updated_at=now)
            .returning(Job)
        )
        job = self.session.execute(stmt).scalar_one_or_none()
        if job:
            self.session.commit()
        return job

    def set_output(self, job_id: str, *, output: dict[str, Any]) -> Optional[Job]:
        now = datetime.now(timezone.utc)
        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(output=output, updated_at=now)
            .returning(Job)
        )
        job = self.session.execute(stmt).scalar_one_or_none()
        if job:
            self.session.commit()
        return job

    def mark_succeeded(
        self,
        job_id: str,
        *,
        output: Optional[dict[str, Any]] = None,
        raw_output_text: Optional[str] = None,
    ) -> Optional[Job]:
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "status": JOB_STATUS_SUCCEEDED,
            "finished_at": now,
            "updated_at": now,
        }
        if output is not None:
            values["output"] = output
        if raw_output_text is not None:
            values["raw_output_text"] = raw_output_text
        stmt = update(Job).where(Job.id == job_id).values(**values).returning(Job)
        job = self.session.execute(stmt).scalar_one_or_none()
        if job:
            self.session.commit()
        return job

    def mark_failed(
        self,
        job_id: str,
        *,
        error: str,
        output: Optional[dict[str, Any]] = None,
    ) -> Optional[Job]:
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "status": JOB_STATUS_FAILED,
            "error": error[:5000],
            "finished_at": now,
            "updated_at": now,
        }
        if output is not None:
            values["output"] = output
        stmt = update(Job).where(Job.id == job_id).values(**values).returning(Job)
        job = self.session.execute(stmt).scalar_one_or_none()
        if job:
            self.session.commit()
        return job
