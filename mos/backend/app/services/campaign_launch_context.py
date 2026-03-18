from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum
from app.db.models import Campaign, WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.strategy_v2_launches import StrategyV2LaunchesRepository
from app.strategy_v2.launches import load_strategy_v2_source_context


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signature(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_launch_context_payload(
    *,
    campaign: Campaign,
    source_run: WorkflowRun,
    source_context: Any,
) -> dict[str, Any]:
    provenance = {
        "sourceStrategyV2WorkflowRunId": str(source_run.id),
        "sourceStrategyV2TemporalWorkflowId": str(source_context.source_temporal_workflow_id),
        "stage3ArtifactId": str(source_context.source_stage3_artifact_id),
        "offerArtifactId": str(source_context.source_offer_artifact_id),
        "copyArtifactId": str(source_context.source_copy_artifact_id),
        "copyContextArtifactId": str(source_context.source_copy_context_artifact_id),
        "awarenessMatrixArtifactId": (
            str(source_context.source_awareness_matrix_artifact_id)
            if source_context.source_awareness_matrix_artifact_id
            else None
        ),
        "requiredStepKeys": ["v2-06", "v2-08", "v2-09", "v2-11"],
        "stepPayloadArtifactIds": {
            step_key: str(record.artifact_id)
            for step_key, record in getattr(source_context, "step_payloads", {}).items()
            if step_key in {"v2-06", "v2-08", "v2-09", "v2-11"}
        },
    }
    signature = _signature(provenance)
    return {
        "schemaVersion": 1,
        "campaignId": str(campaign.id),
        "clientId": str(campaign.client_id),
        "productId": str(campaign.product_id) if campaign.product_id else None,
        "checkedAt": _iso_now(),
        "signature": signature,
        "provenance": provenance,
        "selectedAngle": {
            "angleId": str(source_context.selected_angle_id),
            "angleName": str(source_context.selected_angle_name),
            "angleRunId": str(source_context.angle_run_id),
            "payload": source_context.selected_angle,
        },
        "rankedAngleCandidates": list(source_context.ranked_angle_candidates or []),
        "offerOperatorInputs": dict(source_context.offer_operator_inputs or {}),
        "supportingResearch": {
            "competitorAnalysis": source_context.competitor_analysis,
            "vocObservations": list(source_context.voc_observations or []),
            "vocScored": dict(source_context.voc_scored or {}),
            "proofAssetCandidates": list(source_context.proof_asset_candidates or []),
        },
        "downstreamPacket": dict(source_context.source_downstream_packet or {}),
    }


def ensure_campaign_launch_context_artifact(
    *,
    session: Session,
    org_id: str,
    campaign: Campaign,
) -> dict[str, Any]:
    launches_repo = StrategyV2LaunchesRepository(session)
    launch_rows = launches_repo.list_for_campaign(org_id=org_id, campaign_id=str(campaign.id))
    if not launch_rows:
        return {
            "ready": False,
            "checkedAt": _iso_now(),
            "reason": "Campaign has no pinned Strategy V2 launch lineage yet.",
            "sourceStrategyV2WorkflowRunId": None,
            "sourceStrategyV2TemporalWorkflowId": None,
            "launchContextArtifactId": None,
            "refreshed": False,
            "staleArtifactId": None,
        }

    source_run = session.get(WorkflowRun, launch_rows[0].source_strategy_v2_workflow_run_id)
    if source_run is None:
        return {
            "ready": False,
            "checkedAt": _iso_now(),
            "reason": "Pinned Strategy V2 source workflow run could not be found for this campaign.",
            "sourceStrategyV2WorkflowRunId": str(launch_rows[0].source_strategy_v2_workflow_run_id),
            "sourceStrategyV2TemporalWorkflowId": None,
            "launchContextArtifactId": None,
            "refreshed": False,
            "staleArtifactId": None,
        }

    try:
        source_context = load_strategy_v2_source_context(
            session=session,
            org_id=org_id,
            source_run=source_run,
        )
    except (RuntimeError, ValidationError) as exc:
        return {
            "ready": False,
            "checkedAt": _iso_now(),
            "reason": str(exc),
            "sourceStrategyV2WorkflowRunId": str(source_run.id),
            "sourceStrategyV2TemporalWorkflowId": str(getattr(source_run, "temporal_workflow_id", "") or "") or None,
            "launchContextArtifactId": None,
            "refreshed": False,
            "staleArtifactId": None,
        }

    payload = _build_launch_context_payload(
        campaign=campaign,
        source_run=source_run,
        source_context=source_context,
    )
    artifacts_repo = ArtifactsRepository(session)
    latest = artifacts_repo.get_latest_by_type_for_campaign(
        org_id=org_id,
        campaign_id=str(campaign.id),
        artifact_type=ArtifactTypeEnum.strategy_v2_launch_context,
    )
    latest_signature = None
    if latest is not None and isinstance(latest.data, dict):
        latest_signature = latest.data.get("signature")

    refreshed = latest_signature != payload["signature"]
    stale_artifact_id = str(latest.id) if refreshed and latest is not None else None
    artifact = latest
    if refreshed:
        artifact = artifacts_repo.insert(
            org_id=org_id,
            client_id=str(campaign.client_id),
            product_id=str(campaign.product_id) if campaign.product_id else None,
            campaign_id=str(campaign.id),
            artifact_type=ArtifactTypeEnum.strategy_v2_launch_context,
            data=payload,
        )

    artifact_id = str(artifact.id) if artifact is not None else None
    return {
        "ready": True,
        "checkedAt": _iso_now(),
        "reason": None,
        "sourceStrategyV2WorkflowRunId": str(source_run.id),
        "sourceStrategyV2TemporalWorkflowId": str(source_context.source_temporal_workflow_id),
        "launchContextArtifactId": artifact_id,
        "refreshed": refreshed,
        "staleArtifactId": stale_artifact_id,
    }
