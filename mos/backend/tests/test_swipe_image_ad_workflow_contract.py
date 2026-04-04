from __future__ import annotations

import asyncio

import pytest

from app.temporal.workflows import swipe_image_ad as swipe_image_ad_workflow_module
from app.temporal.workflows.swipe_image_ad import SwipeImageAdInput, SwipeImageAdWorkflow


def test_swipe_image_ad_workflow_uses_single_attempt_activity_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}

    async def _fake_execute_activity(activity_fn, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        recorded["activity"] = activity_fn
        recorded["kwargs"] = kwargs
        return {"asset_ids": ["asset-1"]}

    monkeypatch.setattr(
        swipe_image_ad_workflow_module.workflow,
        "execute_activity",
        _fake_execute_activity,
    )

    result = asyncio.run(
        SwipeImageAdWorkflow().run(
            SwipeImageAdInput(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                asset_brief_id="brief-1",
                campaign_id="campaign-1",
                company_swipe_id="swipe-1",
            )
        )
    )

    assert result == {"asset_ids": ["asset-1"]}
    retry_policy = recorded["kwargs"]["retry_policy"]
    assert retry_policy.maximum_attempts == 1
