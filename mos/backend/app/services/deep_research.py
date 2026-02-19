from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.config import settings
from app.db.base import SessionLocal
from app.db.enums import ResearchJobStatusEnum
from app.db.models import DeepResearchJob, WorkflowRun
from app.db.repositories.deep_research_jobs import DeepResearchJobsRepository
from app.observability import (
    LangfuseTraceContext,
    bind_langfuse_trace_context,
    get_openai_client_class,
    start_langfuse_span,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = int(os.getenv("LLM_POLL_INTERVAL_SECONDS", "15"))
# Deep research can run for multiple hours; use a dedicated, longer timeout by default.
_POLL_TIMEOUT_SECONDS = int(os.getenv("DEEP_RESEARCH_POLL_TIMEOUT_SECONDS", "21600"))
_DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv("O3_DEEP_RESEARCH_MAX_OUTPUT_TOKENS", "64000"))
_INCLUDE_SOURCES = ["web_search_call.action.sources"]
_TERMINAL_STATUSES = {
    ResearchJobStatusEnum.completed,
    ResearchJobStatusEnum.failed,
    ResearchJobStatusEnum.cancelled,
    ResearchJobStatusEnum.incomplete,
}


def build_openai_client(require_api_key: bool = True) -> Optional[Any]:
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key and require_api_key:
        return None
    client_kwargs: dict[str, Any] = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        client_kwargs["base_url"] = base_url
    openai_client_class = get_openai_client_class()
    return openai_client_class(**client_kwargs)


def extract_output_text(response: Any) -> Optional[str]:
    text = getattr(response, "output_text", None)
    if text:
        return text
    maybe_output = getattr(response, "output", None)
    if not maybe_output:
        return None
    try:
        parts: list[str] = []
        for item in maybe_output:
            content = getattr(item, "content", None)
            if not content:
                continue
            for chunk in content:
                chunk_text = getattr(chunk, "text", None)
                if chunk_text:
                    parts.append(chunk_text)
        return "".join(parts) if parts else None
    except Exception:
        return None


class DeepResearchJobService:
    def __init__(self, session: Session | None = None, openai_client: Any | None = None) -> None:
        self.session = session or SessionLocal()
        self.repo = DeepResearchJobsRepository(self.session)
        self.client = openai_client or build_openai_client(require_api_key=False)

    def _get_existing_job(
        self,
        *,
        org_id: str,
        client_id: str,
        temporal_workflow_id: str | None,
        step_key: str,
    ) -> DeepResearchJob | None:
        if not temporal_workflow_id:
            return None
        stmt = (
            select(DeepResearchJob)
            .where(
                DeepResearchJob.org_id == org_id,
                DeepResearchJob.client_id == client_id,
                DeepResearchJob.temporal_workflow_id == temporal_workflow_id,
                DeepResearchJob.step_key == step_key,
            )
            .order_by(DeepResearchJob.created_at.desc())
        )
        return self.session.scalars(stmt).first()

    def _resolve_workflow_run_id(
        self,
        *,
        org_id: str,
        workflow_run_id: str | None,
        temporal_workflow_id: str | None,
        parent_run_id: str | None = None,
        parent_workflow_id: str | None = None,
    ) -> str | None:
        """
        Ensure the workflow_run_id we persist actually exists in workflow_runs.
        If the provided id is a Temporal run id (not a DB UUID), try to look it up by temporal_run_id/temporal_workflow_id.
        """
        candidate_ids = {cid for cid in [workflow_run_id, parent_run_id] if cid}
        candidate_wf_ids = {cid for cid in [temporal_workflow_id, parent_workflow_id] if cid}
        if not candidate_ids and not candidate_wf_ids:
            return None

        stmt = select(WorkflowRun).where(
            WorkflowRun.org_id == org_id,
            or_(
                WorkflowRun.id.in_(candidate_ids),
                WorkflowRun.temporal_run_id.in_(candidate_ids),
                WorkflowRun.temporal_workflow_id.in_(candidate_wf_ids),
            ),
        )
        run = self.session.scalars(stmt).first()
        if not run:
            logger.warning(
                "Workflow run id not found; omitting FK for deep research job",
                extra={
                    "org_id": org_id,
                    "candidate_run_ids": list(candidate_ids),
                    "candidate_temporal_workflow_ids": list(candidate_wf_ids),
                },
            )
            return None
        return str(run.id)

    @staticmethod
    def _build_trace_context(
        *,
        org_id: str,
        client_id: str,
        workflow_run_id: str | None,
        temporal_workflow_id: str | None,
        step_key: str,
    ) -> LangfuseTraceContext:
        session_id = workflow_run_id or temporal_workflow_id or f"deep-research:{client_id}:{step_key}"
        metadata: dict[str, Any] = {
            "orgId": org_id,
            "clientId": client_id,
            "workflowRunId": workflow_run_id,
            "temporalWorkflowId": temporal_workflow_id,
            "stepKey": step_key,
        }
        return LangfuseTraceContext(
            name="workflow.deep_research",
            session_id=session_id,
            metadata=metadata,
            tags=["workflow", "deep_research"],
        )

    def run_deep_research(
        self,
        *,
        org_id: str,
        client_id: str,
        prompt: str,
        model: str,
        prompt_sha256: str | None = None,
        use_web_search: bool = True,
        max_output_tokens: int | None = None,
        step_key: str = "04",
        workflow_run_id: str | None = None,
        onboarding_payload_id: str | None = None,
        temporal_workflow_id: str | None = None,
        parent_workflow_id: str | None = None,
        parent_run_id: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Tuple[str, Optional[DeepResearchJob]]:
        resolved_workflow_run_id = self._resolve_workflow_run_id(
            org_id=org_id,
            workflow_run_id=workflow_run_id,
            temporal_workflow_id=temporal_workflow_id,
            parent_run_id=parent_run_id,
            parent_workflow_id=parent_workflow_id,
        )
        trace_context = self._build_trace_context(
            org_id=org_id,
            client_id=client_id,
            workflow_run_id=resolved_workflow_run_id,
            temporal_workflow_id=temporal_workflow_id,
            step_key=step_key,
        )
        trace_metadata: dict[str, Any] = {
            "orgId": org_id,
            "clientId": client_id,
            "model": model,
            "stepKey": step_key,
            "workflowRunId": resolved_workflow_run_id,
            "temporalWorkflowId": temporal_workflow_id,
            "useWebSearch": use_web_search,
            "maxOutputTokens": max_output_tokens,
            "promptSha256": prompt_sha256,
        }
        with bind_langfuse_trace_context(trace_context):
            with start_langfuse_span(
                name="deep_research.run",
                input={"prompt_chars": len(prompt)},
                metadata=trace_metadata,
                tags=["workflow", "deep_research"],
                trace_name="workflow.deep_research",
            ):
                existing = self._get_existing_job(
                    org_id=org_id,
                    client_id=client_id,
                    temporal_workflow_id=temporal_workflow_id,
                    step_key=step_key,
                )
                if existing and existing.response_id:
                    include_existing = _INCLUDE_SOURCES if existing.use_web_search else None
                    resumed = self._poll_until_terminal(
                        job_id=str(existing.id),
                        response_id=existing.response_id,
                        include=include_existing,
                    )
                    if resumed and getattr(resumed, "output_text", None):
                        return resumed.output_text, resumed

                job = self.repo.create_job(
                    org_id=org_id,
                    client_id=client_id,
                    workflow_run_id=resolved_workflow_run_id,
                    onboarding_payload_id=onboarding_payload_id,
                    temporal_workflow_id=temporal_workflow_id,
                    step_key=step_key,
                    model=model,
                    prompt=prompt,
                    prompt_sha256=prompt_sha256,
                    use_web_search=use_web_search,
                    max_output_tokens=max_output_tokens,
                    metadata=metadata,
                )

                if not self.client:
                    logger.error("OPENAI_API_KEY not configured; cannot start deep research.")
                    now = datetime.now(timezone.utc)
                    job = self.repo.update_job(
                        job_id=str(job.id),
                        status=ResearchJobStatusEnum.errored,
                        error="OPENAI_API_KEY not configured",
                        finished_at=now,
                    )
                    raise RuntimeError("OPENAI_API_KEY not configured; deep research cannot run.")

                include = _INCLUDE_SOURCES if use_web_search else None
                try:
                    response = self.client.responses.create(
                        model=model,
                        input=prompt,
                        background=True,
                        max_output_tokens=max_output_tokens or _DEFAULT_MAX_OUTPUT_TOKENS,
                        reasoning={"summary": "auto", "effort": "medium"},
                        tools=[{"type": "web_search"}] if use_web_search else None,
                        include=include,
                        metadata={
                            "deep_research_job_id": str(job.id),
                            "org_id": org_id,
                            "client_id": client_id,
                            "step_key": step_key,
                            "temporal_workflow_id": temporal_workflow_id,
                        },
                    )
                except Exception as exc:
                    logger.exception(
                        "Failed to start deep research response",
                        extra={"org_id": org_id, "client_id": client_id},
                    )
                    now = datetime.now(timezone.utc)
                    job = self.repo.update_job(
                        job_id=str(job.id),
                        status=ResearchJobStatusEnum.errored,
                        error=str(exc),
                        finished_at=now,
                    )
                    raise

                job = self.repo.mark_response(
                    job_id=str(job.id),
                    response_id=getattr(response, "id", ""),
                    status=self._status_from_response_status(getattr(response, "status", None)),
                )

                job = self._poll_until_terminal(
                    job_id=str(job.id),
                    response_id=getattr(response, "id", ""),
                    include=include,
                )

                if not job:
                    raise RuntimeError("Deep research job not found after polling for completion.")

                if not getattr(job, "output_text", None):
                    error_message = getattr(job, "error", None) or "Deep research returned no output text."
                    self.repo.update_job(job_id=str(job.id), error=error_message)
                    raise RuntimeError(error_message)

                if job.status not in _TERMINAL_STATUSES:
                    logger.warning(
                        "Deep research job ended without terminal status but returned output",
                        extra={"job_id": str(job.id), "status": getattr(job, "status", None)},
                    )

                return job.output_text, job

    def refresh_from_openai(self, *, job_id: str) -> Optional[DeepResearchJob]:
        job = self.repo.get(job_id=job_id)
        if not job or not job.response_id:
            return job
        include = _INCLUDE_SOURCES if job.use_web_search else None
        return self._retrieve_and_update(job_id=str(job.id), response_id=job.response_id, include=include, webhook_id=None)

    def cancel_job(self, *, job_id: str) -> Optional[DeepResearchJob]:
        job = self.repo.get(job_id=job_id)
        if not job or not job.response_id or not self.client:
            return job
        try:
            response = self.client.responses.cancel(job.response_id)
        except Exception as exc:
            logger.exception("Failed to cancel deep research job", extra={"job_id": job_id})
            return self.repo.update_job(
                job_id=str(job.id),
                status=ResearchJobStatusEnum.errored,
                error=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
        status = self._status_from_response_status(getattr(response, "status", None))
        finished_at = datetime.now(timezone.utc) if status in _TERMINAL_STATUSES else None
        return self.repo.update_job(
            job_id=str(job.id),
            status=status,
            full_response_json=response.model_dump() if hasattr(response, "model_dump") else None,
            finished_at=finished_at,
        )

    def process_webhook_event(self, *, event: Any, webhook_id: str | None = None) -> Optional[DeepResearchJob]:
        data = getattr(event, "data", None) or {}
        response_id = getattr(data, "id", None) or (data.get("id") if isinstance(data, dict) else None)
        if not response_id:
            logger.warning("Received OpenAI webhook without response id", extra={"webhook_id": webhook_id})
            return None

        job = self.repo.get_by_response_id(response_id=response_id)
        if not job:
            logger.warning(
                "OpenAI webhook for unknown response_id",
                extra={"response_id": response_id, "webhook_id": webhook_id},
            )
            return None

        if webhook_id and job.last_webhook_id and webhook_id == job.last_webhook_id:
            return job

        include = _INCLUDE_SOURCES if job.use_web_search else None
        return self._retrieve_and_update(
            job_id=str(job.id),
            response_id=response_id,
            include=include,
            webhook_id=webhook_id,
        )

    def _poll_until_terminal(
        self,
        *,
        job_id: str,
        response_id: str,
        include: Optional[list[str]] = None,
    ) -> Optional[DeepResearchJob]:
        if not self.client:
            return self.repo.update_job(
                job_id=job_id,
                status=ResearchJobStatusEnum.errored,
                error="OpenAI client not configured",
                finished_at=datetime.now(timezone.utc),
            )

        start = time.monotonic()
        while True:
            job = self._retrieve_and_update(job_id=job_id, response_id=response_id, include=include, webhook_id=None)
            status = job.status if job else None
            if status in _TERMINAL_STATUSES:
                return job

            if (time.monotonic() - start) > _POLL_TIMEOUT_SECONDS:
                return self.repo.update_job(
                    job_id=job_id,
                    status=ResearchJobStatusEnum.incomplete,
                    error="Timed out waiting for deep research response",
                    finished_at=datetime.now(timezone.utc),
                )
            time.sleep(_POLL_INTERVAL_SECONDS)

    def _retrieve_and_update(
        self,
        *,
        job_id: str,
        response_id: str,
        include: Optional[list[str]],
        webhook_id: str | None,
    ) -> Optional[DeepResearchJob]:
        if not self.client:
            return self.repo.update_job(
                job_id=job_id,
                status=ResearchJobStatusEnum.errored,
                error="OpenAI client not configured",
                last_webhook_id=webhook_id,
            )

        try:
            response = self.client.responses.retrieve(response_id, include=include)
        except Exception as exc:
            logger.exception("Failed to retrieve OpenAI response", extra={"job_id": job_id, "response_id": response_id})
            return self.repo.update_job(
                job_id=job_id,
                status=ResearchJobStatusEnum.errored,
                error=str(exc),
                last_webhook_id=webhook_id,
            )

        status = self._status_from_response_status(getattr(response, "status", None))
        finished_at = datetime.now(timezone.utc) if status in _TERMINAL_STATUSES else None
        job = self._update_from_response(
            job_id=job_id,
            response=response,
            status=status,
            webhook_id=webhook_id,
            finished_at=finished_at,
        )
        return job

    def _update_from_response(
        self,
        *,
        job_id: str,
        response: Any,
        status: ResearchJobStatusEnum,
        webhook_id: str | None,
        finished_at: datetime | None,
    ) -> Optional[DeepResearchJob]:
        output_text = extract_output_text(response)
        error = getattr(response, "error", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        full_response_json = response.model_dump() if hasattr(response, "model_dump") else None
        return self.repo.update_job(
            job_id=job_id,
            status=status,
            output_text=output_text,
            full_response_json=full_response_json,
            error=error,
            incomplete_details=incomplete_details,
            last_webhook_id=webhook_id,
            finished_at=finished_at,
        )

    def _status_from_response_status(self, status: str | None) -> ResearchJobStatusEnum:
        if not status:
            return ResearchJobStatusEnum.errored
        try:
            return ResearchJobStatusEnum(status)
        except Exception:
            return ResearchJobStatusEnum.errored
