from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.enums import ArtifactTypeEnum, WorkflowKindEnum, WorkflowStatusEnum
from app.db.models import WorkflowRun
from app.db.repositories.artifacts import ArtifactsRepository
from app.db.repositories.research_artifacts import ResearchArtifactsRepository
from app.strategy_v2.contracts import ProductBriefStage1
from app.strategy_v2.downstream import build_strategy_v2_downstream_packet, normalize_strategy_v2_copy_payload

_REQUIRED_TEMPLATE_IDS = ("pre-sales-listicle", "sales-pdp")
_REQUIRED_LAUNCH_STEP_KEYS = ("v2-06", "v2-08", "v2-09", "v2-11")


@dataclass
class StrategyV2StepPayloadRecord:
    step_key: str
    artifact_id: str
    payload: dict[str, Any]


@dataclass
class StrategyV2SourceContext:
    source_run: WorkflowRun
    source_temporal_workflow_id: str
    selected_angle: dict[str, Any]
    selected_angle_id: str
    selected_angle_name: str
    angle_run_id: str
    stage1: dict[str, Any]
    ranked_angle_candidates: list[dict[str, Any]]
    angle_synthesis_payload: dict[str, Any]
    competitor_analysis: dict[str, Any] | None
    voc_observations: list[dict[str, Any]]
    voc_scored: dict[str, Any]
    proof_asset_candidates: list[dict[str, Any]]
    offer_pipeline_payload: dict[str, Any]
    source_stage3: dict[str, Any]
    source_offer: dict[str, Any]
    source_copy: dict[str, Any]
    source_copy_context: dict[str, Any]
    source_downstream_packet: dict[str, Any]
    source_stage3_artifact_id: str
    source_offer_artifact_id: str
    source_copy_artifact_id: str
    source_copy_context_artifact_id: str
    source_awareness_matrix_artifact_id: str | None
    offer_operator_inputs: dict[str, Any]
    offer_winner_onboarding_payload_id: str | None
    step_payloads: dict[str, StrategyV2StepPayloadRecord]


def _require_nonempty_str(value: Any, *, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuntimeError(f"{field_name} is required.")


def _require_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise RuntimeError(f"{field_name} must be an object.")


def _require_list(value: Any, *, field_name: str) -> list[Any]:
    if isinstance(value, list):
        return value
    raise RuntimeError(f"{field_name} must be an array.")


def _load_step_payload_records(
    *,
    session: Session,
    org_id: str,
    workflow_run_id: str,
) -> dict[str, StrategyV2StepPayloadRecord]:
    research_repo = ResearchArtifactsRepository(session)
    artifacts_repo = ArtifactsRepository(session)
    records: dict[str, StrategyV2StepPayloadRecord] = {}
    for row in research_repo.list_for_workflow_run(org_id=org_id, workflow_run_id=workflow_run_id):
        step_key = str(getattr(row, "step_key", "") or "").strip()
        artifact_id = str(getattr(row, "doc_id", "") or "").strip()
        if not step_key or not artifact_id:
            continue
        artifact = artifacts_repo.get(org_id=org_id, artifact_id=artifact_id)
        if not artifact:
            continue
        if artifact.type != ArtifactTypeEnum.strategy_v2_step_payload:
            continue
        if not isinstance(artifact.data, dict):
            continue
        payload = artifact.data.get("payload")
        if not isinstance(payload, dict):
            continue
        records[step_key] = StrategyV2StepPayloadRecord(
            step_key=step_key,
            artifact_id=artifact_id,
            payload=payload,
        )
    return records


def _require_step_payload(
    *,
    step_payloads: dict[str, StrategyV2StepPayloadRecord],
    step_key: str,
) -> StrategyV2StepPayloadRecord:
    record = step_payloads.get(step_key)
    if record is None:
        raise RuntimeError(
            f"Missing required Strategy V2 step payload '{step_key}'. "
            "Remediation: rerun Strategy V2 and complete all required checkpoints."
        )
    return record


def _missing_required_launch_step_keys(
    *,
    step_payloads: dict[str, StrategyV2StepPayloadRecord],
) -> list[str]:
    return [step_key for step_key in _REQUIRED_LAUNCH_STEP_KEYS if step_key not in step_payloads]


def _find_alternate_completed_run_with_required_payloads(
    *,
    session: Session,
    org_id: str,
    source_run: WorkflowRun,
) -> str | None:
    temporal_workflow_id = str(source_run.temporal_workflow_id or "").strip()
    if not temporal_workflow_id:
        return None
    if not source_run.client_id or not source_run.product_id:
        return None

    stmt = (
        select(WorkflowRun)
        .where(
            WorkflowRun.org_id == org_id,
            WorkflowRun.kind == WorkflowKindEnum.strategy_v2,
            WorkflowRun.status == WorkflowStatusEnum.completed,
            WorkflowRun.temporal_workflow_id == temporal_workflow_id,
            WorkflowRun.client_id == source_run.client_id,
            WorkflowRun.product_id == source_run.product_id,
            WorkflowRun.id != source_run.id,
        )
        .order_by(desc(WorkflowRun.started_at))
    )
    for candidate in session.scalars(stmt).all():
        candidate_step_payloads = _load_step_payload_records(
            session=session,
            org_id=org_id,
            workflow_run_id=str(candidate.id),
        )
        if not _missing_required_launch_step_keys(step_payloads=candidate_step_payloads):
            return str(candidate.id)
    return None


def _load_artifact_payload(
    *,
    session: Session,
    org_id: str,
    artifact_id: str,
    expected_type: ArtifactTypeEnum,
    field_name: str,
) -> dict[str, Any]:
    artifact = ArtifactsRepository(session).get(org_id=org_id, artifact_id=artifact_id)
    if not artifact:
        raise RuntimeError(f"{field_name} not found: {artifact_id}")
    if artifact.type != expected_type:
        raise RuntimeError(
            f"{field_name} type mismatch for artifact {artifact_id}. "
            f"Expected {expected_type.value}, received {artifact.type.value}."
        )
    if not isinstance(artifact.data, dict):
        raise RuntimeError(f"{field_name} payload is invalid for artifact {artifact_id}.")
    return artifact.data


def _extract_competitor_analysis_from_foundation(step_payloads: dict[str, StrategyV2StepPayloadRecord]) -> dict[str, Any] | None:
    foundation_keys = (
        "v2-02.foundation.02",
        "v2-02.foundation.2",
        "v2-02.foundation.02 ",
    )
    for key in foundation_keys:
        record = step_payloads.get(key)
        if record is None:
            continue
        content = record.payload.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Foundational competitor analysis payload is not valid JSON. "
                "Remediation: rerun foundational step 02 with valid serialized competitor analysis."
            ) from exc
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_offer_operator_inputs(offer_pipeline_payload: dict[str, Any]) -> dict[str, Any]:
    offer_input = _require_dict(
        offer_pipeline_payload.get("offer_input"),
        field_name="v2-08.offer_input",
    )
    product_brief = _require_dict(
        offer_input.get("product_brief"),
        field_name="v2-08.offer_input.product_brief",
    )
    constraints = _require_dict(
        product_brief.get("constraints"),
        field_name="v2-08.offer_input.product_brief.constraints",
    )
    target_platforms_raw = _require_list(product_brief.get("target_platforms"), field_name="target_platforms")
    target_regions_raw = _require_list(product_brief.get("target_regions"), field_name="target_regions")
    existing_proof_assets_raw = _require_list(
        constraints.get("existing_proof_assets"),
        field_name="existing_proof_assets",
    )

    target_platforms = [str(item).strip() for item in target_platforms_raw if isinstance(item, str) and item.strip()]
    target_regions = [str(item).strip() for item in target_regions_raw if isinstance(item, str) and item.strip()]
    existing_proof_assets = [
        str(item).strip() for item in existing_proof_assets_raw if isinstance(item, str) and item.strip()
    ]
    if not target_platforms:
        raise RuntimeError("v2-08 target_platforms is empty.")
    if not target_regions:
        raise RuntimeError("v2-08 target_regions is empty.")
    if not existing_proof_assets:
        raise RuntimeError("v2-08 existing_proof_assets is empty.")

    return {
        "business_model": _require_nonempty_str(product_brief.get("business_model"), field_name="business_model"),
        "funnel_position": _require_nonempty_str(product_brief.get("funnel_position"), field_name="funnel_position"),
        "target_platforms": target_platforms,
        "target_regions": target_regions,
        "existing_proof_assets": existing_proof_assets,
        "brand_voice_notes": _require_nonempty_str(
            constraints.get("brand_voice_notes"),
            field_name="brand_voice_notes",
        ),
    }


def _extract_offer_winner_onboarding_payload_id(v2_09_payload: dict[str, Any]) -> str | None:
    decision = v2_09_payload.get("decision")
    if not isinstance(decision, dict):
        return None
    raw = decision.get("onboarding_payload_id")
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None


def _require_template_payloads(copy_payload: dict[str, Any]) -> dict[str, Any]:
    template_payloads = copy_payload.get("template_payloads")
    if not isinstance(template_payloads, dict):
        raise RuntimeError(
            "Strategy V2 copy payload is missing template_payloads. "
            "Remediation: rerun copy pipeline and final approval before launch."
        )
    for template_id in _REQUIRED_TEMPLATE_IDS:
        template_entry = template_payloads.get(template_id)
        if not isinstance(template_entry, dict):
            raise RuntimeError(
                f"Strategy V2 template payload is missing required template '{template_id}'."
            )
        patch_ops = template_entry.get("template_patch")
        if not isinstance(patch_ops, list) or not patch_ops:
            raise RuntimeError(
                f"Strategy V2 template payload for '{template_id}' is missing template_patch operations."
            )
    return template_payloads


def load_strategy_v2_source_context(
    *,
    session: Session,
    org_id: str,
    source_run: WorkflowRun,
) -> StrategyV2SourceContext:
    if source_run.kind != WorkflowKindEnum.strategy_v2:
        raise RuntimeError("Workflow is not a Strategy V2 run.")
    if source_run.status != WorkflowStatusEnum.completed:
        raise RuntimeError("Strategy V2 run must be completed before launch.")
    if not source_run.client_id or not source_run.product_id:
        raise RuntimeError("Source Strategy V2 run must include client_id and product_id.")

    effective_source_run = source_run
    source_run_id = str(effective_source_run.id)
    step_payloads = _load_step_payload_records(session=session, org_id=org_id, workflow_run_id=source_run_id)
    missing_required_launch_steps = _missing_required_launch_step_keys(step_payloads=step_payloads)
    if missing_required_launch_steps:
        alternate_run_id = _find_alternate_completed_run_with_required_payloads(
            session=session,
            org_id=org_id,
            source_run=effective_source_run,
        )
        if not alternate_run_id:
            raise RuntimeError(
                "Missing required Strategy V2 step payloads "
                f"{missing_required_launch_steps}. Remediation: rerun Strategy V2 and complete all required checkpoints."
            )
        alternate_run = session.get(WorkflowRun, alternate_run_id)
        if alternate_run is None:
            raise RuntimeError(
                "Resolved canonical Strategy V2 workflow run was not found. "
                f"Remediation: rerun Strategy V2. canonical_workflow_run_id={alternate_run_id}"
            )
        effective_source_run = alternate_run
        source_run_id = str(effective_source_run.id)
        step_payloads = _load_step_payload_records(session=session, org_id=org_id, workflow_run_id=source_run_id)
        missing_required_launch_steps = _missing_required_launch_step_keys(step_payloads=step_payloads)
        if missing_required_launch_steps:
            raise RuntimeError(
                "Resolved canonical Strategy V2 workflow run is still missing required launch checkpoints "
                f"{missing_required_launch_steps}. Remediation: rerun Strategy V2 and complete all required checkpoints."
            )

    v2_06 = _require_step_payload(step_payloads=step_payloads, step_key="v2-06")
    v2_08 = _require_step_payload(step_payloads=step_payloads, step_key="v2-08")
    v2_09 = _require_step_payload(step_payloads=step_payloads, step_key="v2-09")
    v2_11 = _require_step_payload(step_payloads=step_payloads, step_key="v2-11")

    v2_05 = step_payloads.get("v2-05")

    decision_payload = _require_dict(v2_11.payload.get("decision"), field_name="v2-11.decision")
    approved = decision_payload.get("approved")
    if approved is not True:
        raise RuntimeError(
            "Strategy V2 final copy approval is missing or rejected. "
            "Remediation: approve final copy (v2-11) before launching."
        )
    approved_copy_artifact_id = _require_nonempty_str(
        v2_11.payload.get("approved_artifact_id"),
        field_name="v2-11.approved_artifact_id",
    )
    approved_copy_raw = _load_artifact_payload(
        session=session,
        org_id=org_id,
        artifact_id=approved_copy_artifact_id,
        expected_type=ArtifactTypeEnum.strategy_v2_copy,
        field_name="approved copy artifact",
    )
    approved_copy = normalize_strategy_v2_copy_payload(approved_copy_raw)
    if not isinstance(approved_copy, dict):
        raise RuntimeError("Approved Strategy V2 copy payload is invalid.")
    _require_template_payloads(approved_copy)

    stage3_artifact_id = _require_nonempty_str(
        v2_09.payload.get("stage3_artifact_id"),
        field_name="v2-09.stage3_artifact_id",
    )
    offer_artifact_id = _require_nonempty_str(
        v2_09.payload.get("offer_artifact_id"),
        field_name="v2-09.offer_artifact_id",
    )
    copy_context_artifact_id = _require_nonempty_str(
        v2_09.payload.get("copy_context_artifact_id"),
        field_name="v2-09.copy_context_artifact_id",
    )
    awareness_matrix_artifact_id_raw = v2_09.payload.get("awareness_matrix_artifact_id")
    awareness_matrix_artifact_id = (
        awareness_matrix_artifact_id_raw.strip()
        if isinstance(awareness_matrix_artifact_id_raw, str) and awareness_matrix_artifact_id_raw.strip()
        else None
    )

    stage3_payload = _load_artifact_payload(
        session=session,
        org_id=org_id,
        artifact_id=stage3_artifact_id,
        expected_type=ArtifactTypeEnum.strategy_v2_stage3,
        field_name="source stage3 artifact",
    )
    offer_payload = _load_artifact_payload(
        session=session,
        org_id=org_id,
        artifact_id=offer_artifact_id,
        expected_type=ArtifactTypeEnum.strategy_v2_offer,
        field_name="source offer artifact",
    )
    copy_context_payload = _load_artifact_payload(
        session=session,
        org_id=org_id,
        artifact_id=copy_context_artifact_id,
        expected_type=ArtifactTypeEnum.strategy_v2_copy_context,
        field_name="source copy context artifact",
    )
    awareness_payload = None
    if awareness_matrix_artifact_id is not None:
        awareness_payload = _load_artifact_payload(
            session=session,
            org_id=org_id,
            artifact_id=awareness_matrix_artifact_id,
            expected_type=ArtifactTypeEnum.strategy_v2_awareness_angle_matrix,
            field_name="source awareness matrix artifact",
        )

    selected_angle = _require_dict(stage3_payload.get("selected_angle"), field_name="stage3.selected_angle")
    selected_angle_id = _require_nonempty_str(selected_angle.get("angle_id"), field_name="selected_angle.angle_id")
    selected_angle_name = _require_nonempty_str(
        selected_angle.get("angle_name"),
        field_name="selected_angle.angle_name",
    )
    angle_run_id = _require_nonempty_str(approved_copy.get("angle_run_id"), field_name="approved_copy.angle_run_id")

    stage1_artifact_id = _require_nonempty_str(
        v2_06.payload.get("stage1_artifact_id"),
        field_name="v2-06.stage1_artifact_id",
    )
    stage1_payload = _load_artifact_payload(
        session=session,
        org_id=org_id,
        artifact_id=stage1_artifact_id,
        expected_type=ArtifactTypeEnum.strategy_v2_stage1,
        field_name="source stage1 artifact",
    )
    # Enforce strict contract validation for branch replay.
    ProductBriefStage1.model_validate(stage1_payload)

    ranked_candidates_raw = _require_list(v2_06.payload.get("ranked_candidates"), field_name="v2-06.ranked_candidates")
    ranked_candidates = [row for row in ranked_candidates_raw if isinstance(row, dict)]
    if not ranked_candidates:
        raise RuntimeError("v2-06 ranked_candidates is empty.")

    offer_pipeline_payload = dict(v2_08.payload)
    offer_operator_inputs = _extract_offer_operator_inputs(offer_pipeline_payload)

    competitor_analysis = None
    voc_observations: list[dict[str, Any]] = []
    voc_scored: dict[str, Any] = {}
    proof_asset_candidates: list[dict[str, Any]] = []
    if v2_05 is not None:
        competitor_analysis_raw = v2_05.payload.get("competitor_analysis")
        if isinstance(competitor_analysis_raw, dict):
            competitor_analysis = competitor_analysis_raw
        voc_observations_raw = v2_05.payload.get("voc_observations")
        if isinstance(voc_observations_raw, list):
            voc_observations = [row for row in voc_observations_raw if isinstance(row, dict)]
        voc_scored_raw = v2_05.payload.get("voc_scored")
        if isinstance(voc_scored_raw, dict):
            voc_scored = voc_scored_raw
        proof_candidates_raw = v2_05.payload.get("proof_asset_candidates")
        if isinstance(proof_candidates_raw, list):
            proof_asset_candidates = [row for row in proof_candidates_raw if isinstance(row, dict)]
    if competitor_analysis is None:
        competitor_analysis_v2_06 = v2_06.payload.get("competitor_analysis")
        if isinstance(competitor_analysis_v2_06, dict):
            competitor_analysis = competitor_analysis_v2_06
    if not voc_observations:
        voc_observations_v2_06 = v2_06.payload.get("voc_observations")
        if isinstance(voc_observations_v2_06, list):
            voc_observations = [row for row in voc_observations_v2_06 if isinstance(row, dict)]
    if not voc_scored:
        voc_scored_v2_06 = v2_06.payload.get("voc_scored")
        if isinstance(voc_scored_v2_06, dict):
            voc_scored = voc_scored_v2_06
    if not proof_asset_candidates:
        proof_candidates_v2_06 = v2_06.payload.get("proof_asset_candidates")
        if isinstance(proof_candidates_v2_06, list):
            proof_asset_candidates = [row for row in proof_candidates_v2_06 if isinstance(row, dict)]
    if competitor_analysis is None:
        competitor_analysis = _extract_competitor_analysis_from_foundation(step_payloads)
    if not proof_asset_candidates:
        v2_08_proof_candidates = v2_08.payload.get("proof_asset_candidates")
        if isinstance(v2_08_proof_candidates, list):
            proof_asset_candidates = [row for row in v2_08_proof_candidates if isinstance(row, dict)]

    source_downstream_packet = build_strategy_v2_downstream_packet(
        stage3=stage3_payload,
        offer=offer_payload,
        copy=approved_copy,
        copy_context=copy_context_payload,
        awareness_angle_matrix=awareness_payload if isinstance(awareness_payload, dict) else None,
        artifact_ids={
            "stage3": stage3_artifact_id,
            "offer": offer_artifact_id,
            "copy": approved_copy_artifact_id,
            "copy_context": copy_context_artifact_id,
            "awareness_angle_matrix": awareness_matrix_artifact_id,
        },
    )
    if not isinstance(source_downstream_packet, dict):
        raise RuntimeError(
            "Failed to build Strategy V2 downstream packet from approved artifacts."
        )

    return StrategyV2SourceContext(
        source_run=effective_source_run,
        source_temporal_workflow_id=_require_nonempty_str(
            effective_source_run.temporal_workflow_id,
            field_name="source temporal workflow id",
        ),
        selected_angle=selected_angle,
        selected_angle_id=selected_angle_id,
        selected_angle_name=selected_angle_name,
        angle_run_id=angle_run_id,
        stage1=stage1_payload,
        ranked_angle_candidates=ranked_candidates,
        angle_synthesis_payload=dict(v2_06.payload),
        competitor_analysis=competitor_analysis,
        voc_observations=voc_observations,
        voc_scored=voc_scored,
        proof_asset_candidates=proof_asset_candidates,
        offer_pipeline_payload=offer_pipeline_payload,
        source_stage3=stage3_payload,
        source_offer=offer_payload,
        source_copy=approved_copy,
        source_copy_context=copy_context_payload,
        source_downstream_packet=source_downstream_packet,
        source_stage3_artifact_id=stage3_artifact_id,
        source_offer_artifact_id=offer_artifact_id,
        source_copy_artifact_id=approved_copy_artifact_id,
        source_copy_context_artifact_id=copy_context_artifact_id,
        source_awareness_matrix_artifact_id=awareness_matrix_artifact_id,
        offer_operator_inputs=offer_operator_inputs,
        offer_winner_onboarding_payload_id=_extract_offer_winner_onboarding_payload_id(v2_09.payload),
        step_payloads=step_payloads,
    )


def normalized_angle_slug(angle_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", angle_name).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return cleaned or "angle"


def build_angle_campaign_name(*, angle_id: str, angle_name: str, launch_index: int) -> str:
    if launch_index < 1:
        raise RuntimeError("launch_index must be >= 1.")
    return f"ang-{angle_id}--{normalized_angle_slug(angle_name)}--l{launch_index}"


def canonicalize_string_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def build_launch_key(
    *,
    source_strategy_v2_workflow_run_id: str,
    launch_type: str,
    angle_id: str,
    campaign_id: str | None,
    selected_ums_id: str | None,
    channels: list[str],
    asset_brief_types: list[str],
    experiment_variant_policy: str | None,
) -> str:
    payload = {
        "source_strategy_v2_workflow_run_id": source_strategy_v2_workflow_run_id,
        "launch_type": launch_type,
        "angle_id": angle_id,
        "campaign_id": campaign_id or "",
        "selected_ums_id": selected_ums_id or "",
        "channels": canonicalize_string_list(channels),
        "asset_brief_types": canonicalize_string_list(asset_brief_types),
        "experiment_variant_policy": (experiment_variant_policy or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sv2-launch:{launch_type}:{digest}"


def list_ranked_angle_ids(ranked_candidates: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for row in ranked_candidates:
        if not isinstance(row, dict):
            continue
        angle_raw = row.get("angle")
        angle = angle_raw if isinstance(angle_raw, dict) else row
        angle_id = angle.get("angle_id") if isinstance(angle, dict) else None
        if isinstance(angle_id, str) and angle_id.strip():
            ids.add(angle_id.strip())
    return ids


def find_ranked_angle_payload(
    *,
    ranked_candidates: list[dict[str, Any]],
    angle_id: str,
) -> dict[str, Any] | None:
    target = angle_id.strip()
    for row in ranked_candidates:
        if not isinstance(row, dict):
            continue
        angle_raw = row.get("angle")
        angle_payload = angle_raw if isinstance(angle_raw, dict) else row
        if not isinstance(angle_payload, dict):
            continue
        candidate_id = angle_payload.get("angle_id")
        if isinstance(candidate_id, str) and candidate_id.strip() == target:
            return angle_payload
    return None


def resolve_ums_selection_map(offer_pipeline_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pair_scoring = _require_dict(offer_pipeline_payload.get("pair_scoring"), field_name="v2-08.pair_scoring")
    ranked_pairs_raw = _require_list(pair_scoring.get("ranked_pairs"), field_name="v2-08.pair_scoring.ranked_pairs")
    ranked_pairs = [row for row in ranked_pairs_raw if isinstance(row, dict)]
    if not ranked_pairs:
        raise RuntimeError("v2-08 pair_scoring.ranked_pairs is empty.")

    lookup: dict[str, dict[str, Any]] = {}
    for row in ranked_pairs:
        pair_id = row.get("pair_id")
        if isinstance(pair_id, str) and pair_id.strip():
            lookup[pair_id.strip()] = row
        ums_id = row.get("ums_id")
        if isinstance(ums_id, str) and ums_id.strip():
            lookup[ums_id.strip()] = row
        ums_name = row.get("ums_name")
        if isinstance(ums_name, str) and ums_name.strip():
            lookup[ums_name.strip()] = row
    return lookup
