from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.config import settings
    from app.temporal.activities.campaign_intent_activities import (
        create_campaign_activity,
        create_funnels_from_experiments_activity,
    )
    from app.temporal.workflows.campaign_funnel_media_enrichment import (
        CampaignFunnelMediaEnrichmentInput,
        CampaignFunnelMediaEnrichmentWorkflow,
    )
    from app.temporal.activities.strategy_v2_activities import (
        apply_strategy_v2_angle_selection_activity,
        build_strategy_v2_offer_variants_activity,
        finalize_strategy_v2_copy_approval_activity,
        finalize_strategy_v2_offer_winner_activity,
        run_strategy_v2_copy_pipeline_activity,
        run_strategy_v2_offer_pipeline_activity,
        validate_strategy_v2_offer_data_readiness_activity,
    )
    from app.temporal.activities.strategy_v2_launch_activities import (
        create_strategy_v2_launch_artifacts_activity,
        persist_strategy_v2_launch_record_activity,
    )
    from app.strategy_v2.downstream import build_strategy_v2_downstream_packet


DEFAULT_FUNNEL_PAGES = [
    {"template_id": "pre-sales-listicle", "name": "Pre-Sales", "slug": "pre-sales"},
    {"template_id": "sales-pdp", "name": "Sales", "slug": "sales"},
]

_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=1,
)
_FUNNEL_GENERATION_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
    non_retryable_error_types=[
        "ToolExecutionError",
        "TimeoutError",
        "ValueError",
        "RuntimeError",
        "TestimonialGenerationError",
    ],
)
_COPY_WORKFLOW_GENERATION_MODE = os.getenv(
    "STRATEGY_V2_COPY_WORKFLOW_GENERATION_MODE",
    os.getenv("STRATEGY_V2_COPY_GENERATION_MODE", "template_payload_only"),
).strip()


def _require_nonempty_string(value: Any, *, field_name: str) -> str:
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


def _normalize_dict_rows(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    rows = _require_list(value, field_name=field_name)
    normalized = [row for row in rows if isinstance(row, dict)]
    if not normalized:
        raise RuntimeError(f"{field_name} must include at least one object row.")
    return normalized


def _build_attestation_payload() -> dict[str, bool]:
    return {
        "reviewed_evidence": True,
        "understands_impact": True,
    }


def _score_value(row: dict[str, Any]) -> float:
    for key in ("composite_safety_adjusted", "composite_score", "score"):
        raw = row.get(key)
        if isinstance(raw, (int, float)):
            return float(raw)
    return 0.0


def _select_best_ranked_pair(offer_pipeline_payload: dict[str, Any]) -> dict[str, Any]:
    pair_scoring = _require_dict(
        offer_pipeline_payload.get("pair_scoring"),
        field_name="offer_pipeline_payload.pair_scoring",
    )
    ranked_pairs = _normalize_dict_rows(
        pair_scoring.get("ranked_pairs"),
        field_name="offer_pipeline_payload.pair_scoring.ranked_pairs",
    )
    sorted_pairs = sorted(ranked_pairs, key=_score_value, reverse=True)
    best_pair = sorted_pairs[0]
    _require_nonempty_string(best_pair.get("pair_id"), field_name="best_pair.pair_id")
    return best_pair


def _select_best_offer_variant(offer_variants_payload: dict[str, Any]) -> str:
    composite = _require_dict(
        offer_variants_payload.get("composite_results"),
        field_name="offer_variants_output.composite_results",
    )
    variants = _normalize_dict_rows(
        composite.get("variants"),
        field_name="offer_variants_output.composite_results.variants",
    )
    best = sorted(variants, key=_score_value, reverse=True)[0]
    return _require_nonempty_string(best.get("variant_id"), field_name="best_variant.variant_id")


def _extract_funnel_id(funnels_result: dict[str, Any]) -> str | None:
    rows = funnels_result.get("funnels")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        funnel = row.get("funnel")
        if not isinstance(funnel, dict):
            continue
        funnel_id = funnel.get("funnel_id")
        if isinstance(funnel_id, str) and funnel_id.strip():
            return funnel_id.strip()
    return None


def _extract_media_enrichment_jobs(funnels_result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_jobs = funnels_result.get("media_enrichment_jobs")
    if not isinstance(raw_jobs, list):
        return []
    return [job for job in raw_jobs if isinstance(job, dict)]


async def _start_media_enrichment_workflows(
    *,
    org_id: str,
    media_enrichment_jobs: list[dict[str, Any]],
    default_actor_user_id: str,
    default_workflow_run_id: str,
) -> list[dict[str, Any]]:
    started_workflows: list[dict[str, Any]] = []
    if not media_enrichment_jobs:
        return started_workflows

    parent_workflow_id = workflow.info().workflow_id
    for idx, job in enumerate(media_enrichment_jobs):
        funnel_id = str(job.get("funnel_id") or "").strip()
        page_id = str(job.get("page_id") or "").strip()
        if not funnel_id or not page_id:
            continue

        child_workflow_id = f"{parent_workflow_id}-media-{funnel_id[:8]}-{page_id[:8]}-{idx}"
        workflow_run_id = str(job.get("workflow_run_id") or "").strip() or default_workflow_run_id
        child_handle = await workflow.start_child_workflow(
            CampaignFunnelMediaEnrichmentWorkflow.run,
            CampaignFunnelMediaEnrichmentInput(
                org_id=org_id,
                actor_user_id=str(job.get("actor_user_id") or default_actor_user_id),
                workflow_run_id=workflow_run_id,
                funnel_id=funnel_id,
                page_id=page_id,
                page_name=str(job.get("page_name") or ""),
                template_id=job.get("template_id"),
                prompt=str(job.get("prompt") or "Media enrichment run"),
                idea_workspace_id=job.get("idea_workspace_id"),
                generate_testimonials=bool(job.get("generate_testimonials", False)),
                experiment_id=job.get("experiment_id"),
                variant_id=job.get("variant_id"),
            ),
            id=child_workflow_id,
            task_queue=settings.TEMPORAL_MEDIA_ENRICHMENT_TASK_QUEUE,
            parent_close_policy=workflow.ParentClosePolicy.ABANDON,
        )
        started_workflows.append(
            {
                "workflow_id": child_handle.id,
                "first_execution_run_id": child_handle.first_execution_run_id,
                "funnel_id": funnel_id,
                "page_id": page_id,
                "experiment_id": job.get("experiment_id"),
                "variant_id": job.get("variant_id"),
            }
        )

    return started_workflows


def _build_pair_decision(
    *,
    operator_user_id: str,
    pair_id: str,
    ranked_pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "operator_user_id": operator_user_id,
        "decision_mode": "manual",
        "pair_id": pair_id,
        "rejected_pair_ids": [
            str(row.get("pair_id"))
            for row in ranked_pairs
            if isinstance(row.get("pair_id"), str) and str(row.get("pair_id")) != pair_id
        ],
        "reviewed_candidate_ids": [pair_id],
        "attestation": _build_attestation_payload(),
        "operator_note": "Selected this UMS pair after reviewing ranked candidates and supporting evidence.",
    }


def _build_offer_winner_decision(
    *,
    operator_user_id: str,
    variant_id: str,
    variants: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "operator_user_id": operator_user_id,
        "decision_mode": "manual",
        "variant_id": variant_id,
        "rejected_variant_ids": [
            str(row.get("variant_id"))
            for row in variants
            if isinstance(row.get("variant_id"), str) and str(row.get("variant_id")) != variant_id
        ],
        "reviewed_candidate_ids": [variant_id],
        "attestation": _build_attestation_payload(),
        "operator_note": "Selected this offer variant after reviewing variant scores and evaluation outputs.",
    }


def _build_final_copy_decision(
    *,
    operator_user_id: str,
    reviewed_candidate_id: str,
) -> dict[str, Any]:
    return {
        "operator_user_id": operator_user_id,
        "decision_mode": "manual",
        "approved": True,
        "reviewed_candidate_ids": [reviewed_candidate_id],
        "attestation": _build_attestation_payload(),
        "operator_note": "Approved final copy after reviewing contract checks and launch readiness criteria.",
    }


@dataclass
class StrategyV2AngleCampaignLaunchInput:
    org_id: str
    client_id: str
    product_id: str
    source_strategy_v2_workflow_run_id: str
    source_strategy_v2_temporal_workflow_id: str
    launch_workflow_run_id: str
    operator_user_id: str
    channels: list[str]
    asset_brief_types: list[str]
    experiment_variant_policy: str
    launch_items: list[dict[str, Any]]
    stage1: dict[str, Any] | None = None
    ranked_angle_candidates: list[dict[str, Any]] | None = None
    competitor_analysis: dict[str, Any] | None = None
    voc_scored: dict[str, Any] | None = None
    voc_observations: list[dict[str, Any]] | None = None
    proof_asset_candidates: list[dict[str, Any]] | None = None
    angle_synthesis_payload: dict[str, Any] | None = None
    offer_operator_inputs: dict[str, Any] | None = None
    onboarding_payload_id: str | None = None


@dataclass
class StrategyV2AngleIterationInput:
    org_id: str
    client_id: str
    product_id: str
    source_strategy_v2_workflow_run_id: str
    source_strategy_v2_temporal_workflow_id: str
    launch_workflow_run_id: str
    operator_user_id: str
    campaign_id: str
    channels: list[str]
    asset_brief_types: list[str]
    launch_name_prefix: str
    experiment_variant_policy: str
    base_angle_run_id: str
    selected_angle: dict[str, Any]
    stage1: dict[str, Any]
    ranked_angle_candidates: list[dict[str, Any]]
    offer_pipeline_payload: dict[str, Any]
    offer_operator_inputs: dict[str, Any]
    angle_synthesis_payload: dict[str, Any]
    onboarding_payload_id: str | None
    ums_launch_items: list[dict[str, Any]]


@workflow.defn
class StrategyV2AngleCampaignLaunchWorkflow:
    @workflow.run
    async def run(self, input: StrategyV2AngleCampaignLaunchInput) -> dict[str, Any]:
        if not input.launch_items:
            raise RuntimeError("launch_items are required.")
        workflow_id = workflow.info().workflow_id
        workflow_run_id = input.launch_workflow_run_id
        campaign_ids: list[str] = []
        launch_records: list[dict[str, Any]] = []
        media_enrichment_workflows: list[dict[str, Any]] = []

        for launch_item in input.launch_items:
            launch_type = _require_nonempty_string(launch_item.get("launch_type"), field_name="launch_item.launch_type")
            if launch_type not in {"initial_angle", "additional_angle"}:
                raise RuntimeError(f"Unsupported launch_type for angle campaign workflow: {launch_type}")

            angle_payload = _require_dict(launch_item.get("angle"), field_name="launch_item.angle")
            angle_id = _require_nonempty_string(angle_payload.get("angle_id"), field_name="angle.angle_id")
            angle_name = _require_nonempty_string(angle_payload.get("angle_name"), field_name="angle.angle_name")
            launch_key = _require_nonempty_string(launch_item.get("launch_key"), field_name="launch_item.launch_key")
            campaign_name = _require_nonempty_string(
                launch_item.get("campaign_name"),
                field_name="launch_item.campaign_name",
            )

            selected_ums_id: str | None = None
            selected_variant_id: str | None = None
            angle_run_id: str
            source_stage3_artifact_id: str
            source_offer_artifact_id: str
            source_copy_artifact_id: str
            source_copy_context_artifact_id: str
            strategy_v2_packet: dict[str, Any]
            strategy_v2_copy_context: dict[str, Any]

            if launch_type == "initial_angle":
                strategy_v2_packet = _require_dict(
                    launch_item.get("strategy_v2_packet"),
                    field_name="launch_item.strategy_v2_packet",
                )
                strategy_v2_copy_context = _require_dict(
                    launch_item.get("strategy_v2_copy_context"),
                    field_name="launch_item.strategy_v2_copy_context",
                )
                angle_run_id = _require_nonempty_string(
                    launch_item.get("angle_run_id"),
                    field_name="launch_item.angle_run_id",
                )
                selected_ums_raw = launch_item.get("selected_ums_id")
                selected_ums_id = selected_ums_raw.strip() if isinstance(selected_ums_raw, str) and selected_ums_raw.strip() else None
                selected_variant_raw = launch_item.get("selected_variant_id")
                selected_variant_id = (
                    selected_variant_raw.strip()
                    if isinstance(selected_variant_raw, str) and selected_variant_raw.strip()
                    else None
                )
                source_stage3_artifact_id = _require_nonempty_string(
                    launch_item.get("source_stage3_artifact_id"),
                    field_name="launch_item.source_stage3_artifact_id",
                )
                source_offer_artifact_id = _require_nonempty_string(
                    launch_item.get("source_offer_artifact_id"),
                    field_name="launch_item.source_offer_artifact_id",
                )
                source_copy_artifact_id = _require_nonempty_string(
                    launch_item.get("source_copy_artifact_id"),
                    field_name="launch_item.source_copy_artifact_id",
                )
                source_copy_context_artifact_id = _require_nonempty_string(
                    launch_item.get("source_copy_context_artifact_id"),
                    field_name="launch_item.source_copy_context_artifact_id",
                )
            else:
                stage1 = _require_dict(input.stage1, field_name="stage1")
                ranked_candidates = _normalize_dict_rows(
                    input.ranked_angle_candidates,
                    field_name="ranked_angle_candidates",
                )
                competitor_analysis = _require_dict(input.competitor_analysis, field_name="competitor_analysis")
                voc_scored = _require_dict(input.voc_scored, field_name="voc_scored")
                voc_observations = _normalize_dict_rows(input.voc_observations, field_name="voc_observations")
                proof_asset_candidates = (
                    _normalize_dict_rows(input.proof_asset_candidates, field_name="proof_asset_candidates")
                    if input.proof_asset_candidates
                    else []
                )
                angle_synthesis_payload = _require_dict(input.angle_synthesis_payload, field_name="angle_synthesis_payload")
                offer_operator_inputs = _require_dict(input.offer_operator_inputs, field_name="offer_operator_inputs")

                stage2_result = await workflow.execute_activity(
                    apply_strategy_v2_angle_selection_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "stage1": stage1,
                        "angle_selection_decision": {
                            "operator_user_id": input.operator_user_id,
                            "decision_mode": "manual",
                            "selected_angle": angle_payload,
                            "rejected_angle_ids": [
                                str((row.get("angle") or row).get("angle_id"))
                                for row in ranked_candidates
                                if isinstance((row.get("angle") or row), dict)
                                and str((row.get("angle") or row).get("angle_id")) != angle_id
                            ],
                            "reviewed_candidate_ids": [angle_id],
                            "attestation": _build_attestation_payload(),
                            "operator_note": "Selected this additional angle after reviewing ranked evidence and launch fit.",
                        },
                        "ranked_angle_candidates": ranked_candidates,
                    },
                    schedule_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_RETRY_POLICY,
                )
                stage2 = _require_dict(stage2_result.get("stage2"), field_name="stage2_result.stage2")

                offer_pipeline_result = await workflow.execute_activity(
                    run_strategy_v2_offer_pipeline_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "operator_user_id": input.operator_user_id,
                        "stage2": stage2,
                        "competitor_analysis": competitor_analysis,
                        "voc_scored": voc_scored,
                        "voc_observations": voc_observations,
                        "angle_synthesis": angle_synthesis_payload,
                        "proof_asset_candidates": proof_asset_candidates,
                        "business_model": _require_nonempty_string(
                            offer_operator_inputs.get("business_model"),
                            field_name="offer_operator_inputs.business_model",
                        ),
                        "funnel_position": _require_nonempty_string(
                            offer_operator_inputs.get("funnel_position"),
                            field_name="offer_operator_inputs.funnel_position",
                        ),
                        "target_platforms": _require_list(
                            offer_operator_inputs.get("target_platforms"),
                            field_name="offer_operator_inputs.target_platforms",
                        ),
                        "target_regions": _require_list(
                            offer_operator_inputs.get("target_regions"),
                            field_name="offer_operator_inputs.target_regions",
                        ),
                        "existing_proof_assets": _require_list(
                            offer_operator_inputs.get("existing_proof_assets"),
                            field_name="offer_operator_inputs.existing_proof_assets",
                        ),
                        "brand_voice_notes": _require_nonempty_string(
                            offer_operator_inputs.get("brand_voice_notes"),
                            field_name="offer_operator_inputs.brand_voice_notes",
                        ),
                    },
                    schedule_to_close_timeout=timedelta(minutes=25),
                    retry_policy=_RETRY_POLICY,
                )
                offer_pipeline_payload = _require_dict(offer_pipeline_result, field_name="offer_pipeline_result")
                offer_data_readiness_result = await workflow.execute_activity(
                    validate_strategy_v2_offer_data_readiness_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "onboarding_payload_id": input.onboarding_payload_id,
                        "offer_pipeline_output": offer_pipeline_payload,
                    },
                    schedule_to_close_timeout=timedelta(minutes=10),
                    retry_policy=_RETRY_POLICY,
                )
                offer_data_readiness_payload = _require_dict(
                    offer_data_readiness_result,
                    field_name="offer_data_readiness_result",
                )
                readiness_status = str(offer_data_readiness_payload.get("status") or "").strip().lower()
                if readiness_status != "ready":
                    raise RuntimeError(
                        "Offer data readiness blocked launch workflow additional-angle generation. "
                        f"missing_fields={offer_data_readiness_payload.get('missing_fields')}; "
                        f"inconsistent_fields={offer_data_readiness_payload.get('inconsistent_fields')}"
                    )
                pair_scoring = _require_dict(
                    offer_pipeline_payload.get("pair_scoring"),
                    field_name="offer_pipeline_result.pair_scoring",
                )
                ranked_pairs = _normalize_dict_rows(
                    pair_scoring.get("ranked_pairs"),
                    field_name="offer_pipeline_result.pair_scoring.ranked_pairs",
                )
                best_pair = _select_best_ranked_pair(offer_pipeline_payload)
                selected_pair_id = _require_nonempty_string(best_pair.get("pair_id"), field_name="best_pair.pair_id")

                offer_variants_result = await workflow.execute_activity(
                    build_strategy_v2_offer_variants_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "stage2": stage2,
                        "offer_pipeline_output": offer_pipeline_payload,
                        "offer_data_readiness": offer_data_readiness_payload,
                        "ump_ums_selection_decision": _build_pair_decision(
                            operator_user_id=input.operator_user_id,
                            pair_id=selected_pair_id,
                            ranked_pairs=ranked_pairs,
                        ),
                    },
                    schedule_to_close_timeout=timedelta(minutes=20),
                    retry_policy=_RETRY_POLICY,
                )
                offer_variants_payload = _require_dict(offer_variants_result, field_name="offer_variants_result")
                variants = _normalize_dict_rows(
                    offer_variants_payload.get("variants"),
                    field_name="offer_variants_result.variants",
                )
                selected_variant_id = _select_best_offer_variant(offer_variants_payload)

                stage3_result = await workflow.execute_activity(
                    finalize_strategy_v2_offer_winner_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "stage2": stage2,
                        "offer_variants_output": offer_variants_payload,
                        "offer_pipeline_output": offer_pipeline_payload,
                        "offer_winner_decision": _build_offer_winner_decision(
                            operator_user_id=input.operator_user_id,
                            variant_id=selected_variant_id,
                            variants=variants,
                        ),
                        "onboarding_payload_id": input.onboarding_payload_id,
                        "brand_voice_notes": _require_nonempty_string(
                            offer_operator_inputs.get("brand_voice_notes"),
                            field_name="offer_operator_inputs.brand_voice_notes",
                        ),
                        "compliance_notes": None,
                    },
                    schedule_to_close_timeout=timedelta(minutes=10),
                    retry_policy=_RETRY_POLICY,
                )
                stage3_payload = _require_dict(stage3_result.get("stage3"), field_name="stage3_result.stage3")
                copy_context_payload = _require_dict(
                    stage3_result.get("copy_context"),
                    field_name="stage3_result.copy_context",
                )
                source_stage3_artifact_id = _require_nonempty_string(
                    stage3_result.get("stage3_artifact_id"),
                    field_name="stage3_result.stage3_artifact_id",
                )
                source_offer_artifact_id = _require_nonempty_string(
                    stage3_result.get("offer_artifact_id"),
                    field_name="stage3_result.offer_artifact_id",
                )
                source_copy_context_artifact_id = _require_nonempty_string(
                    stage3_result.get("copy_context_artifact_id"),
                    field_name="stage3_result.copy_context_artifact_id",
                )
                source_awareness_matrix_artifact_id = (
                    _require_nonempty_string(
                        stage3_result.get("awareness_matrix_artifact_id"),
                        field_name="stage3_result.awareness_matrix_artifact_id",
                    )
                    if stage3_result.get("awareness_matrix_artifact_id") is not None
                    else None
                )

                copy_result = await workflow.execute_activity(
                    run_strategy_v2_copy_pipeline_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "stage3": stage3_payload,
                        "copy_context": copy_context_payload,
                        "operator_user_id": input.operator_user_id,
                        "copy_generation_mode": _COPY_WORKFLOW_GENERATION_MODE,
                    },
                    schedule_to_close_timeout=timedelta(minutes=35),
                    retry_policy=_RETRY_POLICY,
                )
                copy_payload = _require_dict(copy_result.get("copy_payload"), field_name="copy_result.copy_payload")
                source_copy_artifact_id = _require_nonempty_string(
                    copy_result.get("copy_artifact_id"),
                    field_name="copy_result.copy_artifact_id",
                )

                await workflow.execute_activity(
                    finalize_strategy_v2_copy_approval_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": None,
                        "workflow_run_id": workflow_run_id,
                        "copy_payload": copy_payload,
                        "final_approval_decision": _build_final_copy_decision(
                            operator_user_id=input.operator_user_id,
                            reviewed_candidate_id=source_copy_artifact_id,
                        ),
                    },
                    schedule_to_close_timeout=timedelta(minutes=5),
                    retry_policy=_RETRY_POLICY,
                )

                angle_run_id = _require_nonempty_string(
                    copy_payload.get("angle_run_id"),
                    field_name="copy_payload.angle_run_id",
                )
                selected_ums_id = (
                    str(best_pair.get("ums_id")).strip()
                    if isinstance(best_pair.get("ums_id"), str) and str(best_pair.get("ums_id")).strip()
                    else selected_pair_id
                )
                awareness_payload = stage3_result.get("awareness_matrix")
                awareness_matrix_payload = awareness_payload if isinstance(awareness_payload, dict) else None
                strategy_v2_packet = build_strategy_v2_downstream_packet(
                    stage3=stage3_payload,
                    offer={
                        "stage3": stage3_payload,
                        "selected_variant": next(
                            (
                                variant
                                for variant in variants
                                if str(variant.get("variant_id")) == selected_variant_id
                            ),
                            {},
                        ),
                        "selected_variant_score": next(
                            (
                                row
                                for row in _normalize_dict_rows(
                                    _require_dict(
                                        offer_variants_payload.get("composite_results"),
                                        field_name="offer_variants_output.composite_results",
                                    ).get("variants"),
                                    field_name="offer_variants_output.composite_results.variants",
                                )
                                if str(row.get("variant_id")) == selected_variant_id
                            ),
                            None,
                        ),
                        "decision": _build_offer_winner_decision(
                            operator_user_id=input.operator_user_id,
                            variant_id=selected_variant_id,
                            variants=variants,
                        ),
                    },
                    copy=copy_payload,
                    copy_context=copy_context_payload,
                    awareness_angle_matrix=awareness_matrix_payload,
                    artifact_ids={
                        "stage3": source_stage3_artifact_id,
                        "offer": source_offer_artifact_id,
                        "copy": source_copy_artifact_id,
                        "copy_context": source_copy_context_artifact_id,
                        "awareness_angle_matrix": source_awareness_matrix_artifact_id,
                    },
                )
                if not isinstance(strategy_v2_packet, dict):
                    raise RuntimeError("Failed to build downstream packet for additional angle launch.")
                strategy_v2_copy_context = copy_context_payload

            strategy_v2_packet["launch_metadata"] = {
                "launch_type": launch_type,
                "launch_key": launch_key,
                "source_strategy_v2_workflow_run_id": input.source_strategy_v2_workflow_run_id,
                "source_strategy_v2_temporal_workflow_id": input.source_strategy_v2_temporal_workflow_id,
                "angle_id": angle_id,
                "selected_ums_id": selected_ums_id,
                "selected_variant_id": selected_variant_id,
            }

            campaign_result = await workflow.execute_activity(
                create_campaign_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_name": campaign_name,
                    "channels": input.channels,
                    "asset_brief_types": input.asset_brief_types,
                    "goal_description": f"Strategy V2 launch for angle {angle_name}",
                    "temporal_workflow_id": workflow_id,
                    "temporal_run_id": workflow.info().run_id,
                },
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=_RETRY_POLICY,
            )
            campaign_id = _require_nonempty_string(campaign_result.get("campaign_id"), field_name="campaign_id")
            campaign_ids.append(campaign_id)

            launch_artifacts = await workflow.execute_activity(
                create_strategy_v2_launch_artifacts_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": campaign_id,
                    "angle_id": angle_id,
                    "angle_name": angle_name,
                    "selected_ums_id": selected_ums_id,
                    "selected_variant_id": selected_variant_id,
                    "channels": input.channels,
                    "asset_brief_types": input.asset_brief_types,
                    "strategy_v2_packet": strategy_v2_packet,
                    "strategy_v2_copy_context": strategy_v2_copy_context,
                    "created_by_user": input.operator_user_id,
                },
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=_RETRY_POLICY,
            )
            experiment_specs = _normalize_dict_rows(
                launch_artifacts.get("experiment_specs"),
                field_name="launch_artifacts.experiment_specs",
            )

            funnels_result = await workflow.execute_activity(
                create_funnels_from_experiments_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": campaign_id,
                    "experiment_specs": experiment_specs,
                    "pages": DEFAULT_FUNNEL_PAGES,
                    "funnel_name_prefix": f"{campaign_name} Funnel",
                    "idea_workspace_id": workflow_id,
                    "actor_user_id": input.operator_user_id,
                    "generate_ai_drafts": True,
                    "generate_testimonials": True,
                    "async_media_enrichment": False,
                    "temporal_workflow_id": workflow_id,
                    "temporal_run_id": workflow.info().run_id,
                    "strategy_v2_packet": strategy_v2_packet,
                    "strategy_v2_copy_context": strategy_v2_copy_context,
                    "require_pinned_strategy_v2_context": True,
                    "require_shopify_connection": True,
                },
                schedule_to_close_timeout=timedelta(
                    minutes=max(35, settings.FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES)
                ),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=_FUNNEL_GENERATION_RETRY_POLICY,
            )
            funnels_payload = _require_dict(funnels_result, field_name="funnels_result")
            media_jobs = _extract_media_enrichment_jobs(funnels_payload)
            if media_jobs:
                media_enrichment_workflows.extend(
                    await _start_media_enrichment_workflows(
                        org_id=input.org_id,
                        media_enrichment_jobs=media_jobs,
                        default_actor_user_id=input.operator_user_id,
                        default_workflow_run_id=workflow_run_id,
                    )
                )
            funnel_id = _extract_funnel_id(funnels_payload)

            launch_record = await workflow.execute_activity(
                persist_strategy_v2_launch_record_activity,
                {
                    "org_id": input.org_id,
                    "source_strategy_v2_workflow_run_id": input.source_strategy_v2_workflow_run_id,
                    "source_strategy_v2_temporal_workflow_id": input.source_strategy_v2_temporal_workflow_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": campaign_id,
                    "funnel_id": funnel_id,
                    "angle_id": angle_id,
                    "angle_run_id": angle_run_id,
                    "selected_ums_id": selected_ums_id,
                    "selected_variant_id": selected_variant_id,
                    "source_stage3_artifact_id": source_stage3_artifact_id,
                    "source_offer_artifact_id": source_offer_artifact_id,
                    "source_copy_artifact_id": source_copy_artifact_id,
                    "source_copy_context_artifact_id": source_copy_context_artifact_id,
                    "launch_type": launch_type,
                    "launch_key": launch_key,
                    "launch_index": launch_item.get("launch_index"),
                    "launch_workflow_run_id": workflow_run_id,
                    "launch_temporal_workflow_id": workflow_id,
                    "created_by_user": input.operator_user_id,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY_POLICY,
            )
            launch_records.append(_require_dict(launch_record, field_name="launch_record"))

        return {
            "campaign_ids": campaign_ids,
            "funnel_workflow_run_ids": [workflow_run_id],
            "launch_records": launch_records,
            "media_enrichment_workflows": media_enrichment_workflows,
        }


@workflow.defn
class StrategyV2AngleIterationWorkflow:
    @workflow.run
    async def run(self, input: StrategyV2AngleIterationInput) -> dict[str, Any]:
        if not input.ums_launch_items:
            raise RuntimeError("ums_launch_items are required.")

        workflow_id = workflow.info().workflow_id
        workflow_run_id = input.launch_workflow_run_id
        stage1 = _require_dict(input.stage1, field_name="stage1")
        ranked_candidates = _normalize_dict_rows(input.ranked_angle_candidates, field_name="ranked_angle_candidates")
        selected_angle = _require_dict(input.selected_angle, field_name="selected_angle")
        offer_pipeline_payload = _require_dict(input.offer_pipeline_payload, field_name="offer_pipeline_payload")
        angle_synthesis_payload = _require_dict(input.angle_synthesis_payload, field_name="angle_synthesis_payload")
        offer_operator_inputs = _require_dict(input.offer_operator_inputs, field_name="offer_operator_inputs")

        angle_id = _require_nonempty_string(selected_angle.get("angle_id"), field_name="selected_angle.angle_id")
        angle_name = _require_nonempty_string(selected_angle.get("angle_name"), field_name="selected_angle.angle_name")

        stage2_result = await workflow.execute_activity(
            apply_strategy_v2_angle_selection_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "workflow_run_id": workflow_run_id,
                "stage1": stage1,
                "angle_selection_decision": {
                    "operator_user_id": input.operator_user_id,
                    "decision_mode": "manual",
                    "selected_angle": selected_angle,
                    "rejected_angle_ids": [
                        str((row.get("angle") or row).get("angle_id"))
                        for row in ranked_candidates
                        if isinstance((row.get("angle") or row), dict)
                        and str((row.get("angle") or row).get("angle_id")) != angle_id
                    ],
                    "reviewed_candidate_ids": [angle_id],
                    "attestation": _build_attestation_payload(),
                    "operator_note": "Replayed the selected angle to run this additional UMS branch with reviewed evidence.",
                },
                "ranked_angle_candidates": ranked_candidates,
            },
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=_RETRY_POLICY,
        )
        stage2 = _require_dict(stage2_result.get("stage2"), field_name="stage2_result.stage2")
        offer_data_readiness_result = await workflow.execute_activity(
            validate_strategy_v2_offer_data_readiness_activity,
            {
                "org_id": input.org_id,
                "client_id": input.client_id,
                "product_id": input.product_id,
                "campaign_id": input.campaign_id,
                "workflow_run_id": workflow_run_id,
                "onboarding_payload_id": input.onboarding_payload_id,
                "offer_pipeline_output": offer_pipeline_payload,
            },
            schedule_to_close_timeout=timedelta(minutes=10),
            retry_policy=_RETRY_POLICY,
        )
        offer_data_readiness_payload = _require_dict(
            offer_data_readiness_result,
            field_name="offer_data_readiness_result",
        )
        readiness_status = str(offer_data_readiness_payload.get("status") or "").strip().lower()
        if readiness_status != "ready":
            raise RuntimeError(
                "Offer data readiness blocked angle iteration launch. "
                f"missing_fields={offer_data_readiness_payload.get('missing_fields')}; "
                f"inconsistent_fields={offer_data_readiness_payload.get('inconsistent_fields')}"
            )

        campaign_ids: list[str] = [input.campaign_id]
        launch_records: list[dict[str, Any]] = []
        media_enrichment_workflows: list[dict[str, Any]] = []

        for launch_item in input.ums_launch_items:
            launch_key = _require_nonempty_string(launch_item.get("launch_key"), field_name="launch_item.launch_key")
            selected_ums_id = _require_nonempty_string(
                launch_item.get("selected_ums_id"),
                field_name="launch_item.selected_ums_id",
            )
            pair_payload = _require_dict(launch_item.get("pair"), field_name="launch_item.pair")
            pair_id = _require_nonempty_string(pair_payload.get("pair_id"), field_name="launch_item.pair.pair_id")

            ranked_pairs = _normalize_dict_rows(
                _require_dict(
                    offer_pipeline_payload.get("pair_scoring"),
                    field_name="offer_pipeline_payload.pair_scoring",
                ).get("ranked_pairs"),
                field_name="offer_pipeline_payload.pair_scoring.ranked_pairs",
            )

            offer_variants_result = await workflow.execute_activity(
                build_strategy_v2_offer_variants_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": workflow_run_id,
                    "stage2": stage2,
                    "offer_pipeline_output": offer_pipeline_payload,
                    "offer_data_readiness": offer_data_readiness_payload,
                    "ump_ums_selection_decision": _build_pair_decision(
                        operator_user_id=input.operator_user_id,
                        pair_id=pair_id,
                        ranked_pairs=ranked_pairs,
                    ),
                },
                schedule_to_close_timeout=timedelta(minutes=20),
                retry_policy=_RETRY_POLICY,
            )
            offer_variants_payload = _require_dict(offer_variants_result, field_name="offer_variants_result")
            variants = _normalize_dict_rows(
                offer_variants_payload.get("variants"),
                field_name="offer_variants_result.variants",
            )
            selected_variant_id = _select_best_offer_variant(offer_variants_payload)

            stage3_result = await workflow.execute_activity(
                finalize_strategy_v2_offer_winner_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": workflow_run_id,
                    "stage2": stage2,
                    "offer_variants_output": offer_variants_payload,
                    "offer_pipeline_output": offer_pipeline_payload,
                    "offer_winner_decision": _build_offer_winner_decision(
                        operator_user_id=input.operator_user_id,
                        variant_id=selected_variant_id,
                        variants=variants,
                    ),
                    "onboarding_payload_id": input.onboarding_payload_id,
                    "brand_voice_notes": _require_nonempty_string(
                        offer_operator_inputs.get("brand_voice_notes"),
                        field_name="offer_operator_inputs.brand_voice_notes",
                    ),
                    "compliance_notes": None,
                },
                schedule_to_close_timeout=timedelta(minutes=10),
                retry_policy=_RETRY_POLICY,
            )
            stage3_payload = _require_dict(stage3_result.get("stage3"), field_name="stage3_result.stage3")
            copy_context_payload = _require_dict(
                stage3_result.get("copy_context"),
                field_name="stage3_result.copy_context",
            )
            source_stage3_artifact_id = _require_nonempty_string(
                stage3_result.get("stage3_artifact_id"),
                field_name="stage3_result.stage3_artifact_id",
            )
            source_offer_artifact_id = _require_nonempty_string(
                stage3_result.get("offer_artifact_id"),
                field_name="stage3_result.offer_artifact_id",
            )
            source_copy_context_artifact_id = _require_nonempty_string(
                stage3_result.get("copy_context_artifact_id"),
                field_name="stage3_result.copy_context_artifact_id",
            )
            source_awareness_matrix_artifact_id = (
                _require_nonempty_string(
                    stage3_result.get("awareness_matrix_artifact_id"),
                    field_name="stage3_result.awareness_matrix_artifact_id",
                )
                if stage3_result.get("awareness_matrix_artifact_id") is not None
                else None
            )

            copy_result = await workflow.execute_activity(
                run_strategy_v2_copy_pipeline_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": workflow_run_id,
                    "stage3": stage3_payload,
                    "copy_context": copy_context_payload,
                    "operator_user_id": input.operator_user_id,
                    "copy_generation_mode": _COPY_WORKFLOW_GENERATION_MODE,
                },
                schedule_to_close_timeout=timedelta(
                    minutes=max(35, settings.FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES)
                ),
                retry_policy=_RETRY_POLICY,
            )
            copy_payload = _require_dict(copy_result.get("copy_payload"), field_name="copy_result.copy_payload")
            source_copy_artifact_id = _require_nonempty_string(
                copy_result.get("copy_artifact_id"),
                field_name="copy_result.copy_artifact_id",
            )

            await workflow.execute_activity(
                finalize_strategy_v2_copy_approval_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": workflow_run_id,
                    "copy_payload": copy_payload,
                    "final_approval_decision": _build_final_copy_decision(
                        operator_user_id=input.operator_user_id,
                        reviewed_candidate_id=source_copy_artifact_id,
                    ),
                },
                schedule_to_close_timeout=timedelta(minutes=5),
                retry_policy=_RETRY_POLICY,
            )

            awareness_payload = stage3_result.get("awareness_matrix")
            awareness_matrix_payload = awareness_payload if isinstance(awareness_payload, dict) else None
            strategy_v2_packet = build_strategy_v2_downstream_packet(
                stage3=stage3_payload,
                offer={
                    "stage3": stage3_payload,
                    "selected_variant": next(
                        (
                            variant
                            for variant in variants
                            if str(variant.get("variant_id")) == selected_variant_id
                        ),
                        {},
                    ),
                    "selected_variant_score": next(
                        (
                            row
                            for row in _normalize_dict_rows(
                                _require_dict(
                                    offer_variants_payload.get("composite_results"),
                                    field_name="offer_variants_output.composite_results",
                                ).get("variants"),
                                field_name="offer_variants_output.composite_results.variants",
                            )
                            if str(row.get("variant_id")) == selected_variant_id
                        ),
                        None,
                    ),
                    "decision": _build_offer_winner_decision(
                        operator_user_id=input.operator_user_id,
                        variant_id=selected_variant_id,
                        variants=variants,
                    ),
                },
                copy=copy_payload,
                copy_context=copy_context_payload,
                awareness_angle_matrix=awareness_matrix_payload,
                artifact_ids={
                    "stage3": source_stage3_artifact_id,
                    "offer": source_offer_artifact_id,
                    "copy": source_copy_artifact_id,
                    "copy_context": source_copy_context_artifact_id,
                    "awareness_angle_matrix": source_awareness_matrix_artifact_id,
                },
            )
            if not isinstance(strategy_v2_packet, dict):
                raise RuntimeError("Failed to build downstream packet for additional UMS launch.")
            strategy_v2_packet["launch_metadata"] = {
                "launch_type": "additional_ums",
                "launch_key": launch_key,
                "source_strategy_v2_workflow_run_id": input.source_strategy_v2_workflow_run_id,
                "source_strategy_v2_temporal_workflow_id": input.source_strategy_v2_temporal_workflow_id,
                "angle_id": angle_id,
                "selected_ums_id": selected_ums_id,
                "selected_variant_id": selected_variant_id,
            }

            launch_artifacts = await workflow.execute_activity(
                create_strategy_v2_launch_artifacts_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "angle_id": angle_id,
                    "angle_name": angle_name,
                    "selected_ums_id": selected_ums_id,
                    "selected_variant_id": selected_variant_id,
                    "channels": input.channels,
                    "asset_brief_types": input.asset_brief_types,
                    "strategy_v2_packet": strategy_v2_packet,
                    "strategy_v2_copy_context": copy_context_payload,
                    "created_by_user": input.operator_user_id,
                },
                schedule_to_close_timeout=timedelta(minutes=3),
                retry_policy=_RETRY_POLICY,
            )
            experiment_specs = _normalize_dict_rows(
                launch_artifacts.get("experiment_specs"),
                field_name="launch_artifacts.experiment_specs",
            )
            funnel_name_prefix = f"{input.launch_name_prefix} · {selected_ums_id}"
            funnels_result = await workflow.execute_activity(
                create_funnels_from_experiments_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "experiment_specs": experiment_specs,
                    "pages": DEFAULT_FUNNEL_PAGES,
                    "funnel_name_prefix": funnel_name_prefix,
                    "idea_workspace_id": workflow_id,
                    "actor_user_id": input.operator_user_id,
                    "generate_ai_drafts": True,
                    "generate_testimonials": True,
                    "async_media_enrichment": False,
                    "temporal_workflow_id": workflow_id,
                    "temporal_run_id": workflow.info().run_id,
                    "strategy_v2_packet": strategy_v2_packet,
                    "strategy_v2_copy_context": copy_context_payload,
                    "require_pinned_strategy_v2_context": True,
                    "require_shopify_connection": True,
                },
                schedule_to_close_timeout=timedelta(
                    minutes=max(35, settings.FUNNEL_MEDIA_ENRICHMENT_ACTIVITY_TIMEOUT_MINUTES)
                ),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=_FUNNEL_GENERATION_RETRY_POLICY,
            )
            funnels_payload = _require_dict(funnels_result, field_name="funnels_result")
            media_jobs = _extract_media_enrichment_jobs(funnels_payload)
            if media_jobs:
                media_enrichment_workflows.extend(
                    await _start_media_enrichment_workflows(
                        org_id=input.org_id,
                        media_enrichment_jobs=media_jobs,
                        default_actor_user_id=input.operator_user_id,
                        default_workflow_run_id=workflow_run_id,
                    )
                )
            funnel_id = _extract_funnel_id(funnels_payload)

            launch_record = await workflow.execute_activity(
                persist_strategy_v2_launch_record_activity,
                {
                    "org_id": input.org_id,
                    "source_strategy_v2_workflow_run_id": input.source_strategy_v2_workflow_run_id,
                    "source_strategy_v2_temporal_workflow_id": input.source_strategy_v2_temporal_workflow_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "funnel_id": funnel_id,
                    "angle_id": angle_id,
                    "angle_run_id": input.base_angle_run_id,
                    "selected_ums_id": selected_ums_id,
                    "selected_variant_id": selected_variant_id,
                    "source_stage3_artifact_id": source_stage3_artifact_id,
                    "source_offer_artifact_id": source_offer_artifact_id,
                    "source_copy_artifact_id": source_copy_artifact_id,
                    "source_copy_context_artifact_id": source_copy_context_artifact_id,
                    "launch_type": "additional_ums",
                    "launch_key": launch_key,
                    "launch_index": None,
                    "launch_workflow_run_id": workflow_run_id,
                    "launch_temporal_workflow_id": workflow_id,
                    "created_by_user": input.operator_user_id,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
                retry_policy=_RETRY_POLICY,
            )
            launch_records.append(_require_dict(launch_record, field_name="launch_record"))

        return {
            "campaign_ids": campaign_ids,
            "funnel_workflow_run_ids": [workflow_run_id],
            "launch_records": launch_records,
            "media_enrichment_workflows": media_enrichment_workflows,
        }
