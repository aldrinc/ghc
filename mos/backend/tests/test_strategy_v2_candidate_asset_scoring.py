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


def _honest_herbalist_stage1_urls() -> list[str]:
    return [
        "https://ancientremedies.com",
        "https://gaiaherbs.com",
        "https://gaiaherbs.com/pages/meet-your-herb",
        "https://consumerlab.com/join",
        "https://learningherbs.com/herbmentor",
        "https://theherbalacademy.com/about-us",
        "https://mountainroseherbs.com/herbal-education",
        "https://trchealthcare.com/product/natmed-pro",
        "https://blog.herbsociety.org/research-education/other-research-education/chestnut-school-of-herbal-medicine-teaches-online",
        "https://bbb.org/us/wa/shelton/profile/health-products/learningherbscom-llc-1296-22025340",
    ]


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


def test_score_candidate_assets_rejects_directory_hosts_and_prefers_first_party_pages() -> None:
    scored = score_candidate_assets(
        build_url_candidates(
            [
                "https://gaiaherbs.com",
                "https://blog.herbsociety.org/research-education/other-research-education/chestnut-school-of-herbal-medicine-teaches-online",
                "https://bbb.org/us/wa/shelton/profile/health-products/learningherbscom-llc-1296-22025340",
            ]
        )
    )

    by_ref = {str(row["source_ref"]): row for row in scored}
    assert by_ref["https://bbb.org/us/wa/shelton/profile/health-products/learningherbscom-llc-1296-22025340"]["eligible"] is False
    assert "non_competitor_directory_source" in by_ref[
        "https://bbb.org/us/wa/shelton/profile/health-products/learningherbscom-llc-1296-22025340"
    ]["hard_gate_flags"]
    assert by_ref["https://gaiaherbs.com"]["score_components"]["source_relevance_signal"] > by_ref[
        "https://blog.herbsociety.org/research-education/other-research-education/chestnut-school-of-herbal-medicine-teaches-online"
    ]["score_components"]["source_relevance_signal"]


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
    assert selection_limits.get("max_candidates") == strategy_v2_activities._H2_MAX_CANDIDATE_ASSETS
    operator_confirmation_policy = summary.get("operator_confirmation_policy")
    assert isinstance(operator_confirmation_policy, dict)
    assert operator_confirmation_policy.get("target_confirmed_assets") == strategy_v2_activities._H2_TARGET_CONFIRMED_ASSETS


def test_prepare_competitor_asset_candidates_prefers_scraped_caption_over_seed_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _stub_ingest(**_kwargs) -> dict[str, object]:
        return {
            "candidate_assets": [
                {
                    **build_url_candidates(["https://gaiaherbs.com/pages/herb-reference-guide"])[0],
                    "headline_or_caption": "Herb Reference Guide",
                    "compliance_risk": "GREEN",
                }
            ],
            "social_video_observations": [],
            "external_voc_corpus": [],
            "proof_asset_candidates": [],
            "raw_runs": [],
            "summary": {
                "strategy_config_run_count": 1,
                "planned_actor_run_count": 1,
            },
        }

    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest,
    )
    params = {
        "stage1": _stage1_payload(
            competitor_urls=[
                "https://gaiaherbs.com/pages/herb-reference-guide",
                "https://gaiaherbs.com/pages/meet-your-herb",
                "https://ancientremedies.com",
            ]
        )
    }

    result = prepare_strategy_v2_competitor_asset_candidates_activity(params)
    by_ref = {str(row["source_ref"]): row for row in result["candidates"]}
    assert by_ref["https://gaiaherbs.com/pages/herb-reference-guide"]["headline_or_caption"] == "Herb Reference Guide"


def test_prepare_competitor_asset_candidates_relaxes_single_platform_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _stub_ingest(**_kwargs) -> dict[str, object]:
        return {
            "candidate_assets": build_url_candidates(_honest_herbalist_stage1_urls()),
            "social_video_observations": [],
            "external_voc_corpus": [],
            "proof_asset_candidates": [],
            "raw_runs": [],
            "summary": {
                "strategy_config_run_count": 2,
                "planned_actor_run_count": 2,
            },
        }

    monkeypatch.setattr(
        strategy_v2_activities,
        "_ingest_strategy_v2_asset_data",
        _stub_ingest,
    )
    monkeypatch.setattr(strategy_v2_activities, "_H2_MAX_CANDIDATE_ASSETS", 12)
    monkeypatch.setattr(strategy_v2_activities, "_H2_MAX_CANDIDATES_PER_PLATFORM", 6)

    result = prepare_strategy_v2_competitor_asset_candidates_activity(
        {"stage1": _stage1_payload(competitor_urls=_honest_herbalist_stage1_urls())}
    )

    summary = result["candidate_summary"]
    assert summary["selected_candidate_count"] > 6
    assert "https://gaiaherbs.com" in summary["selected_candidate_ids"]
    assert "https://bbb.org/us/wa/shelton/profile/health-products/learningherbscom-llc-1296-22025340" not in summary[
        "selected_candidate_ids"
    ]
    assert summary["selection_limits"]["max_per_platform"] == 12
    assert summary["selection_limits"]["configured_max_per_platform"] == 6


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
