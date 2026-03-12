from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from types import SimpleNamespace

import pytest

from app.temporal.activities import asset_activities
from app.temporal.activities import swipe_image_ad_activities


def _install_image_generation_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan_items: list[dict[str, str]],
    existing_assets: list[SimpleNamespace],
    swipe_callable,
):
    logs: list[dict[str, object]] = []
    updated_assets: dict[str, dict[str, object]] = {}
    asset_by_id = {asset.id: asset for asset in existing_assets}
    expected_batch_id = asset_activities._build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-1",
    )

    @contextmanager
    def _fake_session_scope():
        yield object()

    class _FakeAssetsRepository:
        def __init__(self, session) -> None:
            self.session = session

        def list(self, **_kwargs):
            return list(existing_assets)

        def get(self, org_id: str, asset_id: str):
            return asset_by_id.get(asset_id)

        def update(self, org_id: str, asset_id: str, **fields):
            asset = asset_by_id.get(asset_id)
            if asset is None:
                raise AssertionError(f"Unexpected asset update for {asset_id}")
            for key, value in fields.items():
                setattr(asset, key, value)
            updated_assets[asset_id] = fields
            return asset

    class _FakeWorkflowsRepository:
        def __init__(self, session) -> None:
            self.session = session

        def log_activity(self, **kwargs) -> None:
            logs.append(kwargs)

    copy_artifact = SimpleNamespace(
        id="copy-artifact-1",
        data={
            "schemaVersion": 2,
            "assetBriefId": "brief-1",
            "sourceBriefArtifactId": "brief-artifact-1",
            "sourceBriefSha256": "brief-sha-1",
            "sourceFunnelId": None,
            "copyPacks": [
                {
                    "id": "copy-pack-1",
                    "requirementIndex": 0,
                    "channel": "facebook",
                    "format": "image",
                    "funnelStage": "top-of-funnel",
                    "angle": "Angle",
                    "hook": "Hook",
                    "creativeConcept": "Concept",
                    "metaPrimaryText": "Primary text",
                    "metaHeadline": "Headline",
                    "metaDescription": "Description",
                    "claimsGuardrails": [],
                }
            ],
        },
    )
    plan_artifact = SimpleNamespace(
        id="plan-artifact-1",
        data={
            "assetBriefId": "brief-1",
            "sourceBriefArtifactId": "brief-artifact-1",
            "adCopyPackArtifactId": "copy-artifact-1",
            "batchId": expected_batch_id,
            "sourceSetKey": "default_initial_swipes_v1",
            "items": plan_items,
        },
    )

    monkeypatch.setattr(asset_activities, "session_scope", _fake_session_scope)
    monkeypatch.setattr(asset_activities, "ArtifactsRepository", lambda session: object())
    monkeypatch.setattr(asset_activities, "AssetsRepository", _FakeAssetsRepository)
    monkeypatch.setattr(asset_activities, "WorkflowsRepository", _FakeWorkflowsRepository)
    monkeypatch.setattr(
        asset_activities,
        "_extract_brief",
        lambda **_kwargs: (
            {
                "creativeConcept": "Concept",
                "requirements": [
                    {
                        "channel": "facebook",
                        "format": "image",
                        "angle": "Angle",
                        "hook": "Hook",
                    }
                ],
                "constraints": [],
                "toneGuidelines": [],
                "visualGuidelines": [],
            },
            "brief-artifact-1",
        ),
    )
    monkeypatch.setattr(asset_activities, "_validate_brief_scope", lambda **_kwargs: None)
    monkeypatch.setattr(asset_activities, "_get_or_create_ad_copy_pack_artifact", lambda **_kwargs: copy_artifact)

    def _fake_create_plan(**kwargs):
        assert kwargs["batch_id"] == expected_batch_id
        return plan_artifact

    monkeypatch.setattr(asset_activities, "_create_creative_generation_plan_artifact", _fake_create_plan)
    monkeypatch.setattr(swipe_image_ad_activities, "generate_swipe_image_ad_activity", swipe_callable)

    return {
        "asset_by_id": asset_by_id,
        "expected_batch_id": expected_batch_id,
        "logs": logs,
        "updated_assets": updated_assets,
    }


def test_generate_assets_for_brief_activity_resumes_completed_image_plan_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_batch_id = asset_activities._build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-1",
    )
    existing_asset = SimpleNamespace(
        id="existing-asset-1",
        ai_metadata={
            "assetBriefId": "brief-1",
            "creativeGenerationBatchId": expected_batch_id,
            "creativeGenerationPlanItemId": "plan-item-1",
        },
        content={"assetBriefId": "brief-1"},
    )
    swipe_calls: list[dict[str, object]] = []

    def _fake_swipe(params):
        swipe_calls.append(params)
        asset_by_id["new-asset-2"] = SimpleNamespace(
            id="new-asset-2",
            ai_metadata={"assetBriefId": "brief-1"},
            content={"assetBriefId": "brief-1"},
        )
        return {"asset_ids": ["new-asset-2"]}

    installed = _install_image_generation_stubs(
        monkeypatch,
        plan_items=[
            {
                "id": "plan-item-1",
                "batchId": expected_batch_id,
                "assetBriefId": "brief-1",
                "requirementIndex": 0,
                "channel": "facebook",
                "format": "image",
                "funnelStage": "top-of-funnel",
                "angle": "Angle",
                "hook": "Hook",
                "companySwipeId": "swipe-1",
                "sourceLabel": "10.png",
                "sourceMediaUrl": "https://example.com/10.png",
                "copyPackId": "copy-pack-1",
                "productImagePolicy": False,
                "sourceSetKey": "default_initial_swipes_v1",
            },
            {
                "id": "plan-item-2",
                "batchId": expected_batch_id,
                "assetBriefId": "brief-1",
                "requirementIndex": 0,
                "channel": "facebook",
                "format": "image",
                "funnelStage": "top-of-funnel",
                "angle": "Angle",
                "hook": "Hook",
                "companySwipeId": "swipe-2",
                "sourceLabel": "11.png",
                "sourceMediaUrl": "https://example.com/11.png",
                "copyPackId": "copy-pack-1",
                "productImagePolicy": False,
                "sourceSetKey": "default_initial_swipes_v1",
            },
        ],
        existing_assets=[existing_asset],
        swipe_callable=_fake_swipe,
    )
    asset_by_id = installed["asset_by_id"]

    result = asset_activities.generate_assets_for_brief_activity(
        {
            "org_id": "org-1",
            "client_id": "client-1",
            "campaign_id": "campaign-1",
            "product_id": "product-1",
            "asset_brief_id": "brief-1",
            "workflow_run_id": "workflow-run-1",
        }
    )

    assert result["asset_ids"] == ["existing-asset-1", "new-asset-2"]
    assert len(swipe_calls) == 1
    assert swipe_calls[0]["company_swipe_id"] == "swipe-2"
    assert swipe_calls[0]["creative_generation_batch_id"] == expected_batch_id
    assert swipe_calls[0]["creative_generation_plan_item_id"] == "plan-item-2"
    assert installed["updated_assets"]["new-asset-2"]["ai_metadata"]["creativeGenerationPlanItemId"] == "plan-item-2"
    assert asset_by_id["new-asset-2"].ai_metadata["adCopyPackId"] == "copy-pack-1"


def test_generate_assets_for_brief_activity_preserves_plan_order_with_parallel_swipes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_batch_id = asset_activities._build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-1",
    )
    monkeypatch.setattr(asset_activities.settings, "CREATIVE_IMAGE_PLAN_ITEM_MAX_CONCURRENCY", 2)

    completion_order: list[str] = []
    start_barrier = threading.Barrier(2)

    def _parallel_swipe(params):
        plan_item_id = str(params["creative_generation_plan_item_id"])
        asset_id = "new-asset-1" if plan_item_id == "plan-item-1" else "new-asset-2"
        start_barrier.wait(timeout=1)
        if plan_item_id == "plan-item-1":
            time.sleep(0.05)
        asset_by_id[asset_id] = SimpleNamespace(
            id=asset_id,
            ai_metadata={"assetBriefId": "brief-1"},
            content={"assetBriefId": "brief-1"},
        )
        completion_order.append(plan_item_id)
        return {"asset_ids": [asset_id]}

    installed = _install_image_generation_stubs(
        monkeypatch,
        plan_items=[
            {
                "id": "plan-item-1",
                "batchId": expected_batch_id,
                "assetBriefId": "brief-1",
                "requirementIndex": 0,
                "channel": "facebook",
                "format": "image",
                "funnelStage": "top-of-funnel",
                "angle": "Angle",
                "hook": "Hook",
                "companySwipeId": "swipe-1",
                "sourceLabel": "10.png",
                "sourceMediaUrl": "https://example.com/10.png",
                "copyPackId": "copy-pack-1",
                "productImagePolicy": False,
                "sourceSetKey": "default_initial_swipes_v1",
            },
            {
                "id": "plan-item-2",
                "batchId": expected_batch_id,
                "assetBriefId": "brief-1",
                "requirementIndex": 0,
                "channel": "facebook",
                "format": "image",
                "funnelStage": "top-of-funnel",
                "angle": "Angle",
                "hook": "Hook",
                "companySwipeId": "swipe-2",
                "sourceLabel": "11.png",
                "sourceMediaUrl": "https://example.com/11.png",
                "copyPackId": "copy-pack-1",
                "productImagePolicy": False,
                "sourceSetKey": "default_initial_swipes_v1",
            },
        ],
        existing_assets=[],
        swipe_callable=_parallel_swipe,
    )
    asset_by_id = installed["asset_by_id"]

    result = asset_activities.generate_assets_for_brief_activity(
        {
            "org_id": "org-1",
            "client_id": "client-1",
            "campaign_id": "campaign-1",
            "product_id": "product-1",
            "asset_brief_id": "brief-1",
            "workflow_run_id": "workflow-run-1",
        }
    )

    assert completion_order == ["plan-item-2", "plan-item-1"]
    assert result["asset_ids"] == ["new-asset-1", "new-asset-2"]
    assert installed["updated_assets"]["new-asset-1"]["ai_metadata"]["creativeGenerationPlanItemId"] == "plan-item-1"
    assert installed["updated_assets"]["new-asset-2"]["ai_metadata"]["creativeGenerationPlanItemId"] == "plan-item-2"


def test_generate_assets_for_brief_activity_compacts_swipe_generation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_batch_id = asset_activities._build_creative_generation_batch_id(
        execution_key="workflow-run-1",
        asset_brief_id="brief-1",
    )

    def _failing_swipe(_params):
        raise RuntimeError("render failed " + ("x" * 5000))

    _install_image_generation_stubs(
        monkeypatch,
        plan_items=[
            {
                "id": "plan-item-1",
                "batchId": expected_batch_id,
                "assetBriefId": "brief-1",
                "requirementIndex": 0,
                "channel": "facebook",
                "format": "image",
                "funnelStage": "top-of-funnel",
                "angle": "Angle",
                "hook": "Hook",
                "companySwipeId": "swipe-1",
                "sourceLabel": "10.png",
                "sourceMediaUrl": "https://example.com/10.png",
                "copyPackId": "copy-pack-1",
                "productImagePolicy": False,
                "sourceSetKey": "default_initial_swipes_v1",
            }
        ],
        existing_assets=[],
        swipe_callable=_failing_swipe,
    )

    with pytest.raises(RuntimeError) as exc_info:
        asset_activities.generate_assets_for_brief_activity(
            {
                "org_id": "org-1",
                "client_id": "client-1",
                "campaign_id": "campaign-1",
                "product_id": "product-1",
                "asset_brief_id": "brief-1",
                "workflow_run_id": "workflow-run-1",
            }
        )

    error_text = str(exc_info.value)
    assert "plan_item_id=plan-item-1" in error_text
    assert "RuntimeError: render failed" in error_text
    assert len(error_text) < 900
    assert error_text.count("x") < 500
