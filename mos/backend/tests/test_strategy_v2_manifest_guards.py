from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.temporal.activities import strategy_v2_activities
from app.temporal.activities.strategy_v2_activities import (
    StrategyV2MissingContextError,
    StrategyV2SchemaValidationError,
    _build_scraped_data_manifest,
    _derive_agent1_outputs_from_file_assessments,
    _extract_manifest_date_range,
    _normalize_scraped_item_for_manifest,
    _validate_agent1_output_source_file_grounding,
)


def test_normalize_scraped_item_for_manifest_hydrates_google_organic_results() -> None:
    payload = _normalize_scraped_item_for_manifest(
        {
            "organicResults": [
                {
                    "title": "Best Herbal Sleep Remedies",
                    "description": "Evidence and safety interactions for common herbs.",
                    "url": "https://example.com/herbal-remedies",
                }
            ]
        }
    )

    assert payload["title"] == "Best Herbal Sleep Remedies"
    assert payload["source_url"] == "https://example.com/herbal-remedies"
    assert "Evidence and safety interactions" in payload["body"]
    assert payload["organic_results_sample"][0]["description"].startswith("Evidence and safety")


def test_normalize_scraped_item_for_manifest_preserves_full_text_and_all_comment_rows() -> None:
    long_body = "x" * 4000
    payload = _normalize_scraped_item_for_manifest(
        {
            "url": "https://example.com/long-post",
            "body": long_body,
            "comments": [{"text": f"comment-{index}"} for index in range(20)],
            "hashtags": [f"tag-{index}" for index in range(30)],
        }
    )

    assert payload["body"] == long_body
    assert len(payload["comments_sample"]) == 20
    assert len(payload["hashtags"]) == 30


def test_manifest_date_range_includes_tiktok_epoch_timestamps() -> None:
    epoch_earliest = 1_700_000_000
    epoch_latest = 1_700_000_500
    expected_earliest = datetime.fromtimestamp(epoch_earliest, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    expected_latest = datetime.fromtimestamp(epoch_latest, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    date_range = _extract_manifest_date_range(
        [
            {"createTime": epoch_latest},
            {"createTime": epoch_earliest},
        ]
    )

    assert isinstance(date_range, dict)
    assert date_range["earliest"] == expected_earliest
    assert date_range["latest"] == expected_latest


def test_build_scraped_data_manifest_excludes_unusable_runs_and_logs_web_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_calls: list[dict[str, object]] = []

    def _capture_warning(message: str, *, extra: dict[str, object] | None = None) -> None:
        warning_calls.append({"message": message, "extra": extra or {}})

    monkeypatch.setattr(strategy_v2_activities._LOGGER, "warning", _capture_warning)
    manifest = _build_scraped_data_manifest(
        apify_context={
            "raw_runs": [
                {
                    "actor_id": "apify/web-scraper",
                    "run_id": "run-web-1",
                    "dataset_id": "dataset-web-1",
                    "status": "SUCCEEDED",
                    "config_id": "cfg-web-1",
                    "config_metadata": {"target_id": "HT-WEB-001", "habitat_name": "example.com", "habitat_type": "Web"},
                    "input_payload": {"startUrls": [{"url": "https://example.com"}]},
                    "items": [{"url": "https://example.com/article", "text": ""}],
                },
                {
                    "actor_id": "clockworks/tiktok-scraper",
                    "run_id": "run-tt-1",
                    "dataset_id": "dataset-tt-1",
                    "status": "SUCCEEDED",
                    "config_id": "cfg-tt-1",
                    "config_metadata": {"target_id": "HT-TT-001", "habitat_name": "tiktok.com", "habitat_type": "Social_Video"},
                    "input_payload": {"postURLs": ["https://www.tiktok.com/@acct/video/1"]},
                    "items": [{"error": "Profile is private"}],
                },
                {
                    "actor_id": "practicaltools/apify-reddit-api",
                    "run_id": "run-rd-1",
                    "dataset_id": "dataset-rd-1",
                    "status": "SUCCEEDED",
                    "config_id": "cfg-rd-1",
                    "config_metadata": {
                        "target_id": "HT-REDDIT-001",
                        "habitat_name": "reddit.com/r/herbalism",
                        "habitat_type": "Reddit",
                    },
                    "input_payload": {"startUrls": [{"url": "https://www.reddit.com/r/herbalism"}]},
                    "items": [
                        {
                            "source_url": "https://www.reddit.com/r/herbalism/comments/abc123/example",
                            "title": "What helped with herb timing?",
                            "selftext": "I need real examples and safety notes.",
                        }
                    ],
                },
            ],
            "candidate_assets": [],
            "social_video_observations": [],
            "external_voc_corpus": [],
        },
        competitor_analysis={"asset_observation_sheets": []},
    )

    assert manifest["run_count"] == 1
    assert manifest["total_run_count"] == 3
    assert manifest["excluded_run_count"] == 2
    assert len(manifest["raw_scraped_data_files"]) == 1
    excluded_reasons = {str(row.get("exclusion_reason")) for row in manifest["excluded_runs"] if isinstance(row, dict)}
    assert excluded_reasons == {"WEB_SCRAPER_EMPTY_TEXT", "RUN_CONTAINS_ERROR_PAYLOAD"}
    assert len(warning_calls) == 1
    assert warning_calls[0]["message"] == "strategy_v2.web_scraper_empty_text_detected"


def test_build_scraped_data_manifest_raises_when_all_runs_are_excluded() -> None:
    with pytest.raises(StrategyV2MissingContextError, match="all runs were excluded"):
        _build_scraped_data_manifest(
            apify_context={
                "raw_runs": [
                    {
                        "actor_id": "apify/web-scraper",
                        "run_id": "run-web-1",
                        "dataset_id": "dataset-web-1",
                        "status": "SUCCEEDED",
                        "config_id": "cfg-web-1",
                        "config_metadata": {"target_id": "HT-WEB-001"},
                        "input_payload": {"startUrls": [{"url": "https://example.com"}]},
                        "items": [{"url": "https://example.com/article", "text": ""}],
                    }
                ],
                "candidate_assets": [],
                "social_video_observations": [],
                "external_voc_corpus": [],
            },
            competitor_analysis={"asset_observation_sheets": []},
        )


def test_build_scraped_data_manifest_keeps_google_organic_results_as_text_signal() -> None:
    manifest = _build_scraped_data_manifest(
        apify_context={
            "raw_runs": [
                {
                    "actor_id": "apify/google-search-scraper",
                    "run_id": "run-gs-1",
                    "dataset_id": "dataset-gs-1",
                    "status": "SUCCEEDED",
                    "config_id": "cfg-gs-1",
                    "config_metadata": {"target_id": "HT-SEARCH-001", "habitat_type": "Discovery"},
                    "input_payload": {"queries": ["herbal interactions"]},
                    "items": [
                        {
                            "organicResults": [
                                {
                                    "title": "Herbal Interaction Safety Checklist",
                                    "description": "What to ask before mixing herbs and medications.",
                                    "url": "https://example.com/checklist",
                                }
                            ]
                        }
                    ],
                }
            ],
            "candidate_assets": [],
            "social_video_observations": [],
            "external_voc_corpus": [],
        },
        competitor_analysis={"asset_observation_sheets": []},
    )

    assert manifest["run_count"] == 1
    first_item = manifest["raw_scraped_data_files"][0]["items"][0]
    assert first_item["title"] == "Herbal Interaction Safety Checklist"
    assert "mixing herbs and medications" in first_item["body"]
    assert first_item["source_url"] == "https://example.com/checklist"


def _agent1_file_assessment(
    *,
    source_file: str,
    decision: str = "OBSERVE",
    include_in_mining_plan: bool = False,
    priority_rank: int | None = None,
) -> dict[str, object]:
    observation_projection = (
        _agent1_observation_projection(
            source_file=source_file,
            include_in_mining_plan=include_in_mining_plan,
            priority_rank=priority_rank,
        )
        if decision != "EXCLUDE"
        else None
    )
    return {
        "source_file": source_file,
        "decision": decision,
        "exclude_reason": "Insufficient usable evidence in file." if decision == "EXCLUDE" else "",
        "include_in_mining_plan": include_in_mining_plan,
        "observation_projection": observation_projection,
    }


def _agent1_observation(
    *,
    source_file: str,
    include_in_mining_plan: bool = False,
    priority_rank: int | None = None,
) -> dict[str, object]:
    observation_id = f"obs-{source_file.replace('.', '-')}"
    return {
        "observation_id": observation_id,
        "habitat_name": f"Habitat for {source_file}",
        "habitat_type": "TEXT_COMMUNITY",
        "url_pattern": f"https://example.com/{source_file}",
        "items_in_file": 12,
        "data_quality": "CLEAN",
        "observation_sheet": {
            "threads_50_plus": "Y",
            "threads_200_plus": "N",
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
            "specific_dollar_or_time": "Y",
            "long_detailed_posts": "Y",
            "comparison_discussions": "Y",
            "price_value_mentions": "Y",
            "post_purchase_experience": "Y",
            "relevance_pct": "OVER_50_PCT",
            "dominated_by_offtopic": "N",
            "competitor_brands_mentioned": "Y",
            "competitor_brand_count": "1-3",
            "competitor_ads_present": "N",
            "trend_direction": "HIGHER",
            "seasonal_patterns": "N",
            "seasonal_description": "N/A",
            "habitat_age": "3_TO_7YR",
            "membership_trend": "GROWING",
            "post_frequency_trend": "INCREASING",
            "publicly_accessible": "Y",
            "text_based_content": "Y",
            "target_language": "Y",
            "no_rate_limiting": "Y",
            "purchase_intent_density": "SOME",
            "discusses_spending": "Y",
            "recommendation_threads": "Y",
            "reusability": "PATTERN_REUSABLE",
        },
        "language_samples": [
            {
                "sample_id": "S1",
                "evidence_ref": f"{source_file}::item[0]",
                "word_count": 120,
                "has_trigger_event": "Y",
                "has_failed_solution": "Y",
                "has_identity_language": "Y",
                "has_specific_outcome": "Y",
            }
        ],
        "video_extension": None,
        "competitive_overlap": {
            "competitors_in_data": ["Competitor A"],
            "overlap_level": "LOW",
            "whitespace_opportunity": "Y",
        },
        "trend_lifecycle": {
            "trend_direction": "HIGHER",
            "lifecycle_stage": "GROWING",
        },
        "mining_gate": {
            "status": "PASS",
            "failed_fields": [],
            "reason": "All mining requirements satisfied.",
        },
        "rank_score": 77,
        "estimated_yield": 22,
        "evidence_refs": [f"{source_file}::item[0]"],
        "include_in_mining_plan": include_in_mining_plan,
        "priority_rank": priority_rank,
        "target_voc_types": ["PAIN_LANGUAGE"] if include_in_mining_plan else [],
        "sampling_strategy": "Chronological high-signal scan." if include_in_mining_plan else None,
        "platform_behavior_note": "Narrative posts with detailed symptom context." if include_in_mining_plan else None,
        "compliance_flags": "",
    }


def _agent1_observation_projection(
    *,
    source_file: str,
    include_in_mining_plan: bool = False,
    priority_rank: int | None = None,
) -> dict[str, object]:
    projection = _agent1_observation(
        source_file=source_file,
        include_in_mining_plan=include_in_mining_plan,
        priority_rank=priority_rank,
    )
    projection.pop("source_file", None)
    projection.pop("observation_id", None)
    projection.pop("include_in_mining_plan", None)
    return projection


def test_validate_agent1_output_source_file_grounding_rejects_unknown_files() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="Unknown source_file entries"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    _agent1_file_assessment(
                        source_file="unexpected_file.json",
                        decision="EXCLUDE",
                    )
                ]
            },
            scraped_data_manifest={"raw_scraped_data_files": [{"file_name": "allowed_file.json"}]},
        )


def test_validate_agent1_output_source_file_grounding_rejects_excluded_rows_marked_for_mining() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="cannot mark an EXCLUDE file_assessments row for mining"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    _agent1_file_assessment(
                        source_file="mined_file.json",
                        decision="EXCLUDE",
                        include_in_mining_plan=True,
                    )
                ]
            },
            scraped_data_manifest={
                "raw_scraped_data_files": [{"file_name": "mined_file.json"}]
            },
        )


def test_validate_agent1_output_source_file_grounding_requires_exact_union_coverage() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="exact source-file coverage"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    _agent1_file_assessment(
                        source_file="observed_file.json",
                        include_in_mining_plan=True,
                        priority_rank=1,
                    )
                ]
            },
            scraped_data_manifest={
                "raw_scraped_data_files": [
                    {"file_name": "observed_file.json"},
                    {"file_name": "missing_file.json"},
                ]
            },
        )


def test_validate_agent1_output_source_file_grounding_accepts_exact_coverage_with_exclusions() -> None:
    derived = _derive_agent1_outputs_from_file_assessments(
        agent01_output={
            "file_assessments": [
                _agent1_file_assessment(
                    source_file="observed_file.json",
                    include_in_mining_plan=True,
                    priority_rank=1,
                ),
                _agent1_file_assessment(
                    source_file="excluded_file.json",
                    decision="EXCLUDE",
                ),
            ],
        },
        scraped_data_manifest={
            "raw_scraped_data_files": [
                {"file_name": "observed_file.json"},
                {"file_name": "excluded_file.json"},
            ]
        },
    )
    assert [row["source_file"] for row in derived["habitat_observations"]] == ["observed_file.json"]
    assert derived["excluded_source_files"] == ["excluded_file.json"]
    assert [row["source_file"] for row in derived["mining_plan"]] == ["observed_file.json"]


def test_validate_agent1_output_source_file_grounding_rejects_mined_rows_without_target_voc_types() -> None:
    observation_projection = _agent1_observation_projection(
        source_file="observed_file.json",
        include_in_mining_plan=True,
        priority_rank=1,
    )
    observation_projection["target_voc_types"] = []

    with pytest.raises(
        StrategyV2SchemaValidationError,
        match="target_voc_types must be a non-empty array when include_in_mining_plan=true",
    ):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    {
                        **_agent1_file_assessment(
                            source_file="observed_file.json",
                            include_in_mining_plan=True,
                        ),
                        "observation_projection": observation_projection,
                    }
                ]
            },
            scraped_data_manifest={"raw_scraped_data_files": [{"file_name": "observed_file.json"}]},
        )


def test_validate_agent1_output_source_file_grounding_rejects_include_in_mining_plan_mismatch() -> None:
    observation_projection = _agent1_observation_projection(
        source_file="observed_file.json",
        include_in_mining_plan=False,
        priority_rank=None,
    )

    with pytest.raises(
        StrategyV2SchemaValidationError,
        match="mining_plan_projection is missing required fields",
    ):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    {
                        **_agent1_file_assessment(
                            source_file="observed_file.json",
                            include_in_mining_plan=True,
                        ),
                        "observation_projection": observation_projection,
                    }
                ]
            },
            scraped_data_manifest={"raw_scraped_data_files": [{"file_name": "observed_file.json"}]},
        )


def test_validate_agent1_output_source_file_grounding_rejects_missing_observation_projection() -> None:
    with pytest.raises(
        StrategyV2SchemaValidationError,
        match="observation_projection must be an object when decision=OBSERVE",
    ):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "file_assessments": [
                    {
                        "decision": "OBSERVE",
                        "source_file": "observed_file.json",
                        "exclude_reason": "",
                        "include_in_mining_plan": False,
                        "observation_projection": None,
                    }
                ]
            },
            scraped_data_manifest={"raw_scraped_data_files": [{"file_name": "observed_file.json"}]},
        )
