from __future__ import annotations

from typing import Any, Dict

from temporalio import activity

from app.db.enums import ArtifactTypeEnum
from app.db.repositories.artifacts import ArtifactsRepository
from app.schemas.client_canon import ClientCanon
from app.schemas.metric_schema import MetricSchema
from app.db.base import SessionLocal
from app.db.repositories.onboarding_payloads import OnboardingPayloadsRepository


def _repo() -> ArtifactsRepository:
    return ArtifactsRepository(SessionLocal())


@activity.defn
def build_client_canon_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    precanon_research = params.get("precanon_research") or {}
    payload_repo = OnboardingPayloadsRepository(SessionLocal())
    payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
    payload_data = payload.data if payload else {}

    # TODO: load onboarding payload and use LLM; returning stub for now.
    research_summaries = precanon_research.get("step_summaries", {}) if isinstance(precanon_research, dict) else {}
    # Prefer onboarding story, then deep research summary if present.
    story = payload_data.get("brand_story") or research_summaries.get("04") or "Placeholder story"

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
    repo = _repo()
    repo.insert(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.client_canon, data=canon_dict)
    return canon_dict


@activity.defn
def build_metric_schema_activity(params: Dict[str, Any]) -> Dict[str, Any]:
    org_id = params["org_id"]
    client_id = params["client_id"]
    onboarding_payload_id = params["onboarding_payload_id"]
    payload_repo = OnboardingPayloadsRepository(SessionLocal())
    payload = payload_repo.get(org_id=org_id, payload_id=onboarding_payload_id)
    payload_data = payload.data if payload else {}

    metric_schema = MetricSchema(
        clientId=client_id,
        primaryMarkets=payload_data.get("primary_markets") or [],
        primaryLanguages=payload_data.get("primary_languages") or [],
    )
    repo = _repo()
    repo.insert(org_id=org_id, client_id=client_id, artifact_type=ArtifactTypeEnum.metric_schema, data=metric_schema.model_dump())
    return metric_schema.model_dump()


@activity.defn
def persist_client_onboarding_artifacts_activity(params: Dict[str, Any]) -> None:
    # Placeholder activity; artifacts already persisted in build_* activities.
    # Accept and ignore research artifacts for now so the workflow can pass them through.
    _ = params.get("research_artifacts")
    return None
