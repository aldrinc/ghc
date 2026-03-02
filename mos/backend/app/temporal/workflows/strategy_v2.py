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
        run_strategy_v2_voc_agent0_habitat_strategy_activity,
        run_strategy_v2_voc_agent0b_apify_collection_activity,
        run_strategy_v2_voc_agent0b_social_video_strategy_activity,
        run_strategy_v2_voc_agent0b_apify_ingestion_activity,
        run_strategy_v2_voc_agent1_habitat_qualifier_activity,
        run_strategy_v2_voc_agent2_extraction_activity,
        run_strategy_v2_voc_agent3_synthesis_activity,
    )

_STEP_PAYLOAD_LINEAGE_EXPECTATIONS_BY_CHECKPOINT: Dict[str, list[str]] = {
    "v2-04 Agent 1 habitat qualifier": ["v2-02", "v2-03", "v2-03b", "v2-03c"],
    "v2-05 Agent 2 VOC extraction": ["v2-04"],
    "v2-06 Agent 3 angle synthesis": ["v2-05"],
}


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

    @staticmethod
    def _normalize_angle_gate_candidates(rows: Any) -> list[Dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: list[Dict[str, Any]] = []
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

    @staticmethod
    def _normalized_pending_decision_payload(
        *,
        pending_signal_type: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return payload
        if pending_signal_type != "strategy_v2_select_angle":
            return payload
        normalized_payload = dict(payload)
        normalized_payload["candidates"] = StrategyV2Workflow._normalize_angle_gate_candidates(payload.get("candidates"))
        return normalized_payload

    @staticmethod
    def _infer_strategy_config_run_count(agent00_output: Any, agent00b_output: Any) -> int:
        """Derive base strategy config count from Agent 0/0b payloads."""
        count = 0
        if isinstance(agent00_output, dict):
            tier1 = agent00_output.get("apify_configs_tier1")
            tier2 = agent00_output.get("apify_configs_tier2")
            if isinstance(tier1, list):
                count += len(tier1)
            if isinstance(tier2, list):
                count += len(tier2)
        if isinstance(agent00b_output, dict):
            video_configs = agent00b_output.get("configurations")
            if isinstance(video_configs, list):
                count += len(video_configs)
        return count

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
        # Keep a direct step-key lookup so UI/API consumers can read
        # artifact_refs[step_key] consistently across live-query and
        # persisted fallback state shapes.
        self._artifact_refs[step_key] = artifact_id
        normalized_step_key = step_key.replace("-", "_")
        self._artifact_refs[f"step_payload_{normalized_step_key}_artifact_id"] = artifact_id

    def _require_step_payload_artifacts(
        self,
        *,
        checkpoint_label: str,
        required_step_keys: list[str],
    ) -> None:
        effective_required_step_keys = list(required_step_keys)
        expected_lineage_keys = _STEP_PAYLOAD_LINEAGE_EXPECTATIONS_BY_CHECKPOINT.get(checkpoint_label, [])
        for step_key in expected_lineage_keys:
            if step_key not in effective_required_step_keys:
                effective_required_step_keys.append(step_key)
        refs = self._artifact_refs.get("step_payload_artifact_ids")
        if not isinstance(refs, dict):
            raise RuntimeError(
                f"{checkpoint_label} cannot start because step_payload_artifact_ids is missing from workflow state."
            )
        missing: list[str] = []
        for step_key in effective_required_step_keys:
            artifact_id = refs.get(step_key)
            if not isinstance(artifact_id, str) or not artifact_id.strip():
                missing.append(step_key)
        if missing:
            raise RuntimeError(
                f"{checkpoint_label} cannot start because prerequisite step payload artifacts are missing: {missing}. "
                "Remediation: reset to an earlier completed checkpoint and rerun forward."
            )

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
        pending_decision_payload = self._normalized_pending_decision_payload(
            pending_signal_type=self._pending_signal_type,
            payload=self._pending_decision_payload,
        )
        return {
            "workflow_run_id": self._workflow_run_id,
            "current_stage": self._current_stage,
            "pending_signal_type": self._pending_signal_type,
            "required_signal_type": self._pending_signal_type,
            "pending_decision_payload": pending_decision_payload,
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

            self._current_stage = "v2-02.foundation"
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
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(foundational_result, dict):
                raise RuntimeError("Strategy V2 foundational research activity returned an invalid payload.")
            stage1 = foundational_result.get("stage1")
            if not isinstance(stage1, dict):
                raise RuntimeError("Strategy V2 foundational research activity did not return stage1.")
            precanon_research = foundational_result.get("precanon_research")
            if not isinstance(precanon_research, dict):
                raise RuntimeError("Strategy V2 foundational research activity did not return precanon_research.")
            stage1_artifact_id = foundational_result.get("stage1_artifact_id")
            if not isinstance(stage1_artifact_id, str) or not stage1_artifact_id.strip():
                raise RuntimeError("Strategy V2 foundational research activity did not return stage1_artifact_id.")
            self._artifact_refs["stage1_artifact_id"] = stage1_artifact_id
            foundational_step_payload_map_raw = foundational_result.get("step_payload_artifact_ids")
            step_payload_artifact_ids: Dict[str, str] = {}
            if isinstance(foundational_step_payload_map_raw, dict):
                for step_key, artifact_id in foundational_step_payload_map_raw.items():
                    if (
                        isinstance(step_key, str)
                        and step_key.strip()
                        and isinstance(artifact_id, str)
                        and artifact_id.strip()
                    ):
                        normalized_step_key = step_key.strip()
                        normalized_artifact_id = artifact_id.strip()
                        step_payload_artifact_ids[normalized_step_key] = normalized_artifact_id
                        self._record_step_payload_artifact_ref(
                            step_key=normalized_step_key,
                            artifact_id=normalized_artifact_id,
                        )

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
            if isinstance(research_proceed_result.get("step_payload_artifact_id"), str):
                step_payload_artifact_ids["v2-02a"] = str(research_proceed_result["step_payload_artifact_id"])

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
                # Apify ingestion fans out across multiple actors. With
                # STRATEGY_V2_APIFY_MAX_WAIT_SECONDS=1200 and 3 actor runs, a
                # 30m budget is insufficient and causes ScheduleToClose timeouts.
                schedule_to_close_timeout=timedelta(minutes=90),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(candidate_assets_result, dict):
                raise RuntimeError("Competitor asset candidate preparation returned an invalid payload.")
            competitor_asset_candidates = candidate_assets_result.get("candidates")
            if not isinstance(competitor_asset_candidates, list) or len(competitor_asset_candidates) < 3:
                raise RuntimeError(
                    "Competitor asset candidate preparation did not return at least 3 scored candidates."
                )
            candidate_summary = candidate_assets_result.get("candidate_summary")
            self._scored_candidate_summaries["competitor_assets"] = competitor_asset_candidates
            self._record_step_payload_artifact_ref(
                step_key="v2-02i",
                artifact_id=candidate_assets_result.get("step_payload_artifact_id"),
            )
            if isinstance(candidate_assets_result.get("step_payload_artifact_id"), str):
                step_payload_artifact_ids["v2-02i"] = str(candidate_assets_result["step_payload_artifact_id"])

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
            if isinstance(competitor_assets_result.get("step_payload_artifact_id"), str):
                step_payload_artifact_ids["v2-02b"] = str(competitor_assets_result["step_payload_artifact_id"])
            self._pending_decision_payload = None

            self._current_stage = "v2-02"
            self._require_step_payload_artifacts(
                checkpoint_label="v2-02 Agent 0 habitat strategy",
                required_step_keys=["v2-02b"],
            )
            checkpoint_v2_02_result = await workflow.execute_activity(
                run_strategy_v2_voc_agent0_habitat_strategy_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": stage1_artifact_id,
                    "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(checkpoint_v2_02_result, dict):
                raise RuntimeError("Strategy V2 v2-02 activity returned an invalid payload.")
            agent00_output = checkpoint_v2_02_result.get("agent00_output")
            if not isinstance(agent00_output, dict):
                raise RuntimeError("Strategy V2 v2-02 activity did not return agent00_output.")
            competitor_analysis = checkpoint_v2_02_result.get("competitor_analysis")
            if not isinstance(competitor_analysis, dict):
                raise RuntimeError("Strategy V2 v2-02 activity did not return competitor_analysis.")
            v2_02_step_payload_artifact_id = checkpoint_v2_02_result.get("step_payload_artifact_id")
            if not isinstance(v2_02_step_payload_artifact_id, str) or not v2_02_step_payload_artifact_id.strip():
                raise RuntimeError("Strategy V2 v2-02 activity did not return step_payload_artifact_id.")
            self._record_step_payload_artifact_ref(
                step_key="v2-02",
                artifact_id=v2_02_step_payload_artifact_id,
            )
            step_payload_artifact_ids["v2-02"] = v2_02_step_payload_artifact_id
            if isinstance(checkpoint_v2_02_result.get("stage1_artifact_id"), str):
                stage1_artifact_id = str(checkpoint_v2_02_result["stage1_artifact_id"])
                self._artifact_refs["stage1_artifact_id"] = stage1_artifact_id

            self._current_stage = "v2-03"
            self._require_step_payload_artifacts(
                checkpoint_label="v2-03 Agent 0b social video strategy",
                required_step_keys=["v2-02"],
            )
            checkpoint_v2_03_result = await workflow.execute_activity(
                run_strategy_v2_voc_agent0b_social_video_strategy_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": stage1_artifact_id,
                    "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "agent00_output": agent00_output,
                    "competitor_analysis": competitor_analysis,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=120),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(checkpoint_v2_03_result, dict):
                raise RuntimeError("Strategy V2 v2-03 activity returned an invalid payload.")
            agent00b_output = checkpoint_v2_03_result.get("agent00b_output")
            if not isinstance(agent00b_output, dict):
                raise RuntimeError("Strategy V2 v2-03 activity did not return agent00b_output.")
            v2_03_step_payload_artifact_id = checkpoint_v2_03_result.get("step_payload_artifact_id")
            if not isinstance(v2_03_step_payload_artifact_id, str) or not v2_03_step_payload_artifact_id.strip():
                raise RuntimeError("Strategy V2 v2-03 activity did not return step_payload_artifact_id.")
            self._record_step_payload_artifact_ref(
                step_key="v2-03",
                artifact_id=v2_03_step_payload_artifact_id,
            )
            step_payload_artifact_ids["v2-03"] = v2_03_step_payload_artifact_id

            apify_split_checkpoint_enabled = workflow.patched("strategy_v2_apify_collection_split_v1")
            strategy_counter_contract_enabled = workflow.patched("strategy_v2_apify_strategy_counter_contract_v1")
            handoff_audit: dict[str, Any] | None = None
            scoring_audit: dict[str, Any] = {}
            expected_strategy_config_run_count = self._infer_strategy_config_run_count(agent00_output, agent00b_output)

            self._current_stage = "v2-03b"
            self._require_step_payload_artifacts(
                checkpoint_label="v2-03b Apify collection",
                required_step_keys=["v2-02", "v2-03"],
            )
            if apify_split_checkpoint_enabled:
                checkpoint_v2_03b_result = await workflow.execute_activity(
                    run_strategy_v2_voc_agent0b_apify_collection_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": input.campaign_id,
                        "workflow_run_id": self._workflow_run_id,
                        "stage0": stage0,
                        "precanon_research": precanon_research,
                        "stage1": stage1,
                        "stage1_artifact_id": stage1_artifact_id,
                        "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                        "confirmed_competitor_assets": confirmed_competitor_assets,
                        "agent00_output": agent00_output,
                        "agent00b_output": agent00b_output,
                        "competitor_analysis": competitor_analysis,
                        "operator_user_id": input.operator_user_id or "system",
                    },
                    schedule_to_close_timeout=timedelta(hours=6),
                    heartbeat_timeout=timedelta(minutes=60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if not isinstance(checkpoint_v2_03b_result, dict):
                    raise RuntimeError("Strategy V2 v2-03b activity returned an invalid payload.")
                apify_collection_artifact_id = checkpoint_v2_03b_result.get("apify_collection_artifact_id")
                if not isinstance(apify_collection_artifact_id, str) or not apify_collection_artifact_id.strip():
                    raise RuntimeError("Strategy V2 v2-03b activity did not return apify_collection_artifact_id.")
                strategy_config_run_count = checkpoint_v2_03b_result.get("strategy_config_run_count")
                planned_actor_run_count = checkpoint_v2_03b_result.get("planned_actor_run_count")
                executed_actor_run_count = checkpoint_v2_03b_result.get("executed_actor_run_count")
                failed_actor_run_count = checkpoint_v2_03b_result.get("failed_actor_run_count")
                if (
                    not isinstance(planned_actor_run_count, int)
                    or planned_actor_run_count < 0
                    or not isinstance(executed_actor_run_count, int)
                    or executed_actor_run_count < 0
                    or not isinstance(failed_actor_run_count, int)
                    or failed_actor_run_count < 0
                ):
                    raise RuntimeError(
                        "Strategy V2 v2-03b activity must return explicit strategy/planned/executed/failed actor run counters."
                    )
                if strategy_counter_contract_enabled:
                    if not isinstance(strategy_config_run_count, int) or strategy_config_run_count < 0:
                        raise RuntimeError(
                            "Strategy V2 v2-03b activity must return explicit strategy/planned/executed/failed actor run counters."
                        )
                else:
                    if not isinstance(strategy_config_run_count, int) or strategy_config_run_count < 0:
                        strategy_config_run_count = expected_strategy_config_run_count
                v2_03b_step_payload_artifact_id = checkpoint_v2_03b_result.get("step_payload_artifact_id")
                if not isinstance(v2_03b_step_payload_artifact_id, str) or not v2_03b_step_payload_artifact_id.strip():
                    raise RuntimeError("Strategy V2 v2-03b activity did not return step_payload_artifact_id.")
                self._record_step_payload_artifact_ref(
                    step_key="v2-03b",
                    artifact_id=v2_03b_step_payload_artifact_id,
                )
                step_payload_artifact_ids["v2-03b"] = v2_03b_step_payload_artifact_id

                self._current_stage = "v2-03c"
                self._require_step_payload_artifacts(
                    checkpoint_label="v2-03c Apify postprocess + virality",
                    required_step_keys=["v2-02", "v2-03", "v2-03b"],
                )
                checkpoint_v2_03c_result = await workflow.execute_activity(
                    run_strategy_v2_voc_agent0b_apify_ingestion_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": input.campaign_id,
                        "workflow_run_id": self._workflow_run_id,
                        "stage0": stage0,
                        "precanon_research": precanon_research,
                        "stage1": stage1,
                        "stage1_artifact_id": stage1_artifact_id,
                        "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                        "confirmed_competitor_assets": confirmed_competitor_assets,
                        "agent00_output": agent00_output,
                        "agent00b_output": agent00b_output,
                        "competitor_analysis": competitor_analysis,
                        "apify_collection_artifact_id": apify_collection_artifact_id,
                        "operator_user_id": input.operator_user_id or "system",
                    },
                    schedule_to_close_timeout=timedelta(minutes=90),
                    heartbeat_timeout=timedelta(minutes=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if not isinstance(checkpoint_v2_03c_result, dict):
                    raise RuntimeError("Strategy V2 v2-03c activity returned an invalid payload.")
                scraped_data_manifest = checkpoint_v2_03c_result.get("scraped_data_manifest")
                if not isinstance(scraped_data_manifest, dict):
                    raise RuntimeError("Strategy V2 v2-03c activity did not return scraped_data_manifest.")
                video_scored = checkpoint_v2_03c_result.get("video_scored")
                if not isinstance(video_scored, list):
                    raise RuntimeError("Strategy V2 v2-03c activity did not return video_scored array.")
                existing_corpus = checkpoint_v2_03c_result.get("existing_corpus")
                if not isinstance(existing_corpus, list):
                    raise RuntimeError("Strategy V2 v2-03c activity did not return existing_corpus array.")
                merged_voc_artifact_rows = checkpoint_v2_03c_result.get("merged_voc_artifact_rows")
                if not isinstance(merged_voc_artifact_rows, list):
                    raise RuntimeError(
                        "Strategy V2 v2-03c activity did not return merged_voc_artifact_rows array."
                    )
                corpus_selection_summary = checkpoint_v2_03c_result.get("corpus_selection_summary")
                if not isinstance(corpus_selection_summary, dict):
                    raise RuntimeError(
                        "Strategy V2 v2-03c activity did not return corpus_selection_summary object."
                    )
                external_corpus_count = checkpoint_v2_03c_result.get("external_corpus_count")
                if not isinstance(external_corpus_count, int) or external_corpus_count < 0:
                    raise RuntimeError(
                        "Strategy V2 v2-03c activity did not return a valid external_corpus_count integer."
                    )
                proof_asset_candidates = checkpoint_v2_03c_result.get("proof_asset_candidates")
                if not isinstance(proof_asset_candidates, list):
                    raise RuntimeError("Strategy V2 v2-03c activity did not return proof_asset_candidates array.")
                handoff_audit = checkpoint_v2_03c_result.get("handoff_audit")
                if handoff_audit is not None and not isinstance(handoff_audit, dict):
                    raise RuntimeError("Strategy V2 v2-03c activity returned invalid handoff_audit payload.")
                scoring_audit_raw = checkpoint_v2_03c_result.get("scoring_audit")
                if scoring_audit_raw is not None and not isinstance(scoring_audit_raw, dict):
                    raise RuntimeError("Strategy V2 v2-03c activity returned invalid scoring_audit payload.")
                scoring_audit = dict(scoring_audit_raw) if isinstance(scoring_audit_raw, dict) else {}
                strategy_config_run_count_post = checkpoint_v2_03c_result.get("strategy_config_run_count")
                planned_actor_run_count_post = checkpoint_v2_03c_result.get("planned_actor_run_count")
                executed_actor_run_count_post = checkpoint_v2_03c_result.get("executed_actor_run_count")
                failed_actor_run_count_post = checkpoint_v2_03c_result.get("failed_actor_run_count")
                if (
                    not isinstance(planned_actor_run_count_post, int)
                    or not isinstance(executed_actor_run_count_post, int)
                    or not isinstance(failed_actor_run_count_post, int)
                ):
                    raise RuntimeError("Strategy V2 v2-03c activity did not return explicit run counters.")
                if strategy_counter_contract_enabled:
                    if not isinstance(strategy_config_run_count_post, int):
                        raise RuntimeError("Strategy V2 v2-03c activity did not return explicit run counters.")
                else:
                    if not isinstance(strategy_config_run_count_post, int):
                        strategy_config_run_count_post = strategy_config_run_count
                strategy_config_run_count = strategy_config_run_count_post
                planned_actor_run_count = planned_actor_run_count_post
                executed_actor_run_count = executed_actor_run_count_post
                failed_actor_run_count = failed_actor_run_count_post
                v2_03c_step_payload_artifact_id = checkpoint_v2_03c_result.get("step_payload_artifact_id")
                if not isinstance(v2_03c_step_payload_artifact_id, str) or not v2_03c_step_payload_artifact_id.strip():
                    raise RuntimeError("Strategy V2 v2-03c activity did not return step_payload_artifact_id.")
                self._record_step_payload_artifact_ref(
                    step_key="v2-03c",
                    artifact_id=v2_03c_step_payload_artifact_id,
                )
                step_payload_artifact_ids["v2-03c"] = v2_03c_step_payload_artifact_id
            else:
                checkpoint_v2_03b_legacy_result = await workflow.execute_activity(
                    run_strategy_v2_voc_agent0b_apify_ingestion_activity,
                    {
                        "org_id": input.org_id,
                        "client_id": input.client_id,
                        "product_id": input.product_id,
                        "campaign_id": input.campaign_id,
                        "workflow_run_id": self._workflow_run_id,
                        "stage0": stage0,
                        "precanon_research": precanon_research,
                        "stage1": stage1,
                        "stage1_artifact_id": stage1_artifact_id,
                        "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                        "confirmed_competitor_assets": confirmed_competitor_assets,
                        "agent00_output": agent00_output,
                        "agent00b_output": agent00b_output,
                        "competitor_analysis": competitor_analysis,
                        "operator_user_id": input.operator_user_id or "system",
                    },
                    schedule_to_close_timeout=timedelta(hours=6),
                    heartbeat_timeout=timedelta(minutes=60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if not isinstance(checkpoint_v2_03b_legacy_result, dict):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity returned an invalid payload.")
                scraped_data_manifest = checkpoint_v2_03b_legacy_result.get("scraped_data_manifest")
                if not isinstance(scraped_data_manifest, dict):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity did not return scraped_data_manifest.")
                video_scored = checkpoint_v2_03b_legacy_result.get("video_scored")
                if not isinstance(video_scored, list):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity did not return video_scored array.")
                existing_corpus = checkpoint_v2_03b_legacy_result.get("existing_corpus")
                if not isinstance(existing_corpus, list):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity did not return existing_corpus array.")
                merged_voc_artifact_rows = checkpoint_v2_03b_legacy_result.get("merged_voc_artifact_rows")
                if not isinstance(merged_voc_artifact_rows, list):
                    raise RuntimeError(
                        "Strategy V2 v2-03b legacy activity did not return merged_voc_artifact_rows array."
                    )
                corpus_selection_summary = checkpoint_v2_03b_legacy_result.get("corpus_selection_summary")
                if not isinstance(corpus_selection_summary, dict):
                    raise RuntimeError(
                        "Strategy V2 v2-03b legacy activity did not return corpus_selection_summary object."
                    )
                external_corpus_count = checkpoint_v2_03b_legacy_result.get("external_corpus_count")
                if not isinstance(external_corpus_count, int) or external_corpus_count < 0:
                    raise RuntimeError(
                        "Strategy V2 v2-03b legacy activity did not return a valid external_corpus_count integer."
                    )
                proof_asset_candidates = checkpoint_v2_03b_legacy_result.get("proof_asset_candidates")
                if not isinstance(proof_asset_candidates, list):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity did not return proof_asset_candidates array.")
                legacy_scoring_audit = checkpoint_v2_03b_legacy_result.get("scoring_audit")
                if legacy_scoring_audit is not None and not isinstance(legacy_scoring_audit, dict):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity returned invalid scoring_audit payload.")
                scoring_audit = dict(legacy_scoring_audit) if isinstance(legacy_scoring_audit, dict) else {}
                v2_03b_step_payload_artifact_id = checkpoint_v2_03b_legacy_result.get("step_payload_artifact_id")
                if not isinstance(v2_03b_step_payload_artifact_id, str) or not v2_03b_step_payload_artifact_id.strip():
                    raise RuntimeError("Strategy V2 v2-03b legacy activity did not return step_payload_artifact_id.")
                self._record_step_payload_artifact_ref(
                    step_key="v2-03b",
                    artifact_id=v2_03b_step_payload_artifact_id,
                )
                step_payload_artifact_ids["v2-03b"] = v2_03b_step_payload_artifact_id

                planned_actor_run_count = checkpoint_v2_03b_legacy_result.get("planned_actor_run_count")
                executed_actor_run_count = checkpoint_v2_03b_legacy_result.get("executed_actor_run_count")
                failed_actor_run_count = checkpoint_v2_03b_legacy_result.get("failed_actor_run_count")
                strategy_config_run_count = checkpoint_v2_03b_legacy_result.get("strategy_config_run_count")
                if (
                    not isinstance(planned_actor_run_count, int)
                    or not isinstance(executed_actor_run_count, int)
                    or not isinstance(failed_actor_run_count, int)
                ):
                    raise RuntimeError(
                        "Strategy V2 v2-03b legacy activity did not return required run counters "
                        "(planned_actor_run_count/executed_actor_run_count/failed_actor_run_count)."
                    )
                if strategy_counter_contract_enabled:
                    if not isinstance(strategy_config_run_count, int):
                        raise RuntimeError(
                            "Strategy V2 v2-03b legacy activity did not return strategy_config_run_count."
                        )
                else:
                    if not isinstance(strategy_config_run_count, int):
                        strategy_config_run_count = expected_strategy_config_run_count
                if (
                    strategy_config_run_count < 0
                    or planned_actor_run_count < 0
                    or executed_actor_run_count < 0
                    or failed_actor_run_count < 0
                ):
                    raise RuntimeError("Strategy V2 v2-03b legacy activity returned invalid run counters.")

            self._current_stage = "v2-04"
            required_step_keys_v2_04 = ["v2-02", "v2-03", "v2-03b"]
            if apify_split_checkpoint_enabled:
                required_step_keys_v2_04.append("v2-03c")
            self._require_step_payload_artifacts(
                checkpoint_label="v2-04 Agent 1 habitat qualifier",
                required_step_keys=required_step_keys_v2_04,
            )
            checkpoint_v2_04_result = await workflow.execute_activity(
                run_strategy_v2_voc_agent1_habitat_qualifier_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": stage1_artifact_id,
                    "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "agent00_output": agent00_output,
                    "agent00b_output": agent00b_output,
                    "scraped_data_manifest": scraped_data_manifest,
                    "video_scored": video_scored,
                    "strategy_config_run_count": strategy_config_run_count,
                    "planned_actor_run_count": planned_actor_run_count,
                    "executed_actor_run_count": executed_actor_run_count,
                    "failed_actor_run_count": failed_actor_run_count,
                    "handoff_audit": handoff_audit if isinstance(handoff_audit, dict) else {},
                    "scoring_audit": scoring_audit,
                    "competitor_analysis": competitor_analysis,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(checkpoint_v2_04_result, dict):
                raise RuntimeError("Strategy V2 v2-04 activity returned an invalid payload.")
            agent01_output = checkpoint_v2_04_result.get("agent01_output")
            if not isinstance(agent01_output, dict):
                raise RuntimeError("Strategy V2 v2-04 activity did not return agent01_output.")
            habitat_scored = checkpoint_v2_04_result.get("habitat_scored")
            if not isinstance(habitat_scored, dict):
                raise RuntimeError("Strategy V2 v2-04 activity did not return habitat_scored.")
            v2_04_step_payload_artifact_id = checkpoint_v2_04_result.get("step_payload_artifact_id")
            if not isinstance(v2_04_step_payload_artifact_id, str) or not v2_04_step_payload_artifact_id.strip():
                raise RuntimeError("Strategy V2 v2-04 activity did not return step_payload_artifact_id.")
            self._record_step_payload_artifact_ref(
                step_key="v2-04",
                artifact_id=v2_04_step_payload_artifact_id,
            )
            step_payload_artifact_ids["v2-04"] = v2_04_step_payload_artifact_id

            self._current_stage = "v2-05"
            self._require_step_payload_artifacts(
                checkpoint_label="v2-05 Agent 2 VOC extraction",
                required_step_keys=["v2-04"],
            )
            checkpoint_v2_05_result = await workflow.execute_activity(
                run_strategy_v2_voc_agent2_extraction_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": stage1_artifact_id,
                    "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "agent01_output": agent01_output,
                    "habitat_scored": habitat_scored,
                    "scraped_data_manifest": scraped_data_manifest,
                    "existing_corpus": existing_corpus,
                    "merged_voc_artifact_rows": merged_voc_artifact_rows,
                    "corpus_selection_summary": corpus_selection_summary,
                    "external_corpus_count": external_corpus_count,
                    "proof_asset_candidates": proof_asset_candidates,
                    "competitor_analysis": competitor_analysis,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=90),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(checkpoint_v2_05_result, dict):
                raise RuntimeError("Strategy V2 v2-05 activity returned an invalid payload.")
            voc_observations = checkpoint_v2_05_result.get("voc_observations")
            if not isinstance(voc_observations, list):
                raise RuntimeError("Strategy V2 v2-05 activity did not return voc_observations array.")
            voc_scored = checkpoint_v2_05_result.get("voc_scored")
            if not isinstance(voc_scored, dict):
                raise RuntimeError("Strategy V2 v2-05 activity did not return voc_scored.")
            proof_asset_candidates = checkpoint_v2_05_result.get("proof_asset_candidates")
            if not isinstance(proof_asset_candidates, list):
                raise RuntimeError("Strategy V2 v2-05 activity did not return proof_asset_candidates array.")
            v2_05_step_payload_artifact_id = checkpoint_v2_05_result.get("step_payload_artifact_id")
            if not isinstance(v2_05_step_payload_artifact_id, str) or not v2_05_step_payload_artifact_id.strip():
                raise RuntimeError("Strategy V2 v2-05 activity did not return step_payload_artifact_id.")
            self._record_step_payload_artifact_ref(
                step_key="v2-05",
                artifact_id=v2_05_step_payload_artifact_id,
            )
            step_payload_artifact_ids["v2-05"] = v2_05_step_payload_artifact_id

            self._current_stage = "v2-06"
            self._require_step_payload_artifacts(
                checkpoint_label="v2-06 Agent 3 angle synthesis",
                required_step_keys=["v2-05"],
            )
            checkpoint_v2_06_result = await workflow.execute_activity(
                run_strategy_v2_voc_agent3_synthesis_activity,
                {
                    "org_id": input.org_id,
                    "client_id": input.client_id,
                    "product_id": input.product_id,
                    "campaign_id": input.campaign_id,
                    "workflow_run_id": self._workflow_run_id,
                    "stage0": stage0,
                    "precanon_research": precanon_research,
                    "stage1": stage1,
                    "stage1_artifact_id": stage1_artifact_id,
                    "existing_step_payload_artifact_ids": step_payload_artifact_ids,
                    "confirmed_competitor_assets": confirmed_competitor_assets,
                    "competitor_analysis": competitor_analysis,
                    "voc_observations": voc_observations,
                    "voc_scored": voc_scored,
                    "operator_user_id": input.operator_user_id or "system",
                },
                schedule_to_close_timeout=timedelta(minutes=60),
                heartbeat_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            if not isinstance(checkpoint_v2_06_result, dict):
                raise RuntimeError("Strategy V2 v2-06 activity returned an invalid payload.")
            ranked_angle_candidates = checkpoint_v2_06_result.get("ranked_angle_candidates")
            if not isinstance(ranked_angle_candidates, list) or not ranked_angle_candidates:
                raise RuntimeError(
                    "Strategy V2 angle synthesis did not produce ranked candidates for angle selection."
                )
            v2_06_step_payload_artifact_id = checkpoint_v2_06_result.get("step_payload_artifact_id")
            if not isinstance(v2_06_step_payload_artifact_id, str) or not v2_06_step_payload_artifact_id.strip():
                raise RuntimeError("Strategy V2 v2-06 activity did not return step_payload_artifact_id.")
            self._record_step_payload_artifact_ref(
                step_key="v2-06",
                artifact_id=v2_06_step_payload_artifact_id,
            )
            step_payload_artifact_ids["v2-06"] = v2_06_step_payload_artifact_id

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
                    "competitor_analysis": competitor_analysis,
                    "voc_observations": voc_observations,
                    "voc_scored": voc_scored,
                    "angle_synthesis": {"ranked_candidates": ranked_angle_candidates},
                    "business_model": input.business_model or "",
                    "funnel_position": input.funnel_position or "",
                    "target_platforms": input.target_platforms or [],
                    "target_regions": input.target_regions or [],
                    "existing_proof_assets": input.existing_proof_assets or [],
                    "proof_asset_candidates": proof_asset_candidates,
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
                retry_policy=RetryPolicy(maximum_attempts=1),
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
