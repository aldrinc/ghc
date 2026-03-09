import asyncio
from datetime import timedelta

import pytest

from app.temporal.workflows import strategy_v2 as strategy_v2_workflow_module
from app.temporal.workflows.strategy_v2 import StrategyV2Input, StrategyV2Workflow


def _stage0_payload() -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "stage": 0,
        "product_name": "Product Name",
        "description": "Product description",
        "price": "$49",
        "competitor_urls": ["https://competitor.example"],
        "product_customizable": True,
    }


def test_strategy_v2_workflow_does_not_execute_precanon_child(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append(("execute_activity", activity_name))
        if activity_name == "check_strategy_v2_enabled_activity":
            return {"enabled": True}
        if activity_name == "ensure_strategy_v2_workflow_run_activity":
            return {"workflow_run_id": "strategy-v2-run-id"}
        if activity_name == "build_strategy_v2_stage0_activity":
            assert payload["onboarding_payload_id"] == "payload-1"
            return {"stage0": _stage0_payload(), "stage0_artifact_id": "artifact-stage0"}
        if activity_name == "build_strategy_v2_foundational_research_activity":
            assert _kwargs["heartbeat_timeout"] == timedelta(minutes=20)
            assert _kwargs["retry_policy"].maximum_attempts == 2
            assert _kwargs["retry_policy"].non_retryable_error_types == [
                "StrategyV2MissingContextError",
                "StrategyV2SchemaValidationError",
            ]
            raise RuntimeError("stop_after_foundational_activity")
        if activity_name == "run_strategy_v2_voc_angle_pipeline_activity":
            assert payload["onboarding_payload_id"] == "payload-1"
            assert _kwargs["heartbeat_timeout"] == timedelta(minutes=20)
            raise RuntimeError("stop_after_voc_activity")
        if activity_name == "mark_strategy_v2_failed_activity":
            return {"ok": True}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    async def _fake_execute_child_workflow(*_args, **_kwargs):  # noqa: ANN003
        raise AssertionError("Strategy V2 must not start PreCanon child workflow.")

    class _Info:
        workflow_id = "strategy-v2-workflow-id"
        run_id = "strategy-v2-run-id"

    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "execute_child_workflow", _fake_execute_child_workflow)
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "info", lambda: _Info())

    with pytest.raises(strategy_v2_workflow_module.ApplicationError, match="stop_after_foundational_activity"):
        asyncio.run(
            StrategyV2Workflow().run(
                StrategyV2Input(
                    org_id="org-1",
                    client_id="client-1",
                    product_id="product-1",
                    onboarding_payload_id="payload-1",
                    operator_user_id="operator-1",
                )
            )
        )

    assert ("execute_activity", "build_strategy_v2_foundational_research_activity") in calls


def test_strategy_v2_workflow_stage2b_runs_as_checkpoint_activities(monkeypatch) -> None:
    calls: list[str] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append(activity_name)
        if activity_name == "check_strategy_v2_enabled_activity":
            return {"enabled": True}
        if activity_name == "ensure_strategy_v2_workflow_run_activity":
            return {"workflow_run_id": "strategy-v2-run-id"}
        if activity_name == "build_strategy_v2_stage0_activity":
            return {
                "stage0": _stage0_payload(),
                "stage0_artifact_id": "artifact-stage0",
                "step_payload_artifact_id": "artifact-step-v2-01",
            }
        if activity_name == "build_strategy_v2_foundational_research_activity":
            return {
                "stage1": {"category_niche": "Sleep Support"},
                "stage1_artifact_id": "artifact-stage1",
                "precanon_research": {"step_summaries": {"01": "summary"}},
                "step_payload_artifact_ids": {
                    "v2-02.foundation.01": "artifact-foundation-01",
                    "v2-02.foundation.02": "artifact-foundation-02",
                    "v2-02.foundation.03": "artifact-foundation-03",
                    "v2-02.foundation.04": "artifact-foundation-04",
                    "v2-02.foundation.06": "artifact-foundation-06",
                },
            }
        if activity_name == "finalize_strategy_v2_research_proceed_activity":
            return {"step_payload_artifact_id": "artifact-step-v2-02a"}
        if activity_name == "prepare_strategy_v2_competitor_asset_candidates_activity":
            return {
                "candidates": ["cand-1", "cand-2", "cand-3"],
                "candidate_summary": {"selected_candidate_count": 3},
                "step_payload_artifact_id": "artifact-step-v2-02i",
            }
        if activity_name == "finalize_strategy_v2_competitor_assets_confirmation_activity":
            return {
                "confirmed_asset_refs": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "step_payload_artifact_id": "artifact-step-v2-02b",
            }
        if activity_name == "run_strategy_v2_voc_agent0_habitat_strategy_activity":
            return {
                "agent00_output": {"handoff": "ok"},
                "competitor_analysis": {"asset_observation_sheets": []},
                "stage1_artifact_id": "artifact-stage1",
                "step_payload_artifact_id": "artifact-step-v2-02",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_social_video_strategy_activity":
            return {
                "agent00b_output": {"configurations": []},
                "step_payload_artifact_id": "artifact-step-v2-03",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_apify_collection_activity":
            return {
                "apify_collection_artifact_id": "artifact-step-v2-03b",
                "strategy_config_run_count": 0,
                "planned_actor_run_count": 0,
                "executed_actor_run_count": 0,
                "failed_actor_run_count": 0,
                "step_payload_artifact_id": "artifact-step-v2-03b",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_apify_ingestion_activity":
            return {
                "scraped_data_manifest": {},
                "video_scored": [],
                "existing_corpus": [],
                "merged_voc_artifact_rows": [],
                "corpus_selection_summary": {},
                "external_corpus_count": 0,
                "strategy_config_run_count": 0,
                "planned_actor_run_count": 0,
                "executed_actor_run_count": 0,
                "failed_actor_run_count": 0,
                "proof_asset_candidates": [],
                "handoff_audit": {},
                "step_payload_artifact_id": "artifact-step-v2-03c",
            }
        if activity_name == "run_strategy_v2_voc_agent1_habitat_qualifier_activity":
            return {
                "agent01_output": {"habitat_observations": []},
                "habitat_scored": {"habitats": []},
                "step_payload_artifact_id": "artifact-step-v2-04",
            }
        if activity_name == "run_strategy_v2_voc_agent2_extraction_activity":
            return {
                "agent02_output": {
                    "mode": "FRESH",
                    "input_count": 0,
                    "output_count": 0,
                    "decisions_by_evidence_id": {},
                    "accepted_observations": [],
                    "validation_errors": [],
                },
                "agent02_input_manifest": {"input_count": 0, "rows": []},
                "agent02_prompt_provenance": {},
                "agent02_raw_output": "{}",
                "evidence_rows": [],
                "evidence_diagnostics": {},
                "prompt_corpus_count": 0,
                "merged_corpus_count": 0,
                "external_corpus_count": 0,
                "corpus_selection_summary": {},
                "proof_asset_candidates": [],
                "step_payload_artifact_id": "artifact-step-v2-05a",
            }
        if activity_name == "run_strategy_v2_voc_agent2_qa_activity":
            return {
                "voc_observations": [],
                "voc_scored": {"items": [{"zero_evidence_gate": False, "adjusted_score": 1.0}]},
                "proof_asset_candidates": [],
                "step_payload_artifact_id": "artifact-step-v2-05",
            }
        if activity_name == "run_strategy_v2_voc_agent3_synthesis_activity":
            return {
                "ranked_angle_candidates": [{"angle": {"angle_id": "angle-1"}}],
                "step_payload_artifact_id": "artifact-step-v2-06",
            }
        if activity_name == "apply_strategy_v2_angle_selection_activity":
            return {
                "stage2": {"selected_angle": {"angle_id": "angle-1"}},
                "stage2_artifact_id": "artifact-stage2",
                "step_payload_artifact_id": "artifact-step-v2-07",
            }
        if activity_name == "run_strategy_v2_offer_pipeline_activity":
            return {
                "pair_scoring": {"ranked_pairs": [{"pair_id": "pair-1"}]},
                "proof_asset_candidates": [],
                "step_payload_artifact_id": "artifact-step-v2-08",
            }
        if activity_name == "validate_strategy_v2_offer_data_readiness_activity":
            return {
                "status": "ready",
                "missing_fields": [],
                "inconsistent_fields": [],
                "context": {
                    "offer_format": "DISCOUNT_PLUS_3_BONUSES_V1",
                    "product_type": "digital",
                    "core_product": {"product_id": "product-1", "title": "Product Name"},
                    "offer_id": "offer-1",
                    "offer_name": "Default Offer",
                    "bonus_items": [
                        {"bonus_id": "bonus-1", "linked_product_id": "b1", "title": "Bonus 1", "position": 1},
                        {"bonus_id": "bonus-2", "linked_product_id": "b2", "title": "Bonus 2", "position": 2},
                        {"bonus_id": "bonus-3", "linked_product_id": "b3", "title": "Bonus 3", "position": 3},
                    ],
                    "pricing_metadata": {"list_price_cents": 9900, "offer_price_cents": 4900},
                    "savings_metadata": {"savings_amount_cents": 5000, "savings_percent": 50.5, "savings_basis": "vs_list_price"},
                    "bundle_contents": {"core_product": {"product_id": "product-1", "title": "Product Name"}},
                },
                "step_payload_artifact_id": "artifact-step-v2-08a",
            }
        if activity_name == "build_strategy_v2_offer_variants_activity":
            return {
                "composite_results": {"variants": [{"variant_id": "variant-1"}]},
                "step_payload_artifact_id": "artifact-step-v2-08b",
            }
        if activity_name == "finalize_strategy_v2_offer_winner_activity":
            return {
                "stage3": {"offer": "winner"},
                "copy_context": {"context": "ok"},
                "stage3_artifact_id": "artifact-stage3",
                "copy_context_artifact_id": "artifact-copy-context",
                "step_payload_artifact_id": "artifact-step-v2-09",
            }
        if activity_name == "run_strategy_v2_copy_pipeline_activity":
            return {
                "copy_payload": {"headline": "headline"},
                "copy_artifact_id": "artifact-copy",
                "step_payload_artifact_id": "artifact-step-v2-10",
            }
        if activity_name == "finalize_strategy_v2_copy_approval_activity":
            return {
                "approved_artifact_id": "artifact-approved",
                "step_payload_artifact_id": "artifact-step-v2-11",
            }
        if activity_name == "mark_strategy_v2_failed_activity":
            return {"ok": True}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    async def _fake_wait_for_signal(self, *, signal_type: str):  # noqa: ANN001
        if signal_type == "strategy_v2_proceed_research":
            self._research_proceed_decision = {"proceed": True}
            return
        if signal_type == "strategy_v2_confirm_competitor_assets":
            self._competitor_asset_confirmation_decision = {"confirmed_asset_refs": ["a", "b", "c"]}
            return
        if signal_type == "strategy_v2_select_angle":
            self._angle_selection_decision = {"selected_angle": {"angle_id": "angle-1"}}
            return
        if signal_type == "strategy_v2_select_ump_ums":
            self._ump_ums_selection_decision = {"pair_id": "pair-1"}
            return
        if signal_type == "strategy_v2_select_offer_winner":
            self._offer_winner_decision = {"variant_id": "variant-1"}
            return
        if signal_type == "strategy_v2_approve_final_copy":
            self._final_approval_decision = {"approved": True}
            return
        raise AssertionError(f"Unexpected wait signal: {signal_type}")

    class _Info:
        workflow_id = "strategy-v2-workflow-id"
        run_id = "strategy-v2-run-id"

    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(strategy_v2_workflow_module.StrategyV2Workflow, "_wait_for_signal", _fake_wait_for_signal)
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "info", lambda: _Info())
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "patched", lambda _id: True)

    result = asyncio.run(
        StrategyV2Workflow().run(
            StrategyV2Input(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                onboarding_payload_id="payload-1",
                operator_user_id="operator-1",
            )
        )
    )
    assert result["status"] == "completed"

    assert "run_strategy_v2_voc_angle_pipeline_activity" not in calls
    for activity_name in [
        "run_strategy_v2_voc_agent0_habitat_strategy_activity",
        "run_strategy_v2_voc_agent0b_social_video_strategy_activity",
        "run_strategy_v2_voc_agent0b_apify_collection_activity",
        "run_strategy_v2_voc_agent0b_apify_ingestion_activity",
        "run_strategy_v2_voc_agent1_habitat_qualifier_activity",
        "run_strategy_v2_voc_agent3_synthesis_activity",
    ]:
        assert activity_name in calls


def test_strategy_v2_workflow_fails_when_v2_03b_counters_missing(monkeypatch) -> None:
    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        if activity_name == "check_strategy_v2_enabled_activity":
            return {"enabled": True}
        if activity_name == "ensure_strategy_v2_workflow_run_activity":
            return {"workflow_run_id": "strategy-v2-run-id"}
        if activity_name == "build_strategy_v2_stage0_activity":
            return {
                "stage0": _stage0_payload(),
                "stage0_artifact_id": "artifact-stage0",
                "step_payload_artifact_id": "artifact-step-v2-01",
            }
        if activity_name == "build_strategy_v2_foundational_research_activity":
            return {
                "stage1": {"category_niche": "Sleep Support"},
                "stage1_artifact_id": "artifact-stage1",
                "precanon_research": {"step_summaries": {"01": "summary"}},
                "step_payload_artifact_ids": {
                    "v2-02.foundation.01": "artifact-foundation-01",
                    "v2-02.foundation.02": "artifact-foundation-02",
                    "v2-02.foundation.03": "artifact-foundation-03",
                    "v2-02.foundation.04": "artifact-foundation-04",
                    "v2-02.foundation.06": "artifact-foundation-06",
                },
            }
        if activity_name == "finalize_strategy_v2_research_proceed_activity":
            return {"step_payload_artifact_id": "artifact-step-v2-02a"}
        if activity_name == "prepare_strategy_v2_competitor_asset_candidates_activity":
            return {
                "candidates": ["cand-1", "cand-2", "cand-3"],
                "candidate_summary": {"selected_candidate_count": 3},
                "step_payload_artifact_id": "artifact-step-v2-02i",
            }
        if activity_name == "finalize_strategy_v2_competitor_assets_confirmation_activity":
            return {
                "confirmed_asset_refs": [
                    "https://competitor-a.example/asset-1",
                    "https://competitor-b.example/asset-2",
                    "https://competitor-c.example/asset-3",
                ],
                "step_payload_artifact_id": "artifact-step-v2-02b",
            }
        if activity_name == "run_strategy_v2_voc_agent0_habitat_strategy_activity":
            return {
                "agent00_output": {"handoff": "ok"},
                "competitor_analysis": {"asset_observation_sheets": []},
                "stage1_artifact_id": "artifact-stage1",
                "step_payload_artifact_id": "artifact-step-v2-02",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_social_video_strategy_activity":
            return {
                "agent00b_output": {"configurations": []},
                "step_payload_artifact_id": "artifact-step-v2-03",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_apify_collection_activity":
            # Legacy payload shape: counters absent.
            return {
                "apify_collection_artifact_id": "artifact-step-v2-03b",
                "step_payload_artifact_id": "artifact-step-v2-03b",
            }
        if activity_name == "run_strategy_v2_voc_agent0b_apify_ingestion_activity":
            raise AssertionError("v2-03c postprocess must not run when v2-03b counters are missing.")
        if activity_name == "mark_strategy_v2_failed_activity":
            return {"ok": True}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    async def _fake_wait_for_signal(self, *, signal_type: str):  # noqa: ANN001
        if signal_type == "strategy_v2_proceed_research":
            self._research_proceed_decision = {"proceed": True}
            return
        if signal_type == "strategy_v2_confirm_competitor_assets":
            self._competitor_asset_confirmation_decision = {"confirmed_asset_refs": ["a", "b", "c"]}
            return
        raise AssertionError(f"Unexpected wait signal: {signal_type}")

    class _Info:
        workflow_id = "strategy-v2-workflow-id"
        run_id = "strategy-v2-run-id"

    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(strategy_v2_workflow_module.StrategyV2Workflow, "_wait_for_signal", _fake_wait_for_signal)
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "info", lambda: _Info())
    monkeypatch.setattr(strategy_v2_workflow_module.workflow, "patched", lambda _id: True)

    with pytest.raises(
        strategy_v2_workflow_module.ApplicationError,
        match="must return explicit strategy/planned/executed/failed actor run counters",
    ):
        asyncio.run(
            StrategyV2Workflow().run(
                StrategyV2Input(
                    org_id="org-1",
                    client_id="client-1",
                    product_id="product-1",
                    onboarding_payload_id="payload-1",
                    operator_user_id="operator-1",
                )
            )
        )
