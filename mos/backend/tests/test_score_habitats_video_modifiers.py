from __future__ import annotations

from app.strategy_v2 import score_habitats


def _base_habitat(*, name: str) -> dict[str, object]:
    return {
        "habitat_name": name,
        "habitat_type": "REDDIT",
        "threads_50_plus": "Y",
        "threads_200_plus": "Y",
        "threads_1000_plus": "N",
        "posts_last_3mo": "Y",
        "posts_last_6mo": "Y",
        "posts_last_12mo": "Y",
        "recency_ratio": "MAJORITY_RECENT",
        "exact_category": "Y",
        "purchasing_comparing": "Y",
        "personal_usage": "Y",
        "adjacent_only": "N",
        "first_person_narratives": "Y",
        "trigger_events": "Y",
        "fear_frustration_shame": "Y",
        "specific_dollar_or_time": "N",
        "long_detailed_posts": "Y",
        "purchase_intent_density": "SOME",
        "discusses_spending": "Y",
        "recommendation_threads": "Y",
        "relevance_pct": "25_TO_50_PCT",
        "dominated_by_offtopic": "N",
        "competitor_brand_count": "1-3",
        "trend_direction": "HIGHER",
        "membership_trend": "GROWING",
        "post_frequency_trend": "INCREASING",
        "publicly_accessible": "Y",
        "text_based_content": "Y",
        "target_language": "Y",
        "no_rate_limiting": "Y",
        "language_samples": [
            {
                "word_count": 180,
                "has_trigger_event": "Y",
                "has_failed_solution": "Y",
                "has_identity_language": "Y",
                "has_specific_outcome": "Y",
            }
        ],
    }


def test_score_habitats_any_failed_mining_field_caps_score() -> None:
    gated = _base_habitat(name="Gate Fail")
    gated["text_based_content"] = "N"

    results = score_habitats([gated])
    row = results["habitats"][0]
    assert row["mining_gate_applied"] is True
    assert row["final_score"] <= 25.0
    assert "text_based_content" in row["mining_gate_failures"]


def test_score_habitats_does_not_add_target_language_failure_when_no_text_content() -> None:
    gated = _base_habitat(name="No Text")
    gated["text_based_content"] = "N"
    gated["target_language"] = "CANNOT_DETERMINE"

    results = score_habitats([gated])
    row = results["habitats"][0]

    assert row["mining_gate_applied"] is True
    assert "text_based_content" in row["mining_gate_failures"]
    assert "target_language" not in row["mining_gate_failures"]


def test_score_habitats_applies_video_modifiers_for_video_fields() -> None:
    baseline = _base_habitat(name="Baseline")
    video_boosted = _base_habitat(name="Video Boosted")
    video_boosted.update(
        {
            "viral_videos_found": "Y",
            "comment_sections_active": "Y",
            "contains_purchase_intent": "Y",
            "creator_diversity": "MANY",
            "video_count_scraped": 120,
            "median_view_count": 74000,
            "viral_video_count": 9,
        }
    )

    results = score_habitats([baseline, video_boosted])
    rows_by_name = {str(row["habitat_name"]): row for row in results["habitats"]}
    base_row = rows_by_name["Baseline"]
    video_row = rows_by_name["Video Boosted"]

    assert base_row["video_modifiers_applied"]["applied"] is False
    assert video_row["video_modifiers_applied"]["applied"] is True
    assert video_row["components"]["emotional_depth"] > base_row["components"]["emotional_depth"]
    assert video_row["components"]["language_quality"] > base_row["components"]["language_quality"]
    assert video_row["components"]["buyer_density"] > base_row["components"]["buyer_density"]
    assert video_row["components"]["signal_to_noise"] > base_row["components"]["signal_to_noise"]
