from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from temporalio import activity

from app.db.enums import ArtifactTypeEnum, WorkflowStatusEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.client_canon import ClientCanon
from app.schemas.metric_schema import MetricSchema
from app.db.base import session_scope
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository


@activity.defn
def build_client_canon_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    precanon_research = params.get("precanon_research") or {}
    with session_scope() as session:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        payload_data = payload.data if payload else {}

    # TODO: load onboarding payload and use LLM to enrich canon.
    research_summaries = precanon_research.get("step_summaries", {}) if isinstance(precanon_research, dict) else {}
    # Prefer onboarding story, then deep research summary if present.
    story = payload_data.get("brand_story") or research_summaries.get("04")
    if not story:
        raise ValueError("Missing brand_story and deep research summary for client canon generation.")

    canon = ClientCanon(
        clientId=client_id,
        brand={
            "story": story,
            "values": [],
            "toneOfVoice": {"do": [], "dont": []},
        },
    )
    canon_dict = canon.model_dump()
    canon_dict["precanon_research"] = precanon_research
    if research_summaries:
        canon_dict["research_highlights"] = research_summaries
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.client_canon, data=canon_dict)
    return canon_dict


@activity.defn
def build_metric_schema_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    with session_scope() as session:
        payload_repo = OnboardingPayloadsRepository(session)
        payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
        payload_data = payload.data if payload else {}

    metric_schema = MetricSchema(
        clientId=client_id,
    )
    with session_scope() as session:
        repo = ArtifactsRepository(session)
        repo.insert(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.metric_schema, data=metric_schema.model_dump())
    return metric_schema.model_dump()


@activity.defn
def persist_client_onboarding_artifacts_activity(params: Dict[str, Any]) -> Dict[str, bool]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    canon = params.get("canon")
    metric_schema = params.get("metric_schema")
    _ = params.get("research_artifacts")
    temporal_workflow_id = params.get("temporal_workflow_id")
    temporal_run_id = params.get("temporal_run_id")

    with session_scope() as session:
        artifacts_repo = ArtifactsRepository(session)
        if canon:
            artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                artifact_type=ArtifactTypeEnum.client_canon,
                data=canon,
            )
        if metric_schema:
            artifacts_repo.insert(
                org_id=org_id,
                client_id=client_id,
                artifact_type=ArtifactTypeEnum.metric_schema,
                data=metric_schema,
            )

        if temporal_workflow_id and temporal_run_id:
            wf_repo = WorkflowsRepository(session)
            run = wf_repo.get_by_temporal_ids(
                org_id=org_id,
                temporal_workflow_id=temporal_workflow_id,
                temporal_run_id=temporal_run_id,
            )
            if run:
                wf_repo.set_status(
                    org_id=org_id,
                    workflow_run_id=str(run.id),
                    status=WorkflowStatusEnum.completed,
                    finished_at=datetime.now(timezone.utc),
                )

    return {
        "canon_persisted": bool(canon),
        "metric_schema_persisted": bool(metric_schema),
    }
