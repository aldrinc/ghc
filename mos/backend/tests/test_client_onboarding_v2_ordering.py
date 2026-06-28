import asyncio

import pytest

from app.temporal.workflows.client_onboarding import ClientOnboardingInput, ClientOnboardingWorkflow
from app.temporal.workflows import client_onboarding as onboarding_workflow_module


def test_client_onboarding_starts_strategy_v2_before_precanon_when_enabled(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append(("execute_activity", activity_name))
        if activity_name == "check_strategy_v2_enabled_activity":
            assert payload["org_id"] == "org-1"
            assert payload["client_id"] == "client-1"
            return {"enabled": True}
        if activity_name == "mark_client_onboarding_workflow_activity":
            assert payload["org_id"] == "org-1"
            assert payload["client_id"] == "client-1"
            assert payload["product_id"] == "product-1"
            assert payload["temporal_workflow_id"] == "wf-1"
            assert payload["temporal_run_id"] == "run-1"
            assert payload["status"] == "completed"
            assert payload["payload_out"] == {"status": "foundation_complete"}
            return {"updated": True}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    async def _fake_execute_child_workflow(*_args, **_kwargs):  # noqa: ANN003
        workflow_fn, payload = _args[:2]
        calls.append(("execute_child_workflow", getattr(workflow_fn, "__qualname__", str(workflow_fn))))
        assert payload.org_id == "org-1"
        assert payload.client_id == "client-1"
        assert payload.product_id == "product-1"
        assert payload.foundation_only is True
        return {"status": "foundation_complete"}

    class _Info:
        workflow_id = "wf-1"
        run_id = "run-1"

    monkeypatch.setattr(onboarding_workflow_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(onboarding_workflow_module.workflow, "execute_child_workflow", _fake_execute_child_workflow)
    monkeypatch.setattr(onboarding_workflow_module.workflow, "info", lambda: _Info())

    asyncio.run(
        ClientOnboardingWorkflow().run(
            ClientOnboardingInput(
                org_id="org-1",
                client_id="client-1",
                onboarding_payload_id="payload-1",
                product_id="product-1",
                business_model="one-time",
                funnel_position="cold_traffic",
                target_platforms=["Meta"],
                target_regions=["US"],
                existing_proof_assets=["Customer testimonials"],
                brand_voice_notes="Direct, clear, compliant voice guidance.",
            )
        )
    )

    assert ("execute_child_workflow", "StrategyV2Workflow.run") in calls
    assert ("execute_activity", "mark_client_onboarding_workflow_activity") in calls


def test_client_onboarding_errors_when_strategy_v2_disabled(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append(("execute_activity", activity_name))
        if activity_name == "check_strategy_v2_enabled_activity":
            assert payload["org_id"] == "org-1"
            assert payload["client_id"] == "client-1"
            return {"enabled": False}
        if activity_name == "mark_client_onboarding_workflow_activity":
            assert payload["status"] == "failed"
            assert "strategy_v2_enabled is false" in payload["error_message"]
            return {"updated": True}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    async def _fake_execute_child_workflow(*_args, **_kwargs):  # noqa: ANN003
        calls.append(("execute_child_workflow", "StrategyV2Workflow.run"))
        raise AssertionError("Strategy V2 child should not start when disabled.")

    class _Info:
        workflow_id = "wf-1"
        run_id = "run-1"

    monkeypatch.setattr(onboarding_workflow_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(onboarding_workflow_module.workflow, "execute_child_workflow", _fake_execute_child_workflow)
    monkeypatch.setattr(onboarding_workflow_module.workflow, "info", lambda: _Info())

    with pytest.raises(RuntimeError, match="strategy_v2_enabled is false"):
        asyncio.run(
            ClientOnboardingWorkflow().run(
                ClientOnboardingInput(
                    org_id="org-1",
                    client_id="client-1",
                    onboarding_payload_id="payload-1",
                    product_id="product-1",
                    business_model="one-time",
                    funnel_position="cold_traffic",
                    target_platforms=["Meta"],
                    target_regions=["US"],
                    existing_proof_assets=["Customer testimonials"],
                    brand_voice_notes="Direct, clear, compliant voice guidance.",
                )
            )
        )

    assert ("execute_child_workflow", "StrategyV2Workflow.run") not in calls
    assert ("execute_activity", "mark_client_onboarding_workflow_activity") in calls
