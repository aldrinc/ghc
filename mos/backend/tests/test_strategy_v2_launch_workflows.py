from __future__ import annotations

import asyncio

from app.temporal.workflows import strategy_v2_launch as strategy_v2_launch_module
from app.temporal.workflows.strategy_v2_launch import (
    StrategyV2AngleCampaignLaunchInput,
    StrategyV2AngleCampaignLaunchWorkflow,
    StrategyV2AngleIterationInput,
    StrategyV2AngleIterationWorkflow,
)


def test_strategy_v2_angle_campaign_launch_runs_meta_tracking_setup(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append((activity_name, payload))
        if activity_name == "create_campaign_activity":
            return {"campaign_id": "campaign-1"}
        if activity_name == "create_strategy_v2_launch_artifacts_activity":
            return {
                "experiment_specs": [
                    {
                        "id": "exp_001",
                        "name": "Angle A",
                        "variants": [{"id": "var_a_1", "name": "Variant A1"}],
                    }
                ]
            }
        if activity_name == "create_funnels_from_experiments_activity":
            return {
                "funnels": [
                    {
                        "experiment_id": "exp_001",
                        "variant_id": "var_a_1",
                        "funnel": {"funnel_id": "funnel-123"},
                    }
                ],
                "media_enrichment_jobs": [],
            }
        if activity_name == "configure_generated_funnels_meta_tracking_activity":
            assert payload["campaign_id"] == "campaign-1"
            assert payload["funnel_ids"] == ["funnel-123"]
            return {"status": "configured", "pixelId": "pixel-123"}
        if activity_name == "persist_strategy_v2_launch_record_activity":
            return {"id": "launch-record-1"}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    class _Info:
        workflow_id = "strategy-v2-angle-launch-workflow-id"
        run_id = "strategy-v2-angle-launch-run-id"

    monkeypatch.setattr(strategy_v2_launch_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(strategy_v2_launch_module.workflow, "info", lambda: _Info())

    result = asyncio.run(
        StrategyV2AngleCampaignLaunchWorkflow().run(
            StrategyV2AngleCampaignLaunchInput(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                source_strategy_v2_workflow_run_id="source-run-1",
                source_strategy_v2_temporal_workflow_id="source-temporal-1",
                launch_workflow_run_id="launch-run-1",
                operator_user_id="user-1",
                channels=["meta"],
                asset_brief_types=["image"],
                experiment_variant_policy="angle_launch_standard_v1",
                launch_items=[
                    {
                        "launch_type": "initial_angle",
                        "angle": {"angle_id": "A01", "angle_name": "Angle A"},
                        "launch_key": "launch-key-1",
                        "campaign_name": "Launch Campaign",
                        "strategy_v2_packet": {},
                        "source_stage3": {"stage3": True},
                        "source_offer": {"offer": True},
                        "source_copy": {"copy": True},
                        "strategy_v2_copy_context": {},
                        "angle_run_id": "angle-run-1",
                        "selected_ums_id": "ums-1",
                        "selected_variant_id": "variant-1",
                        "source_stage3_artifact_id": "stage3-art-1",
                        "source_offer_artifact_id": "offer-art-1",
                        "source_copy_artifact_id": "copy-art-1",
                        "source_copy_context_artifact_id": "copy-context-art-1",
                    }
                ],
            )
        )
    )

    assert result["campaign_ids"] == ["campaign-1"]
    assert [name for name, _payload in calls] == [
        "create_campaign_activity",
        "create_strategy_v2_launch_artifacts_activity",
        "create_funnels_from_experiments_activity",
        "configure_generated_funnels_meta_tracking_activity",
        "persist_strategy_v2_launch_record_activity",
    ]


def test_strategy_v2_angle_iteration_runs_meta_tracking_setup(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append((activity_name, payload))
        if activity_name == "apply_strategy_v2_angle_selection_activity":
            return {"stage2": {}}
        if activity_name == "validate_strategy_v2_offer_data_readiness_activity":
            return {"status": "ready"}
        if activity_name == "build_strategy_v2_offer_variants_activity":
            return {
                "variants": [{"variant_id": "variant-1"}],
                "composite_results": {"variants": [{"variant_id": "variant-1", "score": 1.0}]},
            }
        if activity_name == "finalize_strategy_v2_offer_winner_activity":
            return {
                "stage3": {},
                "copy_context": {},
                "stage3_artifact_id": "stage3-art-1",
                "offer_artifact_id": "offer-art-1",
                "copy_context_artifact_id": "copy-context-art-1",
                "awareness_matrix": {},
            }
        if activity_name == "run_strategy_v2_copy_pipeline_activity":
            return {
                "copy_payload": {"angle_run_id": "angle-run-1"},
                "copy_artifact_id": "copy-art-1",
            }
        if activity_name == "finalize_strategy_v2_copy_approval_activity":
            return {}
        if activity_name == "create_strategy_v2_launch_artifacts_activity":
            return {
                "experiment_specs": [
                    {
                        "id": "exp_001",
                        "name": "Angle A",
                        "variants": [{"id": "var_a_1", "name": "Variant A1"}],
                    }
                ]
            }
        if activity_name == "create_funnels_from_experiments_activity":
            return {
                "funnels": [
                    {
                        "experiment_id": "exp_001",
                        "variant_id": "var_a_1",
                        "funnel": {"funnel_id": "funnel-ums-123"},
                    }
                ],
                "media_enrichment_jobs": [],
            }
        if activity_name == "configure_generated_funnels_meta_tracking_activity":
            assert payload["campaign_id"] == "campaign-1"
            assert payload["funnel_ids"] == ["funnel-ums-123"]
            return {"status": "configured", "pixelId": "pixel-123"}
        if activity_name == "persist_strategy_v2_launch_record_activity":
            return {"id": "launch-record-1"}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    class _Info:
        workflow_id = "strategy-v2-angle-iteration-workflow-id"
        run_id = "strategy-v2-angle-iteration-run-id"

    monkeypatch.setattr(strategy_v2_launch_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(strategy_v2_launch_module.workflow, "info", lambda: _Info())
    monkeypatch.setattr(strategy_v2_launch_module, "build_strategy_v2_downstream_packet", lambda **_kwargs: {})

    result = asyncio.run(
        StrategyV2AngleIterationWorkflow().run(
            StrategyV2AngleIterationInput(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                source_strategy_v2_workflow_run_id="source-run-1",
                source_strategy_v2_temporal_workflow_id="source-temporal-1",
                launch_workflow_run_id="launch-run-1",
                operator_user_id="user-1",
                campaign_id="campaign-1",
                channels=["meta"],
                asset_brief_types=["image"],
                launch_name_prefix="Launch Prefix",
                experiment_variant_policy="angle_launch_standard_v1",
                base_angle_run_id="base-angle-run-1",
                selected_angle={"angle_id": "A01", "angle_name": "Angle A"},
                stage1={"product_name": "Launch Product"},
                ranked_angle_candidates=[{"angle": {"angle_id": "A01", "angle_name": "Angle A"}}],
                offer_pipeline_payload={
                    "pair_scoring": {
                        "ranked_pairs": [{"pair_id": "pair-1", "ums_id": "ums-1"}],
                    }
                },
                offer_operator_inputs={
                    "brand_voice_notes": "Clear and specific.",
                },
                angle_synthesis_payload={"summary": "Angle synthesis"},
                onboarding_payload_id=None,
                ums_launch_items=[
                    {
                        "launch_key": "launch-key-1",
                        "selected_ums_id": "ums-1",
                        "pair": {"pair_id": "pair-1", "ums_id": "ums-1"},
                    }
                ],
            )
        )
    )

    assert result["campaign_ids"] == ["campaign-1"]
    assert [name for name, _payload in calls] == [
        "apply_strategy_v2_angle_selection_activity",
        "validate_strategy_v2_offer_data_readiness_activity",
        "build_strategy_v2_offer_variants_activity",
        "finalize_strategy_v2_offer_winner_activity",
        "run_strategy_v2_copy_pipeline_activity",
        "finalize_strategy_v2_copy_approval_activity",
        "create_strategy_v2_launch_artifacts_activity",
        "create_funnels_from_experiments_activity",
        "configure_generated_funnels_meta_tracking_activity",
        "persist_strategy_v2_launch_record_activity",
    ]
