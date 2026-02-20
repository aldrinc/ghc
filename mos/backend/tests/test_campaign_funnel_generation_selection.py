from __future__ import annotations

import pytest

from app.temporal.workflows.campaign_funnel_generation import _filter_experiment_specs


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
