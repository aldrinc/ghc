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

    with pytest.raises(RuntimeError, match="stop_after_foundational_activity"):
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
