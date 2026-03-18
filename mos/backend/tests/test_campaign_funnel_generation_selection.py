from __future__ import annotations

import asyncio

import pytest

from app.temporal.workflows import campaign_funnel_generation as campaign_funnel_generation_module
from app.temporal.workflows.campaign_funnel_generation import (
    CampaignFunnelGenerationInput,
    CampaignFunnelGenerationWorkflow,
    _filter_experiment_specs,
)


def _experiment_specs() -> list[dict]:
    return [
        {
            "id": "exp_001",
            "name": "Angle A",
            "variants": [
                {"id": "var_a_1", "name": "Variant A1"},
                {"id": "var_a_2", "name": "Variant A2"},
            ],
        },
        {
            "id": "exp_002",
            "name": "Angle B",
            "variants": [
                {"id": "var_b_1", "name": "Variant B1"},
            ],
        },
    ]


def test_filter_experiment_specs_keeps_all_variants_when_no_variant_map() -> None:
    filtered = _filter_experiment_specs(
        selected_experiment_ids=["exp_001"],
        experiment_specs=_experiment_specs(),
        variant_ids_by_experiment={},
    )

    assert len(filtered) == 1
    assert filtered[0]["id"] == "exp_001"
    assert [variant["id"] for variant in filtered[0]["variants"]] == ["var_a_1", "var_a_2"]


def test_filter_experiment_specs_applies_variant_selection() -> None:
    filtered = _filter_experiment_specs(
        selected_experiment_ids=["exp_001", "exp_002"],
        experiment_specs=_experiment_specs(),
        variant_ids_by_experiment={
            "exp_001": ["var_a_2"],
            "exp_002": ["var_b_1"],
        },
    )

    assert [spec["id"] for spec in filtered] == ["exp_001", "exp_002"]
    assert [variant["id"] for variant in filtered[0]["variants"]] == ["var_a_2"]
    assert [variant["id"] for variant in filtered[1]["variants"]] == ["var_b_1"]


def test_filter_experiment_specs_raises_for_unknown_variant_selection() -> None:
    with pytest.raises(RuntimeError, match="Selected variants were not found for experiment exp_001: var_missing"):
        _filter_experiment_specs(
            selected_experiment_ids=["exp_001"],
            experiment_specs=_experiment_specs(),
            variant_ids_by_experiment={"exp_001": ["var_missing"]},
        )


def test_filter_experiment_specs_raises_when_variant_map_has_unselected_experiment() -> None:
    with pytest.raises(RuntimeError, match="which is not in selected experiment_ids"):
        _filter_experiment_specs(
            selected_experiment_ids=["exp_001"],
            experiment_specs=_experiment_specs(),
            variant_ids_by_experiment={"exp_002": ["var_b_1"]},
        )


def test_campaign_funnel_generation_runs_meta_tracking_setup_activity(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _fake_execute_activity(activity_fn, payload, **_kwargs):  # noqa: ANN001, ANN003
        activity_name = getattr(activity_fn, "__name__", str(activity_fn))
        calls.append((activity_name, payload))
        if activity_name == "fetch_experiment_specs_activity":
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
                "non_fatal_errors": [],
                "media_enrichment_jobs": [],
            }
        if activity_name == "configure_generated_funnels_meta_tracking_activity":
            assert payload["funnel_ids"] == ["funnel-123"]
            return {"status": "configured", "pixelId": "pixel-123"}
        if activity_name == "create_asset_briefs_for_experiments_activity":
            return {"briefs": []}
        raise AssertionError(f"Unexpected activity call: {activity_name}")

    class _Info:
        workflow_id = "campaign-funnel-workflow-id"
        run_id = "campaign-funnel-run-id"

    monkeypatch.setattr(campaign_funnel_generation_module.workflow, "execute_activity", _fake_execute_activity)
    monkeypatch.setattr(campaign_funnel_generation_module.workflow, "wait", lambda tasks: asyncio.gather(*tasks))
    monkeypatch.setattr(campaign_funnel_generation_module.workflow, "info", lambda: _Info())

    result = asyncio.run(
        CampaignFunnelGenerationWorkflow().run(
            CampaignFunnelGenerationInput(
                org_id="org-1",
                client_id="client-1",
                product_id="product-1",
                campaign_id="campaign-1",
                experiment_ids=["exp_001"],
                async_media_enrichment=False,
            )
        )
    )

    assert result["meta_tracking_setup"]["status"] == "configured"
    assert [name for name, _payload in calls] == [
        "fetch_experiment_specs_activity",
        "create_funnels_from_experiments_activity",
        "configure_generated_funnels_meta_tracking_activity",
        "create_asset_briefs_for_experiments_activity",
    ]
