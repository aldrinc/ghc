from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.temporal.activities import strategy_v2_activities
from app.temporal.activities.strategy_v2_activities import (
    StrategyV2MissingContextError,
    StrategyV2SchemaValidationError,
    _build_scraped_data_manifest,
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


def test_validate_agent1_output_source_file_grounding_rejects_unknown_files() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="Unknown source_file entries"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "habitat_observations": [{"source_file": "unexpected_file.json"}],
                "mining_plan": [{"source_file": "allowed_file.json"}],
                "excluded_source_files": [],
            },
            scraped_data_manifest={"raw_scraped_data_files": [{"file_name": "allowed_file.json"}]},
        )


def test_validate_agent1_output_source_file_grounding_requires_mining_subset_of_observations() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="mining_plan must be a subset"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "habitat_observations": [{"source_file": "observed_file.json"}],
                "mining_plan": [{"source_file": "mined_file.json"}],
                "excluded_source_files": ["mined_file.json"],
            },
            scraped_data_manifest={
                "raw_scraped_data_files": [
                    {"file_name": "observed_file.json"},
                    {"file_name": "mined_file.json"},
                ]
            },
        )


def test_validate_agent1_output_source_file_grounding_requires_exact_union_coverage() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="exact source-file coverage"):
        _validate_agent1_output_source_file_grounding(
            agent01_output={
                "habitat_observations": [{"source_file": "observed_file.json"}],
                "mining_plan": [{"source_file": "observed_file.json"}],
                "excluded_source_files": [],
            },
            scraped_data_manifest={
                "raw_scraped_data_files": [
                    {"file_name": "observed_file.json"},
                    {"file_name": "missing_file.json"},
                ]
            },
        )


def test_validate_agent1_output_source_file_grounding_accepts_exact_coverage_with_exclusions() -> None:
    _validate_agent1_output_source_file_grounding(
        agent01_output={
            "habitat_observations": [{"source_file": "observed_file.json"}],
            "mining_plan": [{"source_file": "observed_file.json"}],
            "excluded_source_files": ["excluded_file.json"],
        },
        scraped_data_manifest={
            "raw_scraped_data_files": [
                {"file_name": "observed_file.json"},
                {"file_name": "excluded_file.json"},
            ]
        },
    )
