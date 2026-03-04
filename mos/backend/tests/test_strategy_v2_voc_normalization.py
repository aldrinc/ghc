from __future__ import annotations

from app.strategy_v2 import score_voc_items
from app.temporal.activities.strategy_v2_activities import _normalize_voc_observations


def _base_voc_row() -> dict[str, object]:
    return {
        "voc_id": "V001",
        "source": "https://www.reddit.com/r/herbalism/comments/example",
        "source_type": "REDDIT",
        "source_url": "https://www.reddit.com/r/herbalism/comments/example",
        "source_author": "user_01",
        "source_date": "2026-02-20",
        "is_hook": "N",
        "hook_format": "NONE",
        "hook_word_count": 0,
        "video_virality_tier": "BASELINE",
        "video_view_count": 0,
        "competitor_saturation": [],
        "in_whitespace": "Y",
        "evidence_ref": "reddit_01::item[0]",
        "quote": (
            "I keep seeing conflicting advice because every guide says something different, "
            "and I'm anxious about making a mistake for my family."
        ),
        "specific_number": "N",
        "specific_product_brand": "N",
        "specific_event_moment": "Y",
        "specific_body_symptom": "N",
        "before_after_comparison": "N",
        "crisis_language": "N",
        "profanity_extreme_punctuation": "N",
        "physical_sensation": "N",
        "identity_change_desire": "N",
        "word_count": 28,
        "clear_trigger_event": "N",
        "named_enemy": "N",
        "shiftable_belief": "N",
        "expectation_vs_reality": "N",
        "headline_ready": "N",
        "usable_content_pct": "50_TO_75_PCT",
        "personal_context": "N",
        "long_narrative": "N",
        "engagement_received": "N",
        "real_person_signals": "N",
        "moderated_community": "N",
        "trigger_event": "conflicting recommendations",
        "pain_problem": "fear of making unsafe herbal choices",
        "desired_outcome": "safe and consistent guidance",
        "failed_prior_solution": "generic internet articles",
        "enemy_blame": "conflicting expert claims",
        "identity_role": "caregiver",
        "fear_risk": "hurting someone unintentionally",
        "emotional_valence": "ANXIETY",
        "durable_psychology": "Y",
        "market_specific": "N",
        "date_bracket": "LAST_6MO",
        "buyer_stage": "PROBLEM_AWARE",
        "solution_sophistication": "EXPERIENCED",
        "compliance_risk": "YELLOW",
    }


def test_normalize_voc_observations_enriches_empty_component_groups() -> None:
    normalized = _normalize_voc_observations([_base_voc_row()])
    row = normalized[0]

    assert row["moderated_community"] == "Y"
    assert row["expectation_vs_reality"] == "Y"
    assert row["crisis_language"] == "Y"

    scored = score_voc_items(normalized)
    item = scored["items"][0]
    assert float(item["adjusted_score"]) > 0.0


def test_normalize_voc_observations_does_not_infer_without_signal() -> None:
    row = _base_voc_row()
    row["source"] = "https://www.instagram.com/p/example"
    row["quote"] = "Herbal newsletter update."
    row["word_count"] = 3

    normalized = _normalize_voc_observations([row])
    enriched = normalized[0]

    assert enriched["crisis_language"] == "N"
    assert enriched["expectation_vs_reality"] == "N"
    assert enriched["moderated_community"] == "N"
