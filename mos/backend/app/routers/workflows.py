import json
from datetime import datetime, timezone
import hashlib
import os
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthContext, get_current_user
from app.config import settings
from app.db.deps import get_session
from app.db.enums import ArtifactTypeEnum, AssetStatusEnum, WorkflowKindEnum, WorkflowStatusEnum
from app.db.models import Asset, WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.campaigns import CampaignsRepository
from app.db.repositories.clients import ClientsRepository
from app.db.repositories.products import ProductsRepository
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.db.repositories.strategy_v2_launches import StrategyV2LaunchesRepository
from app.db.repositories.workflows import WorkflowsRepository
from app.schemas.workflow_launches import (
    StrategyV2LaunchActionResponse,
    StrategyV2LaunchAdditionalAngleRequest,
    StrategyV2LaunchAdditionalUmsRequest,
    StrategyV2LaunchAngleCampaignRequest,
)
from app.google_clients import download_drive_text_file
from app.strategy_v2.contracts import (
    AngleSelectionDecision,
    CompetitorAssetConfirmationDecision,
    FinalCopyApprovalDecision,
    OfferWinnerSelectionDecision,
    ResearchProceedDecision,
    UmpUmsSelectionDecision,
)
from app.strategy_v2.feature_flags import is_strategy_v2_enabled
from app.strategy_v2.launches import (
    StrategyV2SourceContext,
    build_angle_campaign_name,
    build_launch_key,
    find_ranked_angle_payload,
    list_ranked_angle_ids,
    load_strategy_v2_source_context,
    resolve_ums_selection_map,
)
from app.temporal.client import get_temporal_client
from app.temporal.workflows.strategy_v2_launch import (
    StrategyV2AngleCampaignLaunchInput,
    StrategyV2AngleCampaignLaunchWorkflow,
    StrategyV2AngleIterationInput,
    StrategyV2AngleIterationWorkflow,
)
from app.temporal.workflows.strategy_v2 import StrategyV2Input, StrategyV2Workflow
from temporalio.api.enums.v1 import WorkflowExecutionStatus
from temporalio.exceptions import WorkflowAlreadyStartedError

router = APIRouter(prefix="/workflows", tags=["workflows"])

_HITL_POLICY_MODE_ENV = "STRATEGY_V2_HITL_POLICY_MODE"
_HITL_POLICY_PRODUCTION_STRICT = "production_strict"
_HITL_POLICY_INTERNAL_VALIDATION = "internal_validation"


def _workflow_execution_status_member(*names: str):
    for name in names:
        member = getattr(WorkflowExecutionStatus, name, None)
        if member is not None:
            return member
    return None


def _workflow_status_map() -> dict[object, WorkflowStatusEnum]:
    mapping: dict[object, WorkflowStatusEnum] = {}
    candidates: list[tuple[tuple[str, ...], WorkflowStatusEnum]] = [
        (("RUNNING", "WORKFLOW_EXECUTION_STATUS_RUNNING"), WorkflowStatusEnum.running),
        (("COMPLETED", "WORKFLOW_EXECUTION_STATUS_COMPLETED"), WorkflowStatusEnum.completed),
        (("FAILED", "WORKFLOW_EXECUTION_STATUS_FAILED"), WorkflowStatusEnum.failed),
        (("CANCELED", "CANCELLED", "WORKFLOW_EXECUTION_STATUS_CANCELED"), WorkflowStatusEnum.cancelled),
        (("TERMINATED", "WORKFLOW_EXECUTION_STATUS_TERMINATED"), WorkflowStatusEnum.cancelled),
        (("TIMED_OUT", "WORKFLOW_EXECUTION_STATUS_TIMED_OUT"), WorkflowStatusEnum.failed),
        (("CONTINUED_AS_NEW", "WORKFLOW_EXECUTION_STATUS_CONTINUED_AS_NEW"), WorkflowStatusEnum.running),
    ]
    for names, internal_status in candidates:
        member = _workflow_execution_status_member(*names)
        if member is not None:
            mapping[member] = internal_status
    return mapping


def _timestamp_proto_to_iso(value: Any) -> str | None:
    seconds = getattr(value, "seconds", None)
    if not isinstance(seconds, int):
        return None
    nanos_raw = getattr(value, "nanos", 0)
    nanos = int(nanos_raw) if isinstance(nanos_raw, int) else 0
    dt = datetime.fromtimestamp(seconds + (nanos / 1_000_000_000), tz=timezone.utc)
    return dt.isoformat()


def _decode_temporal_heartbeat_payload(payload: Any) -> Any:
    raw_data = getattr(payload, "data", None)
    if not isinstance(raw_data, (bytes, bytearray)):
        return None
    text = raw_data.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _extract_pending_activity_progress(desc: Any) -> list[dict[str, Any]]:
    raw_description = getattr(desc, "raw_description", None)
    pending_rows = getattr(raw_description, "pending_activities", None)
    if pending_rows is None:
        return []

    progress_rows: list[dict[str, Any]] = []
    for row in list(pending_rows):
        state_value = getattr(row, "state", None)
        if isinstance(state_value, int):
            try:
                enum_desc = row.DESCRIPTOR.fields_by_name["state"].enum_type
                state_name = enum_desc.values_by_number[state_value].name
            except Exception:
                state_name = str(state_value)
        else:
            state_name = str(state_value) if state_value is not None else None

        heartbeat_payload = None
        heartbeat_details = getattr(row, "heartbeat_details", None)
        payloads = list(getattr(heartbeat_details, "payloads", []) or [])
        if payloads:
            heartbeat_payload = _decode_temporal_heartbeat_payload(payloads[-1])

        activity_type = getattr(getattr(row, "activity_type", None), "name", None)
        progress_rows.append(
            {
                "activity_id": str(getattr(row, "activity_id", "") or ""),
                "activity_type": str(activity_type or ""),
                "state": state_name,
                "attempt": int(getattr(row, "attempt", 0) or 0),
                "last_worker_identity": str(getattr(row, "last_worker_identity", "") or ""),
                "last_started_time": _timestamp_proto_to_iso(getattr(row, "last_started_time", None)),
                "last_heartbeat_time": _timestamp_proto_to_iso(getattr(row, "last_heartbeat_time", None)),
                "scheduled_time": _timestamp_proto_to_iso(getattr(row, "scheduled_time", None)),
                "expiration_time": _timestamp_proto_to_iso(getattr(row, "expiration_time", None)),
                "heartbeat_progress": heartbeat_payload,
            }
        )
    return progress_rows


def _maybe_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _resolve_workflow_run(
    *,
    repo: WorkflowsRepository,
    org_id: str,
    workflow_run_id_or_temporal_id: str,
):
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id_or_temporal_id)
    if parsed_run_id:
        run = repo.get(org_id=org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        run = repo.get_by_temporal_workflow_id(
            org_id=org_id,
            temporal_workflow_id=workflow_run_id_or_temporal_id,
        )
    return run


def _normalize_angle_gate_candidates(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_angle = row.get("angle")
        if isinstance(raw_angle, dict):
            angle = raw_angle
        else:
            angle = row
        angle_id = angle.get("angle_id")
        if not isinstance(angle_id, str) or not angle_id.strip():
            continue
        normalized.append(dict(angle))
    return normalized


def _strategy_v2_state_from_research_artifacts(
    *,
    session: Session,
    org_id: str,
    workflow_run_id: str,
    client_id: str | None,
    product_id: str | None,
) -> dict[str, Any]:
    research_repo = ResearchArtifactsRepository(session)
    artifact_repo = ArtifactsRepository(session)
    rows = research_repo.list_for_workflow_run(org_id=org_id, workflow_run_id=workflow_run_id)
    step_payloads: dict[str, dict[str, Any]] = {}
    artifact_refs: dict[str, str] = {}
    for row in rows:
        doc_id = str(getattr(row, "doc_id", "") or "").strip()
        doc_url = str(getattr(row, "doc_url", "") or "").strip()
        if not doc_id:
            continue
        artifact_refs[str(row.step_key)] = doc_url or f"artifact://{doc_id}"
        artifact = artifact_repo.get(org_id=org_id, artifact_id=doc_id)
        if not artifact or not isinstance(artifact.data, dict):
            continue
        data = artifact.data
        payload = data.get("payload")
        if isinstance(payload, dict):
            step_payloads[str(row.step_key)] = payload

    stage1_payload: dict[str, Any] | None = None
    if client_id and product_id:
        stage1_artifact = artifact_repo.get_latest_by_type(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage1,
        )
        if stage1_artifact and isinstance(stage1_artifact.data, dict):
            stage1_payload = stage1_artifact.data

    current_stage = "unknown"
    pending_signal_type = None
    if "v2-11" in step_payloads:
        current_stage = "completed"
    elif "v2-10" in step_payloads:
        current_stage = "v2-11"
        pending_signal_type = "strategy_v2_approve_final_copy"
    elif "v2-09" in step_payloads:
        current_stage = "v2-10"
    elif "v2-08b" in step_payloads:
        current_stage = "v2-09"
        pending_signal_type = "strategy_v2_select_offer_winner"
    elif "v2-08" in step_payloads:
        current_stage = "v2-08b"
        pending_signal_type = "strategy_v2_select_ump_ums"
    elif "v2-07" in step_payloads:
        current_stage = "v2-08"
    elif "v2-06" in step_payloads:
        current_stage = "v2-07"
        pending_signal_type = "strategy_v2_select_angle"
    elif "v2-05" in step_payloads:
        current_stage = "v2-06"
    elif "v2-05a" in step_payloads:
        current_stage = "v2-05"
    elif "v2-04" in step_payloads:
        current_stage = "v2-05a"
    elif "v2-03c" in step_payloads:
        current_stage = "v2-04"
    elif "v2-03b" in step_payloads:
        current_stage = "v2-03c"
    elif "v2-03" in step_payloads:
        current_stage = "v2-03b"
    elif "v2-02" in step_payloads:
        current_stage = "v2-03"
    elif "v2-02b" in step_payloads:
        current_stage = "v2-02"
    elif "v2-02a" in step_payloads:
        current_stage = "v2-02b"
        pending_signal_type = "strategy_v2_confirm_competitor_assets"
    elif "v2-01" in step_payloads:
        current_stage = "v2-02a"
        pending_signal_type = "strategy_v2_proceed_research"

    candidate_summaries: dict[str, Any] = {}
    v2_02i = step_payloads.get("v2-02i")
    if isinstance(v2_02i, dict):
        selected_candidates = v2_02i.get("selected_candidates")
        if isinstance(selected_candidates, list):
            candidate_summaries["competitor_assets"] = selected_candidates
    v2_06 = step_payloads.get("v2-06")
    if isinstance(v2_06, dict) and isinstance(v2_06.get("ranked_candidates"), list):
        candidate_summaries["angles"] = v2_06.get("ranked_candidates")

    v2_08 = step_payloads.get("v2-08")
    if isinstance(v2_08, dict):
        pair_scoring = v2_08.get("pair_scoring")
        if isinstance(pair_scoring, dict) and isinstance(pair_scoring.get("ranked_pairs"), list):
            candidate_summaries["ump_ums_pairs"] = pair_scoring.get("ranked_pairs")
    v2_08b = step_payloads.get("v2-08b")
    if isinstance(v2_08b, dict):
        composite = v2_08b.get("composite_results")
        if isinstance(composite, dict) and isinstance(composite.get("variants"), list):
            candidate_summaries["offer_variants"] = composite.get("variants")

    pending_decision_payload: dict[str, Any] | None = None
    if pending_signal_type == "strategy_v2_proceed_research":
        pending_decision_payload = {
            "stage1": stage1_payload,
            "foundational_step_summaries": None,
        }
    elif pending_signal_type == "strategy_v2_confirm_competitor_assets":
        pending_decision_payload = {
            "competitor_urls": (stage1_payload or {}).get("competitor_urls"),
            "candidates": candidate_summaries.get("competitor_assets") or [],
            "candidate_summary": v2_02i.get("candidate_summary") if isinstance(v2_02i, dict) else None,
        }
    elif pending_signal_type == "strategy_v2_select_angle":
        pending_decision_payload = {
            "candidates": _normalize_angle_gate_candidates(candidate_summaries.get("angles")),
        }
    elif pending_signal_type == "strategy_v2_select_ump_ums":
        proof_asset_candidates = v2_08.get("proof_asset_candidates") if isinstance(v2_08, dict) else None
        pending_decision_payload = {
            "candidates": candidate_summaries.get("ump_ums_pairs") or [],
            "proof_asset_candidates": proof_asset_candidates if isinstance(proof_asset_candidates, list) else [],
        }
    elif pending_signal_type == "strategy_v2_select_offer_winner":
        pending_decision_payload = {
            "candidates": candidate_summaries.get("offer_variants") or [],
        }
    elif pending_signal_type == "strategy_v2_approve_final_copy":
        v2_10 = step_payloads.get("v2-10")
        copy_payload = v2_10.get("copy_payload") if isinstance(v2_10, dict) else None
        pending_decision_payload = {
            "copy_artifact_id": v2_10.get("copy_artifact_id") if isinstance(v2_10, dict) else None,
            "headline": copy_payload.get("headline") if isinstance(copy_payload, dict) else None,
        }

    return {
        "workflow_run_id": workflow_run_id,
        "current_stage": current_stage,
        "pending_signal_type": pending_signal_type,
        "required_signal_type": pending_signal_type,
        "pending_decision_payload": pending_decision_payload,
        "scored_candidate_summaries": candidate_summaries,
        "artifact_refs": artifact_refs,
    }


def _normalize_strategy_v2_artifact_refs(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized = dict(value)
    nested = value.get("step_payload_artifact_ids")
    if not isinstance(nested, dict):
        return normalized
    for raw_step_key, raw_artifact_id in nested.items():
        if not isinstance(raw_step_key, str):
            continue
        step_key = raw_step_key.strip()
        if not step_key:
            continue
        if not isinstance(raw_artifact_id, str):
            continue
        artifact_id = raw_artifact_id.strip()
        if not artifact_id:
            continue
        normalized.setdefault(step_key, artifact_id)
        normalized.setdefault(f"step_payload_{step_key.replace('-', '_')}_artifact_id", artifact_id)
    return normalized


def _normalize_strategy_v2_state_for_api(state: Any) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    normalized_state = dict(state)
    pending_signal_type = normalized_state.get("pending_signal_type")
    pending_payload = normalized_state.get("pending_decision_payload")
    if pending_signal_type == "strategy_v2_select_angle" and isinstance(pending_payload, dict):
        normalized_payload = dict(pending_payload)
        normalized_payload["candidates"] = _normalize_angle_gate_candidates(pending_payload.get("candidates"))
        normalized_state["pending_decision_payload"] = normalized_payload
    return normalized_state


def _require_nonempty_string(*, value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise HTTPException(status_code=400, detail=f"{field_name} is required.")


def _current_hitl_policy_mode() -> str:
    mode = str(os.getenv(_HITL_POLICY_MODE_ENV, _HITL_POLICY_PRODUCTION_STRICT) or "").strip().lower()
    if mode not in {_HITL_POLICY_PRODUCTION_STRICT, _HITL_POLICY_INTERNAL_VALIDATION}:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Invalid {_HITL_POLICY_MODE_ENV} value '{mode}'. "
                f"Expected '{_HITL_POLICY_PRODUCTION_STRICT}' or '{_HITL_POLICY_INTERNAL_VALIDATION}'."
            ),
        )
    return mode


def _prepare_strategy_v2_decision_payload(*, body: dict[str, Any], auth: AuthContext) -> dict[str, Any]:
    if "operator_user_id" in body:
        raise HTTPException(
            status_code=400,
            detail=(
                "operator_user_id is assigned by the server from authenticated identity; "
                "do not provide operator_user_id in request payload."
            ),
        )
    payload = dict(body)
    payload["operator_user_id"] = auth.user_id
    decision_mode = str(payload.get("decision_mode") or "manual").strip().lower()
    if decision_mode not in {"manual", "internal_automation"}:
        raise HTTPException(
            status_code=400,
            detail="decision_mode must be one of: manual, internal_automation.",
        )
    if decision_mode == "internal_automation" and _current_hitl_policy_mode() != _HITL_POLICY_INTERNAL_VALIDATION:
        raise HTTPException(
            status_code=403,
            detail=(
                "decision_mode=internal_automation is disabled in production_strict policy mode. "
                "Set STRATEGY_V2_HITL_POLICY_MODE=internal_validation for explicit validation runs."
            ),
        )
    payload["decision_mode"] = decision_mode

    attestation = payload.get("attestation")
    if not isinstance(attestation, dict):
        raise HTTPException(
            status_code=400,
            detail=(
                "attestation is required and must include reviewed_evidence and understands_impact booleans."
            ),
        )
    reviewed_evidence = attestation.get("reviewed_evidence")
    understands_impact = attestation.get("understands_impact")
    if not isinstance(reviewed_evidence, bool) or not isinstance(understands_impact, bool):
        raise HTTPException(
            status_code=400,
            detail=(
                "attestation.reviewed_evidence and attestation.understands_impact must both be booleans."
            ),
        )
    payload["attestation"] = {
        "reviewed_evidence": reviewed_evidence,
        "understands_impact": understands_impact,
    }
    return payload


def _normalize_strategy_v2_copy_payload(copy_artifact: Any) -> dict[str, Any] | None:
    if copy_artifact is None or not isinstance(getattr(copy_artifact, "data", None), dict):
        return None
    payload = copy_artifact.data
    approved_copy = payload.get("approved_copy")
    if isinstance(approved_copy, dict):
        return approved_copy
    return payload


def _normalize_required_string_list(*, value: list[str], field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=400, detail=f"{field_name} must include at least one non-empty value.")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(status_code=400, detail=f"{field_name} must contain non-empty strings.")
        cleaned = item.strip()
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} must include at least one non-empty value.")
    return normalized


def _strategy_v2_launch_record_to_payload(row: Any, *, launch_status: str | None = None) -> dict[str, Any]:
    launch_type_raw = str(getattr(row, "launch_type", "") or "").strip()
    if launch_type_raw not in {"initial_angle", "additional_ums", "additional_angle"}:
        launch_type = "initial_angle"
    else:
        launch_type = launch_type_raw
    created_at = getattr(row, "created_at", None)
    created_at_iso = created_at.isoformat() if isinstance(created_at, datetime) else ""
    return {
        "id": str(getattr(row, "id")),
        "launch_type": launch_type,
        "launch_key": str(getattr(row, "launch_key", "") or ""),
        "campaign_id": str(getattr(row, "campaign_id")) if getattr(row, "campaign_id", None) else None,
        "funnel_id": str(getattr(row, "funnel_id")) if getattr(row, "funnel_id", None) else None,
        "angle_id": str(getattr(row, "angle_id", "") or ""),
        "angle_run_id": str(getattr(row, "angle_run_id", "") or ""),
        "selected_ums_id": str(getattr(row, "selected_ums_id")) if getattr(row, "selected_ums_id", None) else None,
        "selected_variant_id": (
            str(getattr(row, "selected_variant_id")) if getattr(row, "selected_variant_id", None) else None
        ),
        "launch_index": int(getattr(row, "launch_index")) if getattr(row, "launch_index", None) is not None else None,
        "launch_workflow_run_id": (
            str(getattr(row, "launch_workflow_run_id")) if getattr(row, "launch_workflow_run_id", None) else None
        ),
        "launch_temporal_workflow_id": (
            str(getattr(row, "launch_temporal_workflow_id"))
            if getattr(row, "launch_temporal_workflow_id", None)
            else None
        ),
        "launch_status": launch_status,
        "created_by_user": str(getattr(row, "created_by_user")) if getattr(row, "created_by_user", None) else None,
        "created_at": created_at_iso,
    }


def _compose_launch_action_response(
    *,
    run_id: str,
    temporal_workflow_id: str,
    launch_records: list[dict[str, Any]],
) -> dict[str, Any]:
    campaign_ids: list[str] = []
    funnel_workflow_run_ids = [run_id]
    for row in launch_records:
        campaign_id = row.get("campaign_id")
        if isinstance(campaign_id, str) and campaign_id and campaign_id not in campaign_ids:
            campaign_ids.append(campaign_id)
    return StrategyV2LaunchActionResponse(
        launch_workflow_run_id=run_id,
        launch_temporal_workflow_id=temporal_workflow_id,
        campaign_ids=campaign_ids,
        funnel_workflow_run_ids=funnel_workflow_run_ids,
        launch_records=launch_records,
    ).model_dump(mode="python")


def _launch_index_for_angle(
    *,
    launches_repo: StrategyV2LaunchesRepository,
    org_id: str,
    client_id: str,
    product_id: str,
    angle_id: str,
    angle_id_counts: dict[str, int],
) -> int:
    if angle_id not in angle_id_counts:
        base_index = launches_repo.next_launch_index(
            org_id=org_id,
            client_id=client_id,
            product_id=product_id,
            angle_id=angle_id,
        )
        angle_id_counts[angle_id] = base_index
    next_index = angle_id_counts[angle_id]
    angle_id_counts[angle_id] = next_index + 1
    return next_index


def _idempotent_launch_response_from_rows(rows: list[Any]) -> dict[str, Any]:
    if not rows:
        raise RuntimeError("No launch rows were provided for idempotent response.")

    rows_by_workflow: dict[tuple[str, str], list[Any]] = {}
    for row in rows:
        launch_workflow_run_id = str(getattr(row, "launch_workflow_run_id", "") or "").strip()
        launch_temporal_workflow_id = str(getattr(row, "launch_temporal_workflow_id", "") or "").strip()
        if not launch_workflow_run_id or not launch_temporal_workflow_id:
            raise RuntimeError(
                "Existing launch record is missing launch workflow metadata and cannot satisfy idempotent response."
            )
        key = (launch_workflow_run_id, launch_temporal_workflow_id)
        rows_by_workflow.setdefault(key, []).append(row)

    if len(rows_by_workflow) != 1:
        raise RuntimeError(
            "Existing launch records span multiple launch workflows and cannot satisfy a single idempotent response. "
            "Remediation: request one launch key set per workflow run or use launch history."
        )

    (launch_workflow_run_id, launch_temporal_workflow_id), workflow_rows = next(iter(rows_by_workflow.items()))
    payload_rows = [_strategy_v2_launch_record_to_payload(row) for row in workflow_rows]
    return _compose_launch_action_response(
        run_id=launch_workflow_run_id,
        temporal_workflow_id=launch_temporal_workflow_id,
        launch_records=payload_rows,
    )


def _load_source_context_or_409(
    *,
    session: Session,
    org_id: str,
    source_run: Any,
) -> StrategyV2SourceContext:
    try:
        return load_strategy_v2_source_context(
            session=session,
            org_id=org_id,
            source_run=source_run,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _build_deterministic_launch_temporal_workflow_id(
    *,
    prefix: str,
    org_id: str,
    source_run_id: str,
    launch_keys: list[str],
) -> str:
    normalized = sorted({key.strip() for key in launch_keys if isinstance(key, str) and key.strip()})
    if not normalized:
        raise RuntimeError("At least one launch key is required to build deterministic launch workflow id.")
    digest = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"{prefix}-{org_id}-{source_run_id}-{digest}"


@router.get("")
def list_workflows(
    clientId: str | None = None,
    productId: str | None = None,
    campaignId: str | None = None,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list:
    if (clientId and not productId and campaignId is None) or (productId and not clientId):
        raise HTTPException(
            status_code=400,
            detail="clientId and productId are required together unless campaignId is provided.",
        )
    repo = WorkflowsRepository(session)
    return jsonable_encoder(
        repo.list(
            org_id=auth.org_id,
            client_id=clientId,
            product_id=productId,
            campaign_id=campaignId,
        )
    )


@router.post("/strategy-v2/start")
async def start_strategy_v2_workflow(
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    client_id = _require_nonempty_string(value=body.get("client_id"), field_name="client_id")
    product_id = _require_nonempty_string(value=body.get("product_id"), field_name="product_id")

    clients_repo = ClientsRepository(session)
    client = clients_repo.get(org_id=auth.org_id, client_id=client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    products_repo = ProductsRepository(session)
    product = products_repo.get(org_id=auth.org_id, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if str(product.client_id) != client_id:
        raise HTTPException(
            status_code=400,
            detail="product_id does not belong to client_id.",
        )
    stage0_overrides_raw = body.get("stage0_overrides", {})
    if not isinstance(stage0_overrides_raw, dict):
        raise HTTPException(status_code=400, detail="stage0_overrides must be an object.")
    override_description = stage0_overrides_raw.get("description")
    has_override_description = isinstance(override_description, str) and override_description.strip()
    if not isinstance(product.description, str) or not product.description.strip():
        if not has_override_description:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Product description is required for Strategy V2 stage0 translation. "
                    "Update product.description or provide stage0_overrides.description before starting Strategy V2."
                ),
            )

    if not is_strategy_v2_enabled(session=session, org_id=auth.org_id, client_id=client_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Strategy V2 is disabled for this tenant/client. Enable strategy_v2_enabled first.",
        )

    workflows_repo = WorkflowsRepository(session)
    existing = workflows_repo.list(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
    )
    running_strategy_v2 = [
        run for run in existing if run.kind == WorkflowKindEnum.strategy_v2 and run.status == WorkflowStatusEnum.running
    ]
    if running_strategy_v2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Strategy V2 workflow is already running for this client/product.",
        )

    onboarding_payload_id = body.get("onboarding_payload_id")
    if onboarding_payload_id is not None and (
        not isinstance(onboarding_payload_id, str) or not onboarding_payload_id.strip()
    ):
        raise HTTPException(status_code=400, detail="onboarding_payload_id must be a non-empty string when provided.")
    campaign_id = body.get("campaign_id")
    if campaign_id is not None and (not isinstance(campaign_id, str) or not campaign_id.strip()):
        raise HTTPException(status_code=400, detail="campaign_id must be a non-empty string when provided.")
    if "operator_user_id" in body:
        raise HTTPException(
            status_code=400,
            detail=(
                "operator_user_id is assigned by the server from authenticated identity; "
                "do not provide operator_user_id in request payload."
            ),
        )

    stage0_overrides = stage0_overrides_raw

    business_model = _require_nonempty_string(value=body.get("business_model"), field_name="business_model")
    funnel_position = _require_nonempty_string(value=body.get("funnel_position"), field_name="funnel_position")
    target_platforms_raw = body.get("target_platforms")
    if not isinstance(target_platforms_raw, list):
        raise HTTPException(status_code=400, detail="target_platforms must be a non-empty array of strings.")
    target_platforms = [
        item.strip() for item in target_platforms_raw if isinstance(item, str) and item.strip()
    ]
    if not target_platforms:
        raise HTTPException(status_code=400, detail="target_platforms must include at least one non-empty value.")
    target_regions_raw = body.get("target_regions")
    if not isinstance(target_regions_raw, list):
        raise HTTPException(status_code=400, detail="target_regions must be a non-empty array of strings.")
    target_regions = [
        item.strip() for item in target_regions_raw if isinstance(item, str) and item.strip()
    ]
    if not target_regions:
        raise HTTPException(status_code=400, detail="target_regions must include at least one non-empty value.")
    existing_proof_assets_raw = body.get("existing_proof_assets")
    if not isinstance(existing_proof_assets_raw, list):
        raise HTTPException(status_code=400, detail="existing_proof_assets must be a non-empty array of strings.")
    existing_proof_assets = [
        item.strip() for item in existing_proof_assets_raw if isinstance(item, str) and item.strip()
    ]
    if not existing_proof_assets:
        raise HTTPException(status_code=400, detail="existing_proof_assets must include at least one non-empty value.")

    brand_voice_notes = _require_nonempty_string(value=body.get("brand_voice_notes"), field_name="brand_voice_notes")
    compliance_notes = body.get("compliance_notes")
    if compliance_notes is not None and not isinstance(compliance_notes, str):
        raise HTTPException(status_code=400, detail="compliance_notes must be a string when provided.")
    copy_generation_mode_raw = body.get("copy_generation_mode")
    if copy_generation_mode_raw is not None and not isinstance(copy_generation_mode_raw, str):
        raise HTTPException(status_code=400, detail="copy_generation_mode must be a string when provided.")
    copy_generation_mode = copy_generation_mode_raw.strip().lower() if isinstance(copy_generation_mode_raw, str) else None
    if copy_generation_mode and copy_generation_mode not in {"full_markdown", "template_payload_only"}:
        raise HTTPException(
            status_code=400,
            detail="copy_generation_mode must be either 'full_markdown' or 'template_payload_only'.",
        )

    temporal = await get_temporal_client()
    handle = await temporal.start_workflow(
        StrategyV2Workflow.run,
        StrategyV2Input(
            org_id=auth.org_id,
            client_id=client_id,
            product_id=product_id,
            onboarding_payload_id=onboarding_payload_id.strip() if isinstance(onboarding_payload_id, str) else None,
            campaign_id=campaign_id.strip() if isinstance(campaign_id, str) else None,
            operator_user_id=auth.user_id,
            stage0_overrides=stage0_overrides,
            business_model=business_model,
            funnel_position=funnel_position,
            target_platforms=target_platforms,
            target_regions=target_regions,
            existing_proof_assets=existing_proof_assets,
            brand_voice_notes=brand_voice_notes,
            compliance_notes=compliance_notes.strip() if isinstance(compliance_notes, str) else None,
            copy_generation_mode=copy_generation_mode,
        ),
        id=f"strategy-v2-{auth.org_id}-{client_id}-{product_id}-{uuid4()}",
        task_queue=settings.TEMPORAL_TASK_QUEUE,
    )

    run = workflows_repo.create_run(
        org_id=auth.org_id,
        client_id=client_id,
        product_id=product_id,
        campaign_id=campaign_id.strip() if isinstance(campaign_id, str) else None,
        temporal_workflow_id=handle.id,
        temporal_run_id=handle.first_execution_run_id,
        kind=WorkflowKindEnum.strategy_v2.value,
    )
    workflows_repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2",
        status="started",
        payload_in={
            "client_id": client_id,
            "product_id": product_id,
            "campaign_id": campaign_id,
            "business_model": business_model,
            "funnel_position": funnel_position,
            "target_platforms": target_platforms,
            "target_regions": target_regions,
            "existing_proof_assets": existing_proof_assets,
            "copy_generation_mode": copy_generation_mode,
        },
    )
    return {"workflow_run_id": str(run.id), "temporal_workflow_id": handle.id}


@router.get("/{workflow_run_id}")
async def get_workflow_run(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    run = _resolve_workflow_run(
        repo=repo,
        org_id=auth.org_id,
        workflow_run_id_or_temporal_id=workflow_run_id,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    canonical_run_id = str(run.id)

    temporal_status = None
    strategy_v2_state: dict[str, Any] | None = None
    pending_activity_progress: list[dict[str, Any]] = []
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(
            run.temporal_workflow_id,
            first_execution_run_id=run.temporal_run_id,
        )
        desc = await handle.describe()
        temporal_status = desc.status.name if desc and getattr(desc, "status", None) else None
        pending_activity_progress = _extract_pending_activity_progress(desc)
        status_map = _workflow_status_map()
        new_status = status_map.get(getattr(desc, "status", None)) if desc else None
        finished_at = getattr(desc, "close_time", None)
        if new_status and (new_status != run.status or finished_at):
            repo.set_status(
                org_id=auth.org_id,
                workflow_run_id=canonical_run_id,
                status=new_status,
                finished_at=finished_at,
            )
            run = repo.get(org_id=auth.org_id, workflow_run_id=canonical_run_id) or run
        if run.kind == WorkflowKindEnum.strategy_v2:
            queried_state = await handle.query("strategy_v2_state")
            if isinstance(queried_state, dict):
                strategy_v2_state = queried_state
    except Exception:
        # If Temporal is unreachable, still return persisted data.
        pass

    logs = repo.list_logs(org_id=auth.org_id, workflow_run_id=canonical_run_id)

    artifacts_repo = ArtifactsRepository(session)
    client_canon = None
    metric_schema = None
    strategy_sheet = None
    if run.client_id and run.product_id:
        client_canon = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.client_canon,
            product_id=run.product_id,
        )
        metric_schema = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.metric_schema,
            product_id=run.product_id,
        )
    if run.campaign_id:
        strategy_sheet = artifacts_repo.get_latest_by_type_for_campaign(
            org_id=auth.org_id, campaign_id=run.campaign_id, artifact_type=ArtifactTypeEnum.strategy_sheet
        )
        experiment_specs = artifacts_repo.list(
            org_id=auth.org_id,
            campaign_id=run.campaign_id,
            artifact_type=ArtifactTypeEnum.experiment_spec,
            limit=50,
        )
        asset_briefs = artifacts_repo.list(
            org_id=auth.org_id,
            campaign_id=run.campaign_id,
            artifact_type=ArtifactTypeEnum.asset_brief,
            limit=50,
        )
    else:
        experiment_specs = []
        asset_briefs = []

    strategy_v2_stage3 = None
    strategy_v2_offer = None
    strategy_v2_copy = None
    strategy_v2_copy_canonical = None
    strategy_v2_copy_context = None
    strategy_v2_awareness_matrix = None
    if run.client_id and run.product_id:
        strategy_v2_stage3 = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_stage3,
            product_id=run.product_id,
        )
        strategy_v2_offer = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_offer,
            product_id=run.product_id,
        )
        strategy_v2_copy = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_copy,
            product_id=run.product_id,
        )
        strategy_v2_copy_canonical = _normalize_strategy_v2_copy_payload(strategy_v2_copy)
        strategy_v2_copy_context = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_copy_context,
            product_id=run.product_id,
        )
        strategy_v2_awareness_matrix = artifacts_repo.get_latest_by_type(
            org_id=auth.org_id,
            client_id=run.client_id,
            artifact_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
            product_id=run.product_id,
        )

    research_artifacts_repo = ResearchArtifactsRepository(session)
    research_artifacts_rows = research_artifacts_repo.list_for_workflow_run(
        org_id=auth.org_id,
        workflow_run_id=canonical_run_id,
    )
    research_artifacts = [
        {
            "step_key": row.step_key,
            "title": row.title,
            "doc_url": row.doc_url,
            "doc_id": row.doc_id,
            "summary": row.summary,
        }
        for row in research_artifacts_rows
    ]

    precanon_research = None
    research_highlights = None
    if client_canon and isinstance(client_canon.data, dict):
        precanon_research = client_canon.data.get("precanon_research")
        research_highlights = client_canon.data.get("research_highlights")

    if run.kind == WorkflowKindEnum.strategy_v2 and strategy_v2_state is None:
        strategy_v2_state = _strategy_v2_state_from_research_artifacts(
            session=session,
            org_id=auth.org_id,
            workflow_run_id=canonical_run_id,
            client_id=str(run.client_id) if run.client_id else None,
            product_id=str(run.product_id) if run.product_id else None,
        )
    if run.kind == WorkflowKindEnum.strategy_v2:
        strategy_v2_state = _normalize_strategy_v2_state_for_api(strategy_v2_state)
    if run.kind == WorkflowKindEnum.strategy_v2 and isinstance(strategy_v2_state, dict):
        strategy_v2_state["artifact_refs"] = _normalize_strategy_v2_artifact_refs(
            strategy_v2_state.get("artifact_refs")
        )

    strategy_v2_launches: list[dict[str, Any]] = []
    if run.kind == WorkflowKindEnum.strategy_v2:
        launches_repo = StrategyV2LaunchesRepository(session)
        launch_rows = launches_repo.list_for_source_run(
            org_id=auth.org_id,
            source_strategy_v2_workflow_run_id=canonical_run_id,
        )
        launch_status_by_run_id: dict[str, str | None] = {}
        for row in launch_rows:
            launch_run_id_raw = getattr(row, "launch_workflow_run_id", None)
            if launch_run_id_raw is None:
                continue
            launch_run_id = str(launch_run_id_raw)
            if launch_run_id in launch_status_by_run_id:
                continue
            linked_run = repo.get(org_id=auth.org_id, workflow_run_id=launch_run_id)
            launch_status_by_run_id[launch_run_id] = linked_run.status.value if linked_run else None
        strategy_v2_launches = []
        for row in launch_rows:
            launch_run_id_raw = getattr(row, "launch_workflow_run_id", None)
            launch_status = (
                launch_status_by_run_id.get(str(launch_run_id_raw))
                if launch_run_id_raw is not None
                else None
            )
            strategy_v2_launches.append(
                _strategy_v2_launch_record_to_payload(row, launch_status=launch_status)
            )

    return jsonable_encoder(
        {
            "run": run,
            "logs": logs,
            "client_canon": client_canon,
            "metric_schema": metric_schema,
            "strategy_sheet": strategy_sheet,
            "experiment_specs": experiment_specs,
            "asset_briefs": asset_briefs,
            "precanon_research": precanon_research,
            "research_artifacts": research_artifacts,
            "research_highlights": research_highlights,
            "temporal_status": temporal_status,
            "pending_activity_progress": pending_activity_progress,
            "strategy_v2_state": strategy_v2_state,
            "strategy_v2_stage3": strategy_v2_stage3,
            "strategy_v2_offer": strategy_v2_offer,
            "strategy_v2_copy": strategy_v2_copy,
            "strategy_v2_copy_canonical": strategy_v2_copy_canonical,
            "strategy_v2_copy_context": strategy_v2_copy_context,
            "strategy_v2_awareness_angle_matrix": strategy_v2_awareness_matrix,
            "strategy_v2_launches": strategy_v2_launches,
        }
    )


@router.get("/{workflow_run_id}/research/{step_key}")
def get_workflow_research_artifact(
    workflow_run_id: str,
    step_key: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Return the *full* research artifact content for a given workflow + step.

    The workflow detail endpoint returns only lightweight research artifact refs + summaries.
    Full text is retrieved from the persisted Drive file on-demand so the UI can render the
    complete document even while a workflow is still running (before client canon exists).
    """
    repo = WorkflowsRepository(session)
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    research_repo = ResearchArtifactsRepository(session)
    record = research_repo.get_for_step(org_id=auth.org_id, workflow_run_id=str(run.id), step_key=step_key)
    if not record:
        raise HTTPException(status_code=404, detail="Research artifact not found for this step")

    doc_url = getattr(record, "doc_url", None) or ""
    doc_id = getattr(record, "doc_id", None) or ""
    if not doc_id:
        raise HTTPException(status_code=500, detail="Research artifact is missing a doc_id")

    if isinstance(doc_url, str) and doc_url.startswith("artifact://"):
        artifact_id = doc_url.split("artifact://", 1)[1].strip() or doc_id
        artifact = ArtifactsRepository(session).get(org_id=auth.org_id, artifact_id=artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Referenced artifact record was not found.")
        return jsonable_encoder(
            {
                "step_key": record.step_key,
                "title": record.title,
                "doc_url": record.doc_url,
                "doc_id": record.doc_id,
                "summary": record.summary,
                "content": artifact.data,
            }
        )

    if isinstance(doc_url, str) and doc_url.startswith("drive-stub://"):
        raise HTTPException(
            status_code=409,
            detail="Research artifact was persisted with a Drive stub; full content is unavailable.",
        )

    try:
        content = download_drive_text_file(file_id=doc_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return jsonable_encoder(
        {
            "step_key": record.step_key,
            "title": record.title,
            "doc_url": record.doc_url,
            "doc_id": record.doc_id,
            "summary": record.summary,
            "content": content,
        }
    )


async def _get_handle(session: Session, auth: AuthContext, workflow_run_id: str):
    repo = WorkflowsRepository(session)
    run = _resolve_workflow_run(
        repo=repo,
        org_id=auth.org_id,
        workflow_run_id_or_temporal_id=workflow_run_id,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    client = await get_temporal_client()
    return repo, run, client.get_workflow_handle(
        run.temporal_workflow_id,
        first_execution_run_id=run.temporal_run_id,
    )


@router.post("/{workflow_run_id}/signals/approve-canon")
async def approve_canon(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Canon approval has been removed. Client onboarding is auto-approved and no longer waits for canon approval.",
    )


@router.post("/{workflow_run_id}/signals/approve-metric-schema")
async def approve_metric_schema(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Metric schema approval has been removed. Client onboarding is auto-approved and no longer waits for metric schema approval.",
    )


@router.post("/{workflow_run_id}/signals/approve-strategy")
async def approve_strategy(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    raise HTTPException(
        status_code=410,
        detail="Strategy approval has been removed. Campaign planning and campaign intent now auto-approve the strategy sheet and wait for experiment approvals instead.",
    )


@router.post("/{workflow_run_id}/signals/approve-experiments")
async def approve_experiments(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_experiments",
        {
            "approved_ids": body.get("approved_ids", []),
            "rejected_ids": body.get("rejected_ids", []),
            "edited_specs": body.get("edited_specs"),
        },
    )
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="approve_experiments",
        status="sent",
        payload_in={
            "approved_ids": body.get("approved_ids", []),
            "rejected_ids": body.get("rejected_ids", []),
        },
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-asset-briefs")
async def approve_asset_briefs(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    approved_ids = body.get("approved_ids", [])
    if not isinstance(approved_ids, list):
        raise HTTPException(status_code=400, detail="approved_ids must be a list.")

    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("approve_asset_briefs", {"approved_ids": approved_ids})
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="approve_asset_briefs",
        status="sent",
        payload_in={"approved_ids": approved_ids},
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/approve-assets")
async def approve_assets(
    workflow_run_id: str,
    body: dict,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    approved_ids = body.get("approved_ids", [])
    rejected_ids = body.get("rejected_ids", [])
    if not isinstance(approved_ids, list) or not isinstance(rejected_ids, list):
        raise HTTPException(status_code=400, detail="approved_ids and rejected_ids must be lists.")
    approved_set = {str(asset_id) for asset_id in approved_ids}
    rejected_set = {str(asset_id) for asset_id in rejected_ids}
    overlap = approved_set.intersection(rejected_set)
    if overlap:
        raise HTTPException(status_code=400, detail="Assets cannot be both approved and rejected.")

    all_ids = approved_set.union(rejected_set)
    if all_ids:
        existing_ids = session.scalars(
            select(Asset.id).where(Asset.org_id == auth.org_id, Asset.id.in_(list(all_ids)))
        ).all()
        existing_set = {str(asset_id) for asset_id in existing_ids}
        missing = all_ids.difference(existing_set)
        if missing:
            raise HTTPException(
                status_code=404,
                detail={"message": "Some assets were not found.", "missingAssetIds": sorted(missing)},
            )
        if approved_set:
            session.execute(
                update(Asset)
                .where(Asset.org_id == auth.org_id, Asset.id.in_(list(approved_set)))
                .values(status=AssetStatusEnum.approved)
            )
        if rejected_set:
            session.execute(
                update(Asset)
                .where(Asset.org_id == auth.org_id, Asset.id.in_(list(rejected_set)))
                .values(status=AssetStatusEnum.rejected)
            )
        session.commit()

    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal(
        "approve_assets",
        {"approved_ids": approved_ids, "rejected_ids": rejected_ids},
    )
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="approve_assets",
        status="sent",
        payload_in={
            "approved_ids": approved_ids,
            "rejected_ids": rejected_ids,
        },
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/select-angle")
async def strategy_v2_select_angle(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = AngleSelectionDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_select_angle", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_select_angle",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/proceed-research")
async def strategy_v2_proceed_research(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = ResearchProceedDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_proceed_research", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_proceed_research",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/confirm-competitor-assets")
async def strategy_v2_confirm_competitor_assets(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = CompetitorAssetConfirmationDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_confirm_competitor_assets", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_confirm_competitor_assets",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/select-ump-ums")
async def strategy_v2_select_ump_ums(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = UmpUmsSelectionDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_select_ump_ums", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_select_ump_ums",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/select-offer-winner")
async def strategy_v2_select_offer_winner(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = OfferWinnerSelectionDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_select_offer_winner", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_select_offer_winner",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post("/{workflow_run_id}/signals/strategy-v2/approve-final-copy")
async def strategy_v2_approve_final_copy(
    workflow_run_id: str,
    body: dict[str, Any],
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    if run.kind != WorkflowKindEnum.strategy_v2:
        raise HTTPException(status_code=409, detail="Workflow is not a Strategy V2 run.")
    try:
        decision = FinalCopyApprovalDecision.model_validate(
            _prepare_strategy_v2_decision_payload(body=body, auth=auth)
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = decision.model_dump(mode="python")
    await handle.signal("strategy_v2_approve_final_copy", payload)
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="strategy_v2_approve_final_copy",
        status="sent",
        payload_in=payload,
    )
    return {"ok": True}


@router.post(
    "/{workflow_run_id}/actions/strategy-v2/launch-angle-campaign",
    response_model=StrategyV2LaunchActionResponse,
)
async def strategy_v2_launch_angle_campaign(
    workflow_run_id: str,
    body: StrategyV2LaunchAngleCampaignRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    source_run = _resolve_workflow_run(
        repo=repo,
        org_id=auth.org_id,
        workflow_run_id_or_temporal_id=workflow_run_id,
    )
    if not source_run:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    source_context = _load_source_context_or_409(session=session, org_id=auth.org_id, source_run=source_run)
    effective_source_run = getattr(source_context, "source_run", source_run)

    channels = _normalize_required_string_list(value=body.channels, field_name="channels")
    asset_brief_types = _normalize_required_string_list(
        value=body.asset_brief_types,
        field_name="assetBriefTypes",
    )
    experiment_variant_policy = body.experiment_variant_policy.strip()
    launches_repo = StrategyV2LaunchesRepository(session)
    launch_index = _launch_index_for_angle(
        launches_repo=launches_repo,
        org_id=auth.org_id,
        client_id=str(effective_source_run.client_id),
        product_id=str(effective_source_run.product_id),
        angle_id=source_context.selected_angle_id,
        angle_id_counts={},
    )
    campaign_name = build_angle_campaign_name(
        angle_id=source_context.selected_angle_id,
        angle_name=source_context.selected_angle_name,
        launch_index=launch_index,
    )
    selected_ums_id_raw = source_context.source_stage3.get("ums")
    selected_ums_id = selected_ums_id_raw.strip() if isinstance(selected_ums_id_raw, str) and selected_ums_id_raw.strip() else None
    selected_variant_id_raw = source_context.source_stage3.get("variant_selected")
    selected_variant_id = (
        selected_variant_id_raw.strip()
        if isinstance(selected_variant_id_raw, str) and selected_variant_id_raw.strip()
        else None
    )
    launch_key = build_launch_key(
        source_strategy_v2_workflow_run_id=str(effective_source_run.id),
        launch_type="initial_angle",
        angle_id=source_context.selected_angle_id,
        campaign_id=None,
        selected_ums_id=selected_ums_id,
        channels=channels,
        asset_brief_types=asset_brief_types,
        experiment_variant_policy=experiment_variant_policy,
    )
    existing = launches_repo.get_by_launch_key(org_id=auth.org_id, launch_key=launch_key)
    if existing:
        try:
            return _idempotent_launch_response_from_rows([existing])
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    temporal = await get_temporal_client()
    temporal_workflow_id = _build_deterministic_launch_temporal_workflow_id(
        prefix="strategy-v2-angle-launch",
        org_id=auth.org_id,
        source_run_id=str(effective_source_run.id),
        launch_keys=[launch_key],
    )
    launch_run = WorkflowRun(
        org_id=auth.org_id,
        client_id=str(effective_source_run.client_id),
        product_id=str(effective_source_run.product_id),
        campaign_id=None,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind=WorkflowKindEnum.strategy_v2_angle_launch,
    )
    session.add(launch_run)
    session.commit()
    session.refresh(launch_run)
    launch_items = [
        {
            "launch_type": "initial_angle",
            "launch_key": launch_key,
            "campaign_name": campaign_name,
            "launch_index": launch_index,
            "angle": source_context.selected_angle,
            "angle_run_id": source_context.angle_run_id,
            "selected_ums_id": selected_ums_id,
            "selected_variant_id": selected_variant_id,
            "strategy_v2_packet": source_context.source_downstream_packet,
            "strategy_v2_copy_context": source_context.source_copy_context,
            "source_stage3_artifact_id": source_context.source_stage3_artifact_id,
            "source_offer_artifact_id": source_context.source_offer_artifact_id,
            "source_copy_artifact_id": source_context.source_copy_artifact_id,
            "source_copy_context_artifact_id": source_context.source_copy_context_artifact_id,
        }
    ]
    try:
        handle = await temporal.start_workflow(
            StrategyV2AngleCampaignLaunchWorkflow.run,
            StrategyV2AngleCampaignLaunchInput(
                org_id=auth.org_id,
                client_id=str(effective_source_run.client_id),
                product_id=str(effective_source_run.product_id),
                source_strategy_v2_workflow_run_id=str(effective_source_run.id),
                source_strategy_v2_temporal_workflow_id=source_context.source_temporal_workflow_id,
                launch_workflow_run_id=str(launch_run.id),
                operator_user_id=auth.user_id,
                channels=channels,
                asset_brief_types=asset_brief_types,
                experiment_variant_policy=experiment_variant_policy,
                launch_items=launch_items,
            ),
            id=temporal_workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "A Strategy V2 angle launch is already running for this launch key set. "
                "Wait for the existing launch workflow to finish."
            ),
        ) from exc
    except Exception as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=502,
            detail="Failed to start Strategy V2 angle launch workflow.",
        ) from exc

    launch_run.temporal_run_id = handle.first_execution_run_id
    session.commit()
    session.refresh(launch_run)

    repo.log_activity(
        workflow_run_id=str(launch_run.id),
        step="strategy_v2_angle_launch",
        status="started",
        payload_in={
            "source_strategy_v2_workflow_run_id": str(effective_source_run.id),
            "source_strategy_v2_temporal_workflow_id": source_context.source_temporal_workflow_id,
            "channels": channels,
            "asset_brief_types": asset_brief_types,
            "experiment_variant_policy": experiment_variant_policy,
            "naming_policy": "angle_standard_v1",
            "launch_keys": [launch_key],
        },
    )
    return _compose_launch_action_response(
        run_id=str(launch_run.id),
        temporal_workflow_id=handle.id,
        launch_records=[],
    )


@router.post(
    "/{workflow_run_id}/actions/strategy-v2/launch-additional-ums",
    response_model=StrategyV2LaunchActionResponse,
)
async def strategy_v2_launch_additional_ums(
    workflow_run_id: str,
    body: StrategyV2LaunchAdditionalUmsRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    source_run = _resolve_workflow_run(
        repo=repo,
        org_id=auth.org_id,
        workflow_run_id_or_temporal_id=workflow_run_id,
    )
    if not source_run:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    source_context = _load_source_context_or_409(session=session, org_id=auth.org_id, source_run=source_run)
    effective_source_run = getattr(source_context, "source_run", source_run)

    campaign = CampaignsRepository(session).get(org_id=auth.org_id, campaign_id=body.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if str(campaign.client_id) != str(effective_source_run.client_id) or str(campaign.product_id) != str(effective_source_run.product_id):
        raise HTTPException(
            status_code=409,
            detail="Campaign does not match source Strategy V2 client/product scope.",
        )

    channels = (
        _normalize_required_string_list(value=body.channels, field_name="channels")
        if body.channels is not None
        else _normalize_required_string_list(value=list(campaign.channels or []), field_name="campaign.channels")
    )
    asset_brief_types = (
        _normalize_required_string_list(value=body.asset_brief_types, field_name="assetBriefTypes")
        if body.asset_brief_types is not None
        else _normalize_required_string_list(
            value=list(campaign.asset_brief_types or []),
            field_name="campaign.asset_brief_types",
        )
    )
    ums_selection_ids = _normalize_required_string_list(value=body.ums_selection_ids, field_name="umsSelectionIds")
    launch_name_prefix = body.launch_name_prefix.strip()

    ums_lookup = resolve_ums_selection_map(source_context.offer_pipeline_payload)
    launches_repo = StrategyV2LaunchesRepository(session)
    launch_rows_by_key: list[Any] = []
    launch_items: list[dict[str, Any]] = []

    for selected_ums_id in ums_selection_ids:
        pair = ums_lookup.get(selected_ums_id)
        if pair is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invalid UMS selection '{selected_ums_id}'. "
                    "Remediation: choose ids from v2-08 pair_scoring ranked_pairs."
                ),
            )
        selected_ums_id_from_pair = pair.get("ums_id")
        canonical_selected_ums_id = (
            selected_ums_id_from_pair.strip()
            if isinstance(selected_ums_id_from_pair, str) and selected_ums_id_from_pair.strip()
            else selected_ums_id
        )
        launch_key = build_launch_key(
            source_strategy_v2_workflow_run_id=str(effective_source_run.id),
            launch_type="additional_ums",
            angle_id=source_context.selected_angle_id,
            campaign_id=str(campaign.id),
            selected_ums_id=canonical_selected_ums_id,
            channels=channels,
            asset_brief_types=asset_brief_types,
            experiment_variant_policy="ums_iteration_standard_v1",
        )
        existing_by_key = launches_repo.get_by_launch_key(org_id=auth.org_id, launch_key=launch_key)
        if existing_by_key:
            launch_rows_by_key.append(existing_by_key)
            continue
        existing_by_angle_ums = launches_repo.get_by_angle_run_and_ums(
            org_id=auth.org_id,
            angle_run_id=source_context.angle_run_id,
            selected_ums_id=canonical_selected_ums_id,
        )
        if existing_by_angle_ums:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"UMS selection '{canonical_selected_ums_id}' already launched for angle_run_id '{source_context.angle_run_id}'. "
                    "Use launch history to inspect prior outputs."
                ),
            )
        launch_items.append(
            {
                "selected_ums_id": canonical_selected_ums_id,
                "pair": pair,
                "launch_key": launch_key,
            }
        )

    if launch_rows_by_key and not launch_items:
        try:
            return _idempotent_launch_response_from_rows(launch_rows_by_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    temporal = await get_temporal_client()
    launch_keys = [str(item.get("launch_key", "")).strip() for item in launch_items if str(item.get("launch_key", "")).strip()]
    temporal_workflow_id = _build_deterministic_launch_temporal_workflow_id(
        prefix="strategy-v2-angle-iteration",
        org_id=auth.org_id,
        source_run_id=str(effective_source_run.id),
        launch_keys=launch_keys,
    )
    launch_run = WorkflowRun(
        org_id=auth.org_id,
        client_id=str(effective_source_run.client_id),
        product_id=str(effective_source_run.product_id),
        campaign_id=str(campaign.id),
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind=WorkflowKindEnum.strategy_v2_angle_iteration,
    )
    session.add(launch_run)
    session.commit()
    session.refresh(launch_run)

    try:
        handle = await temporal.start_workflow(
            StrategyV2AngleIterationWorkflow.run,
            StrategyV2AngleIterationInput(
                org_id=auth.org_id,
                client_id=str(effective_source_run.client_id),
                product_id=str(effective_source_run.product_id),
                source_strategy_v2_workflow_run_id=str(effective_source_run.id),
                source_strategy_v2_temporal_workflow_id=source_context.source_temporal_workflow_id,
                launch_workflow_run_id=str(launch_run.id),
                operator_user_id=auth.user_id,
                campaign_id=str(campaign.id),
                channels=channels,
                asset_brief_types=asset_brief_types,
                launch_name_prefix=launch_name_prefix,
                experiment_variant_policy="ums_iteration_standard_v1",
                base_angle_run_id=source_context.angle_run_id,
                selected_angle=source_context.selected_angle,
                stage1=source_context.stage1,
                ranked_angle_candidates=source_context.ranked_angle_candidates,
                offer_pipeline_payload=source_context.offer_pipeline_payload,
                offer_operator_inputs=source_context.offer_operator_inputs,
                angle_synthesis_payload=source_context.angle_synthesis_payload,
                onboarding_payload_id=source_context.offer_winner_onboarding_payload_id,
                ums_launch_items=launch_items,
            ),
            id=temporal_workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "A Strategy V2 additional UMS launch is already running for this launch key set. "
                "Wait for the existing launch workflow to finish."
            ),
        ) from exc
    except Exception as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=502,
            detail="Failed to start Strategy V2 additional UMS launch workflow.",
        ) from exc

    launch_run.temporal_run_id = handle.first_execution_run_id
    session.commit()
    session.refresh(launch_run)

    repo.log_activity(
        workflow_run_id=str(launch_run.id),
        step="strategy_v2_angle_iteration",
        status="started",
        payload_in={
            "source_strategy_v2_workflow_run_id": str(effective_source_run.id),
            "campaign_id": str(campaign.id),
            "ums_selection_ids": ums_selection_ids,
            "launch_name_prefix": launch_name_prefix,
            "channels": channels,
            "asset_brief_types": asset_brief_types,
            "experiment_variant_policy": "ums_iteration_standard_v1",
            "launch_keys": launch_keys,
        },
    )
    return _compose_launch_action_response(
        run_id=str(launch_run.id),
        temporal_workflow_id=handle.id,
        launch_records=[],
    )


@router.post(
    "/{workflow_run_id}/actions/strategy-v2/launch-additional-angle",
    response_model=StrategyV2LaunchActionResponse,
)
async def strategy_v2_launch_additional_angle(
    workflow_run_id: str,
    body: StrategyV2LaunchAdditionalAngleRequest,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    source_run = _resolve_workflow_run(
        repo=repo,
        org_id=auth.org_id,
        workflow_run_id_or_temporal_id=workflow_run_id,
    )
    if not source_run:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    source_context = _load_source_context_or_409(session=session, org_id=auth.org_id, source_run=source_run)
    effective_source_run = getattr(source_context, "source_run", source_run)
    if source_context.competitor_analysis is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Source run is missing pinned competitor_analysis for additional-angle launch replay. "
                "Remediation: rerun source Strategy V2 with foundational competitor analysis persistence."
            ),
        )
    if not source_context.voc_observations or not source_context.voc_scored:
        raise HTTPException(
            status_code=409,
            detail=(
                "Source run is missing VOC payload required for additional-angle launch replay "
                "(expected from v2-05 or v2-06 fallback payload)."
            ),
        )

    channels = _normalize_required_string_list(value=body.channels, field_name="channels")
    asset_brief_types = _normalize_required_string_list(value=body.asset_brief_types, field_name="assetBriefTypes")
    selected_angle_ids = _normalize_required_string_list(value=body.selected_angle_ids, field_name="selectedAngleIds")
    eligible_angle_ids = list_ranked_angle_ids(source_context.ranked_angle_candidates)
    invalid_angles = sorted(set(selected_angle_ids) - eligible_angle_ids)
    if invalid_angles:
        raise HTTPException(
            status_code=409,
            detail=(
                "Invalid additional angle selection. "
                f"Selected IDs were not present in reviewed v2-06 candidates: {invalid_angles}"
            ),
        )

    launches_repo = StrategyV2LaunchesRepository(session)
    launch_rows_by_key: list[Any] = []
    launch_items: list[dict[str, Any]] = []
    angle_counts: dict[str, int] = {}

    for angle_id in selected_angle_ids:
        angle_payload = find_ranked_angle_payload(
            ranked_candidates=source_context.ranked_angle_candidates,
            angle_id=angle_id,
        )
        if angle_payload is None:
            raise HTTPException(
                status_code=409,
                detail=f"Missing angle payload for selected angle_id '{angle_id}'.",
            )
        angle_name = _require_nonempty_string(
            value=angle_payload.get("angle_name"),
            field_name="selected_angle.angle_name",
        )
        launch_index = _launch_index_for_angle(
            launches_repo=launches_repo,
            org_id=auth.org_id,
            client_id=str(effective_source_run.client_id),
            product_id=str(effective_source_run.product_id),
            angle_id=angle_id,
            angle_id_counts=angle_counts,
        )
        campaign_name = build_angle_campaign_name(
            angle_id=angle_id,
            angle_name=angle_name,
            launch_index=launch_index,
        )
        launch_key = build_launch_key(
            source_strategy_v2_workflow_run_id=str(effective_source_run.id),
            launch_type="additional_angle",
            angle_id=angle_id,
            campaign_id=None,
            selected_ums_id=None,
            channels=channels,
            asset_brief_types=asset_brief_types,
            experiment_variant_policy="angle_branch_standard_v1",
        )
        existing = launches_repo.get_by_launch_key(org_id=auth.org_id, launch_key=launch_key)
        if existing:
            launch_rows_by_key.append(existing)
            continue
        launch_items.append(
            {
                "launch_type": "additional_angle",
                "launch_key": launch_key,
                "campaign_name": campaign_name,
                "launch_index": launch_index,
                "angle": angle_payload,
            }
        )

    if launch_rows_by_key and not launch_items:
        try:
            return _idempotent_launch_response_from_rows(launch_rows_by_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    temporal = await get_temporal_client()
    launch_keys = [str(item.get("launch_key", "")).strip() for item in launch_items if str(item.get("launch_key", "")).strip()]
    temporal_workflow_id = _build_deterministic_launch_temporal_workflow_id(
        prefix="strategy-v2-angle-launch",
        org_id=auth.org_id,
        source_run_id=str(effective_source_run.id),
        launch_keys=launch_keys,
    )
    launch_run = WorkflowRun(
        org_id=auth.org_id,
        client_id=str(effective_source_run.client_id),
        product_id=str(effective_source_run.product_id),
        campaign_id=None,
        temporal_workflow_id=temporal_workflow_id,
        temporal_run_id="pending",
        kind=WorkflowKindEnum.strategy_v2_angle_launch,
    )
    session.add(launch_run)
    session.commit()
    session.refresh(launch_run)

    try:
        handle = await temporal.start_workflow(
            StrategyV2AngleCampaignLaunchWorkflow.run,
            StrategyV2AngleCampaignLaunchInput(
                org_id=auth.org_id,
                client_id=str(effective_source_run.client_id),
                product_id=str(effective_source_run.product_id),
                source_strategy_v2_workflow_run_id=str(effective_source_run.id),
                source_strategy_v2_temporal_workflow_id=source_context.source_temporal_workflow_id,
                launch_workflow_run_id=str(launch_run.id),
                operator_user_id=auth.user_id,
                channels=channels,
                asset_brief_types=asset_brief_types,
                experiment_variant_policy="angle_branch_standard_v1",
                launch_items=launch_items,
                stage1=source_context.stage1,
                ranked_angle_candidates=source_context.ranked_angle_candidates,
                competitor_analysis=source_context.competitor_analysis,
                voc_scored=source_context.voc_scored,
                voc_observations=source_context.voc_observations,
                proof_asset_candidates=source_context.proof_asset_candidates,
                angle_synthesis_payload=source_context.angle_synthesis_payload,
                offer_operator_inputs=source_context.offer_operator_inputs,
                onboarding_payload_id=source_context.offer_winner_onboarding_payload_id,
            ),
            id=temporal_workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except WorkflowAlreadyStartedError as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "A Strategy V2 additional-angle launch is already running for this launch key set. "
                "Wait for the existing launch workflow to finish."
            ),
        ) from exc
    except Exception as exc:
        session.delete(launch_run)
        session.commit()
        raise HTTPException(
            status_code=502,
            detail="Failed to start Strategy V2 additional-angle launch workflow.",
        ) from exc

    launch_run.temporal_run_id = handle.first_execution_run_id
    session.commit()
    session.refresh(launch_run)

    repo.log_activity(
        workflow_run_id=str(launch_run.id),
        step="strategy_v2_angle_launch",
        status="started",
        payload_in={
            "source_strategy_v2_workflow_run_id": str(effective_source_run.id),
            "selected_angle_ids": selected_angle_ids,
            "channels": channels,
            "asset_brief_types": asset_brief_types,
            "experiment_variant_policy": "angle_branch_standard_v1",
            "naming_policy": "angle_standard_v1",
            "launch_keys": launch_keys,
        },
    )
    return _compose_launch_action_response(
        run_id=str(launch_run.id),
        temporal_workflow_id=handle.id,
        launch_records=[],
    )


@router.post("/{workflow_run_id}/signals/stop")
async def stop_workflow(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo, run, handle = await _get_handle(session, auth, workflow_run_id)
    await handle.signal("stop")
    repo.log_activity(
        workflow_run_id=str(run.id),
        step="stop",
        status="sent",
        payload_in={},
    )
    return {"ok": True}


@router.get("/{workflow_run_id}/logs")
def get_workflow_logs(
    workflow_run_id: str,
    auth: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    repo = WorkflowsRepository(session)
    run = None
    parsed_run_id = _maybe_uuid(workflow_run_id)
    if parsed_run_id:
        run = repo.get(org_id=auth.org_id, workflow_run_id=str(parsed_run_id))
    if not run:
        run = repo.get_by_temporal_workflow_id(org_id=auth.org_id, temporal_workflow_id=workflow_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    logs = repo.list_logs(org_id=auth.org_id, workflow_run_id=str(run.id))
    return jsonable_encoder(logs)
