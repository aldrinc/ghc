from app.temporal.activities.experiment_activities import (
    _chunk_experiment_specs,
    _collect_expected_variant_pairs,
    _find_unverified_claim_pattern,
    _validate_asset_brief_variant_coverage,
)


def test_chunk_experiment_specs_splits_evenly() -> None:
    experiments = [{"id": f"exp_{idx}", "variants": [{"id": "v1"}]} for idx in range(10)]
    chunks = _chunk_experiment_specs(experiments, chunk_size=4)

    assert [len(chunk) for chunk in chunks] == [4, 4, 2]


def test_collect_expected_variant_pairs() -> None:
    experiments = [
        {"id": "exp_a", "variants": [{"id": "var_1"}, {"id": "var_2"}]},
        {"id": "exp_b", "variants": [{"id": "var_3"}]},
    ]
    pairs = _collect_expected_variant_pairs(experiments)

    assert pairs == {
        ("exp_a", "var_1"),
        ("exp_a", "var_2"),
        ("exp_b", "var_3"),
    }


def test_validate_variant_coverage_raises_when_missing() -> None:
    expected = {("exp_a", "var_1"), ("exp_a", "var_2")}
    briefs = [{"id": "brief_1", "experimentId": "exp_a", "variantId": "var_1", "requirements": []}]

    try:
        _validate_asset_brief_variant_coverage(briefs_raw=briefs, expected_variant_pairs=expected)
    except RuntimeError as exc:
        assert "Missing combinations" in str(exc)
        assert "exp_a:var_2" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected missing variant coverage RuntimeError")


def test_validate_variant_coverage_raises_when_unexpected() -> None:
    expected = {("exp_a", "var_1")}
    briefs = [{"id": "brief_1", "experimentId": "exp_x", "variantId": "var_9", "requirements": []}]

    try:
        _validate_asset_brief_variant_coverage(briefs_raw=briefs, expected_variant_pairs=expected)
    except RuntimeError as exc:
        assert "unknown experiment/variant combinations" in str(exc)
        assert "exp_x:var_9" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected unexpected variant coverage RuntimeError")


def test_find_unverified_claim_pattern_allows_guardrail_language() -> None:
    value = "Do not claim FDA approval; use cleared only if verified."
    assert _find_unverified_claim_pattern(value) is None


def test_find_unverified_claim_pattern_detects_positive_claim_language() -> None:
    value = "Clinically proven results with patented technology."
    pattern = _find_unverified_claim_pattern(value)
    assert pattern is not None
