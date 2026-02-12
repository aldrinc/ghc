from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict

from temporalio import activity

from sqlalchemy import select

from app.db.base import session_scope
from app.db.models import WorkflowRun
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository
from app.google_clients import upload_text_file, create_folder
from app.services.claude_files import ensure_uploaded_to_claude
from app.llm.client import OpenAIResponsePendingError
from app.temporal.precanon.research import (
    IdeaFolderRequest,
    IdeaFolderResult,
    LlmGenerationResult,
    PersistArtifactRequest,
    PersistArtifactResult,
    StepGenerationRequest,
    build_file_name,
    run_deep_research,
    run_llm_generation,
    sanitize_folder_name,
)


def _now_iso() -> str:
    return datetime.utcnow().replace(tzinfo=None).isoformat() + "Z"


def _resolve_root_workflow_run_id(
    *,
    session,
    org_id: str,
    workflow_id: str | None,
    workflow_run_id: str | None,
    parent_workflow_id: str | None,
    parent_run_id: str | None,
) -> str:
    """
    Research artifacts should be attached to the *root* workflow run (the one the UI loads).
    In onboarding, precanon runs as a child workflow, so we must use parent temporal ids.
    """
    if parent_workflow_id or parent_run_id:
        if not parent_workflow_id or not parent_run_id:
            raise RuntimeError(
                "parent_workflow_id and parent_run_id are required together to persist research artifacts."
            )
        stmt = (
            select(WorkflowRun)
            .where(
                WorkflowRun.org_id == org_id,
                WorkflowRun.temporal_workflow_id == parent_workflow_id,
                WorkflowRun.temporal_run_id == parent_run_id,
            )
            .order_by(WorkflowRun.started_at.desc())
        )
        run = session.scalars(stmt).first()
        if not run:
            raise RuntimeError(
                "Workflow run not found for parent temporal ids while persisting research artifact "
                f"(org_id={org_id}, parent_workflow_id={parent_workflow_id}, parent_run_id={parent_run_id})."
            )
        return str(run.id)

    if not workflow_id or not workflow_run_id:
        raise RuntimeError(
            "workflow_id and workflow_run_id are required to persist research artifacts when parent ids are absent."
        )
    stmt = (
        select(WorkflowRun)
        .where(
            WorkflowRun.org_id == org_id,
            WorkflowRun.temporal_workflow_id == workflow_id,
            WorkflowRun.temporal_run_id == workflow_run_id,
        )
        .order_by(WorkflowRun.started_at.desc())
    )
    run = session.scalars(stmt).first()
    if not run:
        raise RuntimeError(
            "Workflow run not found for temporal ids while persisting research artifact "
            f"(org_id={org_id}, workflow_id={workflow_id}, run_id={workflow_run_id})."
        )
    return str(run.id)


@activity.defn
def fetch_onboarding_payload_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    with session_scope() as session:
        repo = OnboardingPayloadsRepository(session)
        payload = repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        return payload.data if payload and payload.data else {}


@activity.defn(name="precanon.ensure_idea_folder")
def ensure_idea_folder_activity(request: IdeaFolderRequest) -> IdeaFolderResult:
    parent_folder_id = request.parent_folder_id or os.getenv("RESEARCH_DRIVE_PARENT_FOLDER_ID") or os.getenv(
        "PARENT_FOLDER_ID"
    )
    if not parent_folder_id:
        return IdeaFolderResult(idea_folder_id=None, idea_folder_url=None)

    folder = create_folder(sanitize_folder_name(request.idea_folder_name), parent_folder_id)
    idea_folder_id = folder.get("id")
    idea_folder_url = folder.get("webViewLink") or folder.get("webContentLink")
    return IdeaFolderResult(idea_folder_id=idea_folder_id, idea_folder_url=idea_folder_url)


def _run_llm_activity(request: StepGenerationRequest, *, expected_step_key: str) -> LlmGenerationResult:
    if request.step_key != expected_step_key:
        raise ValueError(f"Expected step_key {expected_step_key} but received {request.step_key}")
    try:
        return run_llm_generation(request)
    except OpenAIResponsePendingError as exc:
        raise RuntimeError(
            f"LLM generation pending for step {request.step_key}: {exc}. "
            f"Resume with response_id={exc.response_id}."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"LLM generation failed for step {request.step_key}: {exc}") from exc


@activity.defn(name="precanon.step01.generate_output")
def generate_step01_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="01")


@activity.defn(name="precanon.step015.generate_output")
def generate_step015_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="015")


@activity.defn(name="precanon.step03.generate_output")
def generate_step03_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="03")


@activity.defn(name="precanon.step06.generate_output")
def generate_step06_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="06")


@activity.defn(name="precanon.step07.generate_output")
def generate_step07_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="07")


@activity.defn(name="precanon.step08.generate_output")
def generate_step08_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="08")


@activity.defn(name="precanon.step09.generate_output")
def generate_step09_output_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    return _run_llm_activity(request, expected_step_key="09")


@activity.defn(name="precanon.step04.deep_research")
def run_step04_deep_research_activity(request: StepGenerationRequest) -> LlmGenerationResult:
    if request.step_key != "04":
        raise ValueError(f"Expected step_key 04 but received {request.step_key}")
    try:
        return run_deep_research(request)
    except Exception as exc:
        raise RuntimeError(f"Deep research failed for step 04: {exc}") from exc


@activity.defn(name="precanon.persist_artifact")
def persist_artifact_activity(request: PersistArtifactRequest) -> PersistArtifactResult:
    parent_folder_id = request.parent_folder_id or os.getenv("RESEARCH_DRIVE_PARENT_FOLDER_ID") or os.getenv(
        "PARENT_FOLDER_ID"
    )
    effective_parent = request.idea_folder_id or parent_folder_id
    file_name = build_file_name(title=request.title, workflow_id=request.workflow_id, step_key=request.step_key)
    idea_workspace_id = request.idea_workspace_id or request.workflow_id

    try:
        drive_file = upload_text_file(name=file_name, content=request.content, parent_folder_id=effective_parent)
        doc_id = drive_file.get("id", "")
        doc_url = drive_file.get("webViewLink") or drive_file.get("webContentLink") or ""
        if not doc_id or not doc_url:
            raise RuntimeError("Failed to persist research artifact to Drive")
    except Exception:
        if not request.allow_drive_stub:
            raise
        doc_id = f"drive-stub-{uuid.uuid4()}"
        doc_url = f"drive-stub://{doc_id}"

    claude_file_id = None
    try:
        claude_file_id = ensure_uploaded_to_claude(
            org_id=request.org_id,
            idea_workspace_id=idea_workspace_id or request.workflow_id or "",
            client_id=request.client_id,
            product_id=request.product_id,
            campaign_id=request.campaign_id,
            doc_key=f"precanon:{request.step_key}",
            doc_title=request.title,
            source_kind="precanon_step",
            step_key=request.step_key,
            filename=file_name,
            mime_type="text/plain",
            content_bytes=request.content.encode("utf-8"),
            drive_doc_id=doc_id,
            drive_url=doc_url,
            allow_stub=request.allow_claude_stub,
        )
    except Exception:
        if not request.allow_claude_stub:
            raise

    with session_scope() as session:
        root_workflow_run_id = _resolve_root_workflow_run_id(
            session=session,
            org_id=request.org_id,
            workflow_id=request.workflow_id,
            workflow_run_id=request.workflow_run_id,
            parent_workflow_id=request.parent_workflow_id,
            parent_run_id=request.parent_run_id,
        )
        repo = ResearchArtifactsRepository(session)
        repo.upsert(
            org_id=request.org_id,
            workflow_run_id=root_workflow_run_id,
            step_key=request.step_key,
            title=request.title,
            doc_id=doc_id,
            doc_url=doc_url,
            prompt_sha256=request.prompt_sha256 or None,
            summary=(request.summary or "").strip() or None,
        )

    return PersistArtifactResult(
        doc_id=doc_id,
        doc_url=doc_url,
        idea_folder_id=request.idea_folder_id,
        idea_folder_url=request.idea_folder_url,
        claude_file_id=claude_file_id,
        created_at_iso=_now_iso(),
    )
