from __future__ import annotations

import asyncio

import pytest
from temporalio.converter import value_to_type
from temporalio.exceptions import ApplicationError

from app.temporal.workflows import creative_production as creative_production_workflow_module
from app.temporal.workflows.creative_production import (
    CreativeProductionInput,
    CreativeProductionWorkflow,
)


def test_creative_production_input_decodes_legacy_payload_without_swipe_fields() -> None:
    payload = {
        "org_id": "org-1",
        "client_id": "client-1",
        "product_id": "product-1",
        "campaign_id": "campaign-1",
        "asset_brief_ids": ["brief-1"],
        "workflow_run_id": "workflow-run-1",
    }

    result = value_to_type(CreativeProductionInput, payload, [])

    assert result == CreativeProductionInput(
        org_id="org-1",
        client_id="client-1",
        product_id="product-1",
        campaign_id="campaign-1",
        asset_brief_ids=["brief-1"],
        swipe_collection_id="",
        swipe_collection_name="",
        swipe_asset_ids=[],
        workflow_run_id="workflow-run-1",
    )


def test_creative_production_workflow_fails_legacy_payload_as_non_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_execute_activity(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Creative production should fail input validation before scheduling activities.")

    monkeypatch.setattr(
        creative_production_workflow_module.workflow,
        "execute_activity",
        _unexpected_execute_activity,
    )

    with pytest.raises(
        ApplicationError,
        match="missing required field\\(s\\): swipe_collection_id, swipe_collection_name, swipe_asset_ids",
    ) as exc_info:
        asyncio.run(
            CreativeProductionWorkflow().run(
                CreativeProductionInput(
                    org_id="org-1",
                    client_id="client-1",
                    product_id="product-1",
                    campaign_id="campaign-1",
                    asset_brief_ids=["brief-1"],
                    workflow_run_id="workflow-run-1",
                )
            )
        )

    assert exc_info.value.type == "InvalidWorkflowInput"
    assert exc_info.value.non_retryable is True


def test_creative_production_workflow_uses_single_attempt_asset_generation_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_calls: list[dict[str, object]] = []

    async def _fake_execute_activity(activity_fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        recorded_calls.append({"activity": activity_fn, "kwargs": kwargs})
        if activity_fn is creative_production_workflow_module.generate_assets_for_brief_activity:
            return {"asset_ids": ["asset-1"]}
        return None

    async def _fake_wait_condition(_predicate):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        creative_production_workflow_module.workflow,
        "execute_activity",
        _fake_execute_activity,
    )
    monkeypatch.setattr(
        creative_production_workflow_module.workflow,
        "wait_condition",
        _fake_wait_condition,
    )

    asyncio.run(
        CreativeProductionWorkflow().run(
            CreativeProductionInput(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                campaign_id="campaign-1",
                asset_brief_ids=["brief-1"],
                swipe_collection_id="collection-1",
                swipe_collection_name="Default",
                swipe_asset_ids=["swipe-1"],
                workflow_run_id="workflow-run-1",
            )
        )
    )

    retry_policy = recorded_calls[0]["kwargs"]["retry_policy"]
    assert retry_policy.maximum_attempts == 1
