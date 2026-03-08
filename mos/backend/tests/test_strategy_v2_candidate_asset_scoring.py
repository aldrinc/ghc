from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.strategy_v2.contracts import CompetitorAssetConfirmationDecision
from app.strategy_v2 import build_url_candidates, score_candidate_assets, select_top_candidates
from app.strategy_v2.errors import StrategyV2MissingContextError
from app.temporal.activities import strategy_v2_activities
from app.temporal.activities.strategy_v2_activities import (
    prepare_strategy_v2_competitor_asset_candidates_activity,
)


def _stage1_payload(*, competitor_urls: list[str]) -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "stage": 1,
        "product_name": "Product",
        "description": "Product description",
        "price": "$49",
        "competitor_urls": competitor_urls,
        "product_customizable": True,
        "category_niche": "Health & Wellness",
        "market_maturity_stage": "Growth",
        "primary_segment": {
            "name": "Caregivers",
            "size_estimate": "Large",
            "key_differentiator": "Safety-first",
        },
        "bottleneck": "Too much conflicting advice",
        "positioning_gaps": [],
        "competitor_count_validated": 3,
        "primary_icps": [
            "Caregivers",
            "Parents",
            "Budget-conscious buyers",
        ],
    }


def _stub_ingest_strategy_v2_asset_data(**_kwargs) -> dict[str, object]:
    return {
        "candidate_assets": [],
        "social_video_observations": [],
        "external_voc_corpus": [],
        "proof_asset_candidates": [],
        "raw_runs": [],
        "summary": {
            "strategy_config_run_count": 0,
            "planned_actor_run_count": 0,
        },
    }


def test_build_url_candidates_dedupes_and_derives_platforms() -> None:
    candidates = build_url_candidates(
        [
            "https://www.tiktok.com/@brand/video/123",
            "https://www.tiktok.com/@brand/video/123/",
            "https://offer.example.com/page",
        ]
    )

    assert len(candidates) == 2
    tiktok = next(row for row in candidates if row["platform"] == "TIKTOK")
    assert tiktok["asset_kind"] == "VIDEO"
    web = next(row for row in candidates if row["platform"] == "WEB")
    assert web["asset_kind"] == "PAGE"


def test_score_candidate_assets_applies_compliance_hard_gate() -> None:
    scored = score_candidate_assets(
        [
            {
                "candidate_id": "https://competitor.example/red",
                "source_ref": "https://competitor.example/red",
                "competitor_name": "Competitor",
                "platform": "WEB",
                "asset_kind": "PAGE",
                "proof_type": "NONE",
                "estimated_spend_tier": "UNKNOWN",
                "running_duration": "UNKNOWN",
                "compliance_risk": "RED",
                "metrics": {},
            }
        ]
    )

    assert len(scored) == 1
    assert scored[0]["eligible"] is False
    assert "compliance_red" in scored[0]["hard_gate_flags"]


def test_select_top_candidates_enforces_diversity_caps() -> None:
    rows = [
        {
            "candidate_id": "a1",
            "source_ref": "https://a.example/1",
            "competitor_name": "A",
            "platform": "WEB",
            "candidate_asset_score": 95.0,
            "eligible": True,
        },
        {
            "candidate_id": "a2",
            "source_ref": "https://a.example/2",
            "competitor_name": "A",
            "platform": "WEB",
            "candidate_asset_score": 90.0,
            "eligible": True,
        },
        {
            "candidate_id": "b1",
            "source_ref": "https://b.example/1",
            "competitor_name": "B",
            "platform": "WEB",
            "candidate_asset_score": 85.0,
            "eligible": True,
        },
    ]

    selected = select_top_candidates(
        rows,
        max_candidates=10,
        max_per_competitor=1,
        max_per_platform=10,
    )

    assert len(selected) == 2
    assert {row["competitor_name"] for row in selected} == {"A", "B"}


def test_select_top_candidates_tie_breaks_by_candidate_id_asc() -> None:
    rows = [
        {
            "candidate_id": "b",
            "source_ref": "https://b.example/1",
            "competitor_name": "B",
            "platform": "WEB",
            "candidate_asset_score": 90.0,
            "eligible": True,
        },
        {
            "candidate_id": "a",
            "source_ref": "https://a.example/1",
            "competitor_name": "A",
            "platform": "WEB",
            "candidate_asset_score": 90.0,
            "eligible": True,
        },
    ]

    selected = select_top_candidates(
        rows,
        max_candidates=2,
        max_per_competitor=2,
        max_per_platform=2,
    )

    assert [row["candidate_id"] for row in selected] == ["a", "b"]


def test_prepare_competitor_asset_candidates_requires_three_eligible_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest_strategy_v2_asset_data,
    )
    params = {
        "stage1": _stage1_payload(
            competitor_urls=[
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-1",
            ]
        )
    }

    with pytest.raises(StrategyV2MissingContextError, match="at least 3 scored candidate assets"):
        prepare_strategy_v2_competitor_asset_candidates_activity(params)


def test_prepare_competitor_asset_candidates_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest_strategy_v2_asset_data,
    )
    params = {
        "stage1": _stage1_payload(
            competitor_urls=[
                "https://competitor-a.example/asset-1",
                "https://competitor-b.example/asset-2",
                "https://competitor-c.example/asset-3",
            ]
        )
    }

    result = prepare_strategy_v2_competitor_asset_candidates_activity(params)

    assert isinstance(result.get("candidates"), list)
    assert len(result["candidates"]) >= 3
    assert all("candidate_asset_score" in row for row in result["candidates"])
    summary = result.get("candidate_summary")
    assert isinstance(summary, dict)
    assert summary.get("selected_candidate_count", 0) >= 3
    assert isinstance(summary.get("selected_candidate_ids"), list)
    selection_limits = summary.get("selection_limits")
    assert isinstance(selection_limits, dict)
    assert selection_limits == {
        "max_candidates": strategy_v2_activities._H2_MAX_CANDIDATE_ASSETS,
        "max_per_competitor": strategy_v2_activities._H2_MAX_CANDIDATES_PER_COMPETITOR,
        "max_per_platform": strategy_v2_activities._H2_MAX_CANDIDATES_PER_PLATFORM,
    }
    operator_confirmation_policy = summary.get("operator_confirmation_policy")
    assert isinstance(operator_confirmation_policy, dict)
    assert operator_confirmation_policy == {
        "min_confirmed_assets": strategy_v2_activities._MIN_STAGE1_COMPETITORS,
        "target_confirmed_assets": strategy_v2_activities._H2_TARGET_CONFIRMED_ASSETS,
        "max_confirmed_assets": strategy_v2_activities._H2_MAX_CONFIRMED_ASSETS,
    }


def test_competitor_asset_confirmation_decision_caps_confirmed_assets() -> None:
    payload = {
        "operator_user_id": "operator-1",
        "decision_mode": "manual",
        "confirmed_asset_refs": [f"https://asset.example/{idx}" for idx in range(16)],
        "reviewed_candidate_ids": ["id-1", "id-2", "id-3"],
        "attestation": {
            "reviewed_evidence": True,
            "understands_impact": True,
        },
    }
    with pytest.raises(ValidationError, match="at most 15 items"):
        CompetitorAssetConfirmationDecision.model_validate(payload)
