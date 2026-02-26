from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.strategy_v2_activities import (
        apply_strategy_v2_angle_selection_activity,
        build_strategy_v2_offer_variants_activity,
        build_strategy_v2_foundational_research_activity,
        build_strategy_v2_stage0_activity,
        check_strategy_v2_enabled_activity,
        ensure_strategy_v2_workflow_run_activity,
        finalize_strategy_v2_competitor_assets_confirmation_activity,
        finalize_strategy_v2_copy_approval_activity,
        finalize_strategy_v2_offer_winner_activity,
        finalize_strategy_v2_research_proceed_activity,
        mark_strategy_v2_failed_activity,
        prepare_strategy_v2_competitor_asset_candidates_activity,
        run_strategy_v2_copy_pipeline_activity,
        run_strategy_v2_offer_pipeline_activity,
        run_strategy_v2_voc_angle_pipeline_activity,
    )


@dataclass
class StrategyV2Input:
    org_id: str
    client_id: str
    product_id: str
    onboarding_payload_id: Optional[str] = None
    campaign_id: Optional[str] = None
    operator_user_id: Optional[str] = None
    stage0_overrides: Optional[Dict[str, Any]] = None
    business_model: Optional[str] = None
    funnel_position: Optional[str] = None
    target_platforms: Optional[list[str]] = None
    target_regions: Optional[list[str]] = None
    existing_proof_assets: Optional[list[str]] = None
    brand_voice_notes: Optional[str] = None
    compliance_notes: Optional[str] = None


@workflow.defn
class StrategyV2Workflow:
    def __init__(self) -> None:
        self._workflow_run_id: Optional[str] = None
        self._current_stage: str = "not_started"
        self._pending_signal_type: Optional[str] = None
        self._pending_decision_payload: Optional[Dict[str, Any]] = None
        self._scored_candidate_summaries: Dict[str, Any] = {}
        self._artifact_refs: Dict[str, Any] = {}
        self._stop_requested = False

        self._angle_selection_decision: Optional[Dict[str, Any]] = None
        self._research_proceed_decision: Optional[Dict[str, Any]] = None
        self._competitor_asset_confirmation_decision: Optional[Dict[str, Any]] = None
        self._ump_ums_selection_decision: Optional[Dict[str, Any]] = None
        self._offer_winner_decision: Optional[Dict[str, Any]] = None
        self._final_approval_decision: Optional[Dict[str, Any]] = None

    @staticmethod
    def _is_valid_str_list(value: Any) -> bool:
        return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)

    @staticmethod
    def _has_required_attestation(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if str(payload.get("decision_mode") or "").strip().lower() not in {"manual", "internal_automation"}:
            return False
        attestation = payload.get("attestation")
        return (
            isinstance(attestation, dict)
            and isinstance(attestation.get("reviewed_evidence"), bool)
            and isinstance(attestation.get("understands_impact"), bool)
        )

    def _is_signal_payload_ready(self, *, signal_type: str) -> bool:
        if signal_type == "strategy_v2_proceed_research":
            payload = self._research_proceed_decision
            return (
                self._has_required_attestation(payload)
                and isinstance(payload.get("proceed"), bool)
            )
        if signal_type == "strategy_v2_confirm_competitor_assets":
            payload = self._competitor_asset_confirmation_decision
            return (
                self._has_required_attestation(payload)
                and self._is_valid_str_list(payload.get("confirmed_asset_refs"))
                and self._is_valid_str_list(payload.get("reviewed_candidate_ids"))
            )
        if signal_type == "strategy_v2_select_angle":
            payload = self._angle_selection_decision
            selected_angle = payload.get("selected_angle") if isinstance(payload, dict) else None
            return (
                self._has_required_attestation(payload)
                and isinstance(selected_angle, dict)
                and isinstance(selected_angle.get("angle_id"), str)
                and bool(selected_angle.get("angle_id").strip())
                and self._is_valid_str_list(payload.get("reviewed_candidate_ids"))
            )
        if signal_type == "strategy_v2_select_ump_ums":
            payload = self._ump_ums_selection_decision
            return (
                self._has_required_attestation(payload)
                and isinstance(payload.get("pair_id"), str)
                and bool(str(payload.get("pair_id")).strip())
                and self._is_valid_str_list(payload.get("reviewed_candidate_ids"))
            )
        if signal_type == "strategy_v2_select_offer_winner":
            payload = self._offer_winner_decision
            return (
                self._has_required_attestation(payload)
                and isinstance(payload.get("variant_id"), str)
                and bool(str(payload.get("variant_id")).strip())
                and self._is_valid_str_list(payload.get("reviewed_candidate_ids"))
            )
        if signal_type == "strategy_v2_approve_final_copy":
            payload = self._final_approval_decision
            return (
                self._has_required_attestation(payload)
                and isinstance(payload.get("approved"), bool)
                and self._is_valid_str_list(payload.get("reviewed_candidate_ids"))
            )
        return False

    def _record_step_payload_artifact_ref(self, *, step_key: str, artifact_id: Any) -> None:
        if not isinstance(artifact_id, str) or not artifact_id:
            return
        refs = self._artifact_refs.get("step_payload_artifact_ids")
        if not isinstance(refs, dict):
            refs = {}
            self._artifact_refs["step_payload_artifact_ids"] = refs
        refs[step_key] = artifact_id
        normalized_step_key = step_key.replace("-", "_")
        self._artifact_refs[f"step_payload_{normalized_step_key}_artifact_id"] = artifact_id

    @workflow.signal
    def strategy_v2_proceed_research(self, payload: Any) -> None:
        self._research_proceed_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def strategy_v2_confirm_competitor_assets(self, payload: Any) -> None:
        self._competitor_asset_confirmation_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def strategy_v2_select_angle(self, payload: Any) -> None:
        self._angle_selection_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def strategy_v2_select_ump_ums(self, payload: Any) -> None:
        self._ump_ums_selection_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def strategy_v2_select_offer_winner(self, payload: Any) -> None:
        self._offer_winner_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def strategy_v2_approve_final_copy(self, payload: Any) -> None:
        self._final_approval_decision = payload if isinstance(payload, dict) else None

    @workflow.signal
    def stop(self, payload: Any) -> None:
        _ = payload
        self._stop_requested = True

    @workflow.query
    def strategy_v2_state(self) -> Dict[str, Any]:
        return {
            "workflow_run_id": self._workflow_run_id,
            "current_stage": self._current_stage,
            "pending_signal_type": self._pending_signal_type,
            "required_signal_type": self._pending_signal_type,
            "pending_decision_payload": self._pending_decision_payload,
            "scored_candidate_summaries": self._scored_candidate_summaries,
            "artifact_refs": self._artifact_refs,
            "stop_requested": self._stop_requested,
        }

    async def _mark_failed(self, *, org_id: str, error_message: str) -> None:
        if not self._workflow_run_id:
            return
        await workflow.execute_activity(
            mark_strategy_v2_failed_activity,
            {
                "org_id": org_id,
                "workflow_run_id": self._workflow_run_id,
                "error_message": error_message,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
        )

    async def _wait_for_signal(self, *, signal_type: str) -> None:
        self._pending_signal_type = signal_type
        await workflow.wait_condition(
            lambda: self._stop_requested or self._is_signal_payload_ready(signal_type=signal_type)
        )
        if self._stop_requested:
            raise RuntimeError("Strategy V2 workflow was stopped by operator signal.")
        self._pending_signal_type = None

    @workflow.run
    async def run(self, input: StrategyV2Input) -> Dict[str, Any]:
        try:
            enabled_result = await workflow.execute_activity(
                check_strategy_v2_enabled_activity,
                {"org_id": input.org_id, "client_id": input.client_id},
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            enabled = bool(enabled_result.get("enabled")) if isinstance(enabled_result, dict) else False
            if not enabled:
                raise RuntimeError(
                    "Strategy V2 workflow cannot start because strategy_v2_enabled is false for this tenant/client."
                )

            ensure_result = await workflow.execute_activity(
                ensure_strategy_v2_workflow_run_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "temporal_workflow_id": workflow.info().workflow_id,
                    "temporal_run_id": workflow.info().run_id,
                },
                schedule_to_close_timeout=timedelta(minutes=2),
            )
            if not isinstance(ensure_result, dict) or not isinstance(ensure_result.get("workflow_run_id"), str):
                raise RuntimeError("Failed to initialize workflow_run_id for Strategy V2 workflow.")
            self._workflow_run_id = str(ensure_result["workflow_run_id"])

            self._current_stage = "v2-01"
            stage0_result = await workflow.execute_activity(
                build_strategy_v2_stage0_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "onboarding_payload_id": input.onboarding_payload_id,
                    "stage0_overrides": input.stage0_overrides or {},
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            if not isinstance(stage0_result, dict):
                raise RuntimeError("Strategy V2 stage0 activity returned an invalid payload.")
            stage0 = stage0_result.get("stage0")
            if not isinstance(stage0, dict):
                raise RuntimeError("Strategy V2 stage0 payload is missing.")
            self._artifact_refs["stage0_artifact_id"] = stage0_result.get("stage0_artifact_id")
            self._record_step_payload_artifact_ref(
                step_key="v2-01",
                artifact_id=stage0_result.get("step_payload_artifact_id"),
            )

            self._current_stage = "v2-02"
            foundational_result = await workflow.execute_activity(
                build_strategy_v2_foundational_research_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "onboarding_payload_id": input.onboarding_payload_id,
                },
                schedule_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=20),
            )
            if not isinstance(foundational_result, dict):
                raise RuntimeError("Strategy V2 foundational research activity returned an invalid payload.")
            stage1 = foundational_result.get("stage1")
            if not isinstance(stage1, dict):
                raise RuntimeError("Strategy V2 foundational research activity did not return stage1.")
            precanon_research = foundational_result.get("precanon_research")
            if not isinstance(precanon_research, dict):
                raise RuntimeError("Strategy V2 foundational research activity did not return precanon_research.")
            self._artifact_refs["stage1_artifact_id"] = foundational_result.get("stage1_artifact_id")
            foundational_step_payload_map = foundational_result.get("step_payload_artifact_ids")
            if isinstance(foundational_step_payload_map, dict):
                for step_key, artifact_id in foundational_step_payload_map.items():
                    if isinstance(step_key, str):
                        self._record_step_payload_artifact_ref(step_key=step_key, artifact_id=artifact_id)

            self._pending_decision_payload = {
                "stage1": stage1,
                "foundational_step_summaries": precanon_research.get("step_summaries"),
            }
            self._current_stage = "v2-02a"
            await self._wait_for_signal(signal_type="strategy_v2_proceed_research")
            if not isinstance(self._research_proceed_decision, dict):
                raise RuntimeError("Research proceed decision payload is missing or invalid.")

            research_proceed_result = await workflow.execute_activity(
                finalize_strategy_v2_research_proceed_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage1": stage1,
                    "research_proceed_decision": self._research_proceed_decision,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            if not isinstance(research_proceed_result, dict):
                raise RuntimeError("Research proceed finalization returned an invalid payload.")
            self._record_step_payload_artifact_ref(
                step_key="v2-02a",
                artifact_id=research_proceed_result.get("step_payload_artifact_id"),
            )

            candidate_assets_result = await workflow.execute_activity(
                prepare_strategy_v2_competitor_asset_candidates_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage1": stage1,
                },
                # Apify ingestion may fan out across multiple actors and exceed the
                # short foundational timeout budget under real production source mixes.
                schedule_to_close_timeout=timedelta(minutes=30),
            )
            if not isinstance(candidate_assets_result, dict):
                raise RuntimeError("Competitor asset candidate preparation returned an invalid payload.")
            competitor_asset_candidates = candidate_assets_result.get("candidates")
            if not isinstance(competitor_asset_candidates, list) or len(competitor_asset_candidates) < 3:
                raise RuntimeError(
                    "Competitor asset candidate preparation did not return at least 3 scored candidates."
                )
            candidate_summary = candidate_assets_result.get("candidate_summary")
            apify_context = (
                candidate_assets_result.get("apify_context")
                if isinstance(candidate_assets_result.get("apify_context"), dict)
                else {}
            )
            self._scored_candidate_summaries["competitor_assets"] = competitor_asset_candidates
            self._record_step_payload_artifact_ref(
                step_key="v2-02i",
                artifact_id=candidate_assets_result.get("step_payload_artifact_id"),
            )

            self._pending_decision_payload = {
                "competitor_urls": stage1.get("competitor_urls"),
                "candidates": competitor_asset_candidates,
                "candidate_summary": candidate_summary,
            }
            self._current_stage = "v2-02b"
            await self._wait_for_signal(signal_type="strategy_v2_confirm_competitor_assets")
            if not isinstance(self._competitor_asset_confirmation_decision, dict):
                raise RuntimeError("Competitor asset confirmation decision payload is missing or invalid.")

            competitor_assets_result = await workflow.execute_activity(
                finalize_strategy_v2_competitor_assets_confirmation_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage1": stage1,
                    "competitor_asset_candidates": competitor_asset_candidates,
                    "candidate_summary": candidate_summary if isinstance(candidate_summary, dict) else None,
                    "competitor_asset_confirmation_decision": self._competitor_asset_confirmation_decision,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            if not isinstance(competitor_assets_result, dict):
                raise RuntimeError("Competitor asset confirmation finalization returned an invalid payload.")
            confirmed_competitor_assets = competitor_assets_result.get("confirmed_asset_refs")
            if not isinstance(confirmed_competitor_assets, list) or not confirmed_competitor_assets:
                raise RuntimeError("Competitor asset confirmation did not return confirmed asset refs.")
            self._record_step_payload_artifact_ref(
                step_key="v2-02b",
                artifact_id=competitor_assets_result.get("step_payload_artifact_id"),
            )
            self._pending_decision_payload = None

            self._current_stage = "v2-03..v2-06"
            voc_angle_result = await workflow.execute_activity(
                run_strategy_v2_voc_angle_pipeline_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "onboarding_payload_id": input.onboarding_payload_id,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": foundational_result.get("stage1_artifact_id"),
                    "existing_step_payload_artifact_ids": foundational_step_payload_map or {},
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "apify_context": apify_context,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=120),
                heartbeat_timeout=timedelta(minutes=20),
            )
            if not isinstance(voc_angle_result, dict):
                raise RuntimeError("Strategy V2 VOC/angle activity returned an invalid payload.")
            self._artifact_refs["stage1_artifact_id"] = voc_angle_result.get("stage1_artifact_id")
            step_payload_map = voc_angle_result.get("step_payload_artifact_ids")
            if isinstance(step_payload_map, dict):
                for step_key, artifact_id in step_payload_map.items():
                    if isinstance(step_key, str):
                        self._record_step_payload_artifact_ref(step_key=step_key, artifact_id=artifact_id)

            ranked_angle_candidates = voc_angle_result.get("ranked_angle_candidates")
            if not isinstance(ranked_angle_candidates, list) or not ranked_angle_candidates:
                raise RuntimeError(
                    "Strategy V2 angle synthesis did not produce ranked candidates for angle selection."
                )
            self._scored_candidate_summaries["angles"] = ranked_angle_candidates
            self._pending_decision_payload = {"candidates": ranked_angle_candidates}

            self._current_stage = "v2-07"
            await self._wait_for_signal(signal_type="strategy_v2_select_angle")
            if not isinstance(self._angle_selection_decision, dict):
                raise RuntimeError("Angle selection decision payload is missing or invalid.")

            stage2_result = await workflow.execute_activity(
                apply_strategy_v2_angle_selection_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage1": stage1,
                    "angle_selection_decision": self._angle_selection_decision,
                    "ranked_angle_candidates": ranked_angle_candidates,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            if not isinstance(stage2_result, dict):
                raise RuntimeError("Strategy V2 angle selection activity returned an invalid payload.")
            stage2 = stage2_result.get("stage2")
            if not isinstance(stage2, dict):
                raise RuntimeError("Strategy V2 stage2 payload is missing.")
            self._artifact_refs["stage2_artifact_id"] = stage2_result.get("stage2_artifact_id")
            self._record_step_payload_artifact_ref(
                step_key="v2-07",
                artifact_id=stage2_result.get("step_payload_artifact_id"),
            )
            self._pending_decision_payload = None

            self._current_stage = "v2-08"
            offer_pipeline_output = await workflow.execute_activity(
                run_strategy_v2_offer_pipeline_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage2": stage2,
                    "competitor_analysis": voc_angle_result.get("competitor_analysis"),
                    "voc_observations": voc_angle_result.get("voc_observations"),
                    "voc_scored": voc_angle_result.get("voc_scored"),
                    "angle_synthesis": {"ranked_candidates": ranked_angle_candidates},
                    "business_model": input.business_model or "",
                    "funnel_position": input.funnel_position or "",
                    "target_platforms": input.target_platforms or [],
                    "target_regions": input.target_regions or [],
                    "existing_proof_assets": input.existing_proof_assets or [],
                    "proof_asset_candidates": voc_angle_result.get("proof_asset_candidates"),
                    "brand_voice_notes": input.brand_voice_notes or "",
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=90),
                heartbeat_timeout=timedelta(minutes=20),
            )
            if not isinstance(offer_pipeline_output, dict):
                raise RuntimeError("Strategy V2 offer pipeline returned an invalid payload.")
            self._artifact_refs["awareness_matrix_artifact_id"] = offer_pipeline_output.get(
                "awareness_matrix_artifact_id"
            )
            self._record_step_payload_artifact_ref(
                step_key="v2-08",
                artifact_id=offer_pipeline_output.get("step_payload_artifact_id"),
            )

            pair_scoring = offer_pipeline_output.get("pair_scoring")
            ranked_pairs = pair_scoring.get("ranked_pairs") if isinstance(pair_scoring, dict) else None
            if not isinstance(ranked_pairs, list) or not ranked_pairs:
                raise RuntimeError("Offer pipeline did not return ranked UMP/UMS pairs for HITL selection.")
            self._scored_candidate_summaries["ump_ums_pairs"] = ranked_pairs
            self._pending_decision_payload = {
                "candidates": ranked_pairs,
                "proof_asset_candidates": offer_pipeline_output.get("proof_asset_candidates"),
            }

            await self._wait_for_signal(signal_type="strategy_v2_select_ump_ums")
            if not isinstance(self._ump_ums_selection_decision, dict):
                raise RuntimeError("UMP/UMS selection decision payload is missing or invalid.")

            self._current_stage = "v2-08b"
            offer_variants_output = await workflow.execute_activity(
                build_strategy_v2_offer_variants_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage2": stage2,
                    "offer_pipeline_output": offer_pipeline_output,
                    "ump_ums_selection_decision": self._ump_ums_selection_decision,
                },
                schedule_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=20),
            )
            if not isinstance(offer_variants_output, dict):
                raise RuntimeError("Offer variant scoring returned an invalid payload.")
            self._record_step_payload_artifact_ref(
                step_key="v2-08b",
                artifact_id=offer_variants_output.get("step_payload_artifact_id"),
            )

            composite_results = offer_variants_output.get("composite_results")
            ranked_variants = composite_results.get("variants") if isinstance(composite_results, dict) else None
            if not isinstance(ranked_variants, list) or not ranked_variants:
                raise RuntimeError("Offer variant scoring did not return ranked variants for HITL selection.")
            self._scored_candidate_summaries["offer_variants"] = ranked_variants
            self._pending_decision_payload = {"candidates": ranked_variants}

            self._current_stage = "v2-09"
            await self._wait_for_signal(signal_type="strategy_v2_select_offer_winner")
            if not isinstance(self._offer_winner_decision, dict):
                raise RuntimeError("Offer winner decision payload is missing or invalid.")

            stage3_result = await workflow.execute_activity(
                finalize_strategy_v2_offer_winner_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage2": stage2,
                    "offer_pipeline_output": offer_pipeline_output,
                    "offer_variants_output": offer_variants_output,
                    "offer_winner_decision": self._offer_winner_decision,
                    "onboarding_payload_id": input.onboarding_payload_id,
                    "brand_voice_notes": input.brand_voice_notes or "",
                    "compliance_notes": input.compliance_notes or "",
                },
                schedule_to_close_timeout=timedelta(minutes=20),
            )
            if not isinstance(stage3_result, dict):
                raise RuntimeError("Offer winner finalization returned an invalid payload.")
            stage3 = stage3_result.get("stage3")
            copy_context = stage3_result.get("copy_context")
            if not isinstance(stage3, dict) or not isinstance(copy_context, dict):
                raise RuntimeError("Stage3 or copy context output is missing after offer winner selection.")
            self._artifact_refs["stage3_artifact_id"] = stage3_result.get("stage3_artifact_id")
            self._artifact_refs["copy_context_artifact_id"] = stage3_result.get("copy_context_artifact_id")
            if stage3_result.get("awareness_matrix_artifact_id") is not None:
                self._artifact_refs["awareness_matrix_artifact_id"] = stage3_result.get(
                    "awareness_matrix_artifact_id"
                )
            self._record_step_payload_artifact_ref(
                step_key="v2-09",
                artifact_id=stage3_result.get("step_payload_artifact_id"),
            )
            self._pending_decision_payload = None

            self._current_stage = "v2-10"
            copy_result = await workflow.execute_activity(
                run_strategy_v2_copy_pipeline_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage3": stage3,
                    "copy_context": copy_context,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=90),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(
                    maximum_attempts=6,
                    initial_interval=timedelta(minutes=1),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=8),
                    non_retryable_error_types=[
                        "StrategyV2DecisionError",
                        "StrategyV2MissingContextError",
                        "StrategyV2SchemaValidationError",
                    ],
                ),
            )
            if not isinstance(copy_result, dict):
                raise RuntimeError("Copy pipeline returned an invalid payload.")
            copy_payload = copy_result.get("copy_payload")
            if not isinstance(copy_payload, dict):
                raise RuntimeError("Copy pipeline did not return copy payload.")
            self._artifact_refs["copy_artifact_id"] = copy_result.get("copy_artifact_id")
            self._record_step_payload_artifact_ref(
                step_key="v2-10",
                artifact_id=copy_result.get("step_payload_artifact_id"),
            )
            self._pending_decision_payload = {
                "copy_artifact_id": copy_result.get("copy_artifact_id"),
                "headline": copy_payload.get("headline"),
            }

            self._current_stage = "v2-11"
            await self._wait_for_signal(signal_type="strategy_v2_approve_final_copy")
            if not isinstance(self._final_approval_decision, dict):
                raise RuntimeError("Final copy approval decision payload is missing or invalid.")

            final_result = await workflow.execute_activity(
                finalize_strategy_v2_copy_approval_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "final_approval_decision": self._final_approval_decision,
                    "copy_payload": copy_payload,
                },
                schedule_to_close_timeout=timedelta(minutes=5),
            )
            if isinstance(final_result, dict):
                self._artifact_refs["approved_artifact_id"] = final_result.get("approved_artifact_id")
                self._record_step_payload_artifact_ref(
                    step_key="v2-11",
                    artifact_id=final_result.get("step_payload_artifact_id"),
                )
            self._pending_decision_payload = None
            self._pending_signal_type = None
            self._current_stage = "completed"

            return {
                "workflow_run_id": self._workflow_run_id,
                "artifact_refs": self._artifact_refs,
                "status": "completed",
            }
        except Exception as exc:
            self._current_stage = "failed"
            await self._mark_failed(org_id=input.org_id, error_message=str(exc))
            raise
