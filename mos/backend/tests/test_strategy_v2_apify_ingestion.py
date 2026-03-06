from __future__ import annotations

import threading

import pytest

from app.strategy_v2 import apify_ingestion as ingestion
from app.strategy_v2.apify_ingestion import run_strategy_v2_apify_ingestion
from app.strategy_v2.errors import StrategyV2SchemaValidationError
from app.temporal.activities import strategy_v2_activities


def test_run_strategy_v2_apify_ingestion_disabled_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "false")
    with pytest.raises(RuntimeError, match="STRATEGY_V2_APIFY_ENABLED=true"):
        run_strategy_v2_apify_ingestion(
            source_refs=["https://competitor-a.example/landing"],
            include_ads_context=True,
            include_social_video=True,
            include_external_voc=True,
        )


def test_load_strategy_v2_apify_config_defaults_max_actor_runs_to_100(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRATEGY_V2_APIFY_MAX_ACTOR_RUNS", raising=False)
    config = ingestion.load_strategy_v2_apify_config()
    assert config.max_actor_runs == 100


def test_run_strategy_v2_apify_ingestion_enforces_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS", "apify/web-scraper")

    class _UnusedApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _UnusedApifyClient)

    with pytest.raises(RuntimeError, match="allowlist"):
        run_strategy_v2_apify_ingestion(
            source_refs=["https://competitor-a.example/landing"],
            include_ads_context=True,
            include_social_video=False,
            include_external_voc=False,
        )


def test_run_strategy_v2_apify_ingestion_normalizes_external_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api,apify/web-scraper",
    )
    monkeypatch.setenv("STRATEGY_V2_APIFY_REDDIT_ACTOR_ID", "practicaltools/apify-reddit-api")
    monkeypatch.setenv("STRATEGY_V2_APIFY_WEB_ACTOR_ID", "apify/web-scraper")
    monkeypatch.setenv("STRATEGY_V2_APIFY_META_ACTOR_ID", "practicaltools/apify-reddit-api")
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self._run_map: dict[str, str] = {}
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            self._counter += 1
            run_id = f"run-{self._counter}"
            self._run_map[run_id] = actor_id
            return {"id": run_id}

        def fetch_run(self, run_id: str) -> dict:
            _ = self._run_map[run_id]
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = kwargs
            return self.fetch_run(run_id)

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = limit
            if "run-1" in dataset_id:
                return [
                    {
                        "source_url": "https://www.reddit.com/r/sleep/comments/abc123",
                        "quote": "I keep trying routines and nights still collapse.",
                        "author": "user_a",
                        "likes": 12,
                        "replies": 4,
                    }
                ]
            return [
                {
                    "source_url": "https://forum.example.com/thread-44",
                    "quote": "Nothing helped until we changed the timing sequence.",
                    "author": "user_b",
                    "likes": 8,
                    "replies": 2,
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        source_refs=["https://www.reddit.com/r/sleep/comments/abc123"],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
    )
    assert payload["enabled"] is True
    assert isinstance(payload.get("raw_runs"), list) and len(payload["raw_runs"]) >= 2
    external_corpus = payload.get("external_voc_corpus")
    assert isinstance(external_corpus, list) and external_corpus
    assert any("APIFY_EXTERNAL" in row.get("flags", []) for row in external_corpus)
    assert all(
        str(row.get("source_type") or "")
        in {"REDDIT", "FORUM", "BLOG_COMMENT", "REVIEW_SITE", "QA", "TIKTOK_COMMENT", "IG_COMMENT", "YT_COMMENT", "VIDEO_HOOK"}
        for row in external_corpus
    )
    assert all(str(row.get("source_type") or "") != "apify_comment" for row in external_corpus)
    proof_candidates = payload.get("proof_asset_candidates")
    assert isinstance(proof_candidates, list) and proof_candidates
    assert all(len(row.get("source_refs", [])) >= 2 for row in proof_candidates)


def test_run_strategy_v2_apify_ingestion_rejects_empty_apify_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    with pytest.raises(RuntimeError, match="at least one valid config object"):
        run_strategy_v2_apify_ingestion(
            apify_configs=[],
            include_ads_context=False,
            include_social_video=True,
            include_external_voc=True,
        )


def test_require_agent00b_executable_configs_filters_placeholder_actor_id() -> None:
    strategy_v2_activities._require_agent00b_executable_configs(
        {
            "configurations": [
                {
                    "config_id": "VOC_AGENT0B_OUTPUT",
                    "platform": "MULTI",
                    "mode": "STRATEGY+CONFIGS",
                    "actor_id": "N/A",
                    "input": {"startUrls": [{"url": "https://www.youtube.com/results?search_query=herbalism"}], "maxResults": 10},
                    "metadata": {},
                },
                {
                    "config_id": "VOC_AGENT0B_YT_001",
                    "platform": "YOUTUBE",
                    "mode": "VIRAL_DISCOVERY",
                    "actor_id": "streamers/youtube-scraper",
                    "input": {"startUrls": [{"url": "https://www.youtube.com/results?search_query=herbalism"}], "maxResults": 10},
                    "metadata": {},
                },
            ]
        }
    )


def test_require_agent00b_executable_configs_allows_all_placeholder_rows() -> None:
    strategy_v2_activities._require_agent00b_executable_configs(
        {
            "configurations": [
                {
                    "config_id": "VOC_AGENT0B_OUTPUT",
                    "platform": "YOUTUBE",
                    "mode": "VIRAL_DISCOVERY",
                    "actor_id": "streamers/youtube-scraper",
                    "input": {"startUrls": [{"url": "N/A"}], "maxResults": 10},
                    "metadata": {},
                }
            ]
        }
    )


def test_extract_apify_configs_from_agent_strategies_filters_placeholder_rows() -> None:
    normalized = strategy_v2_activities._extract_apify_configs_from_agent_strategies(
        habitat_strategy={
            "apify_configs_tier1": [
                {
                    "config_id": "HT-REDDIT-01",
                    "actor_id": "practicaltools/apify-reddit-api",
                    "input": {"startUrls": [{"url": "https://www.reddit.com/r/herbalism"}], "maxItems": 10},
                    "metadata": {"target_id": "HT-001"},
                }
            ],
            "apify_configs_tier2": [
                {
                    "config_id": "DISC-01",
                    "actor_id": "apify/google-search-scraper",
                    "input": {"queries": ["herbalism community"], "maxPagesPerQuery": 1},
                    "metadata": {"target_id": "DISC-001"},
                }
            ],
        },
        video_strategy={
            "configurations": [
                {
                    "config_id": "VOC_AGENT0B_OUTPUT",
                    "platform": "MULTI",
                    "mode": "STRATEGY+CONFIGS",
                    "actor_id": "N/A",
                    "input": {"startUrls": [{"url": "N/A"}], "maxResults": 10},
                    "metadata": {},
                },
                {
                    "config_id": "SV-IG-01",
                    "platform": "INSTAGRAM",
                    "mode": "VIRAL_DISCOVERY",
                    "actor_id": "apify/instagram-scraper",
                    "input": {"directUrls": ["https://www.instagram.com/reel/abc123"]},
                    "metadata": {"target_id": "SV-001"},
                },
            ]
        },
    )
    assert isinstance(normalized, list)
    assert len(normalized) == 3
    assert {str(row.get("config_id") or "") for row in normalized} == {"HT-REDDIT-01", "DISC-01", "SV-IG-01"}


def test_build_agent2_evidence_rows_normalizes_discovery_and_other_source_platforms() -> None:
    evidence_rows, diagnostics = strategy_v2_activities._build_agent2_evidence_rows(
        existing_corpus=[],
        merged_voc_artifact_rows=[],
        scraped_data_manifest={
            "raw_scraped_data_files": [
                {
                    "file_name": "apify_google-search-scraper_abc123.json",
                    "source_platform": "Discovery",
                    "habitat_name": "google search",
                    "habitat_type": "Other",
                    "strategy_target_id": "DISC-HT-001",
                    "items": [
                        {
                            "source_url": "https://example.com/checklist",
                            "title": "Herbal Interaction Safety Checklist",
                            "body": "What to ask before mixing herbs and medications.",
                        }
                    ],
                },
                {
                    "file_name": "apify_web-scraper_xyz789.json",
                    "source_platform": "Other",
                    "habitat_name": "web scrape",
                    "habitat_type": "Other",
                    "strategy_target_id": "DISC-HT-002",
                    "items": [
                        {
                            "source_url": "https://example.com/forum-thread",
                            "title": "Forum thread",
                            "body": "Detailed anecdote from a user.",
                        }
                    ],
                },
            ]
        },
    )
    assert diagnostics["accepted_rows"] == 2
    assert len(evidence_rows) == 2
    assert all(str(row.get("source_type") or "") == "FORUM" for row in evidence_rows)


def test_run_strategy_v2_apify_ingestion_executes_apify_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_V2_APIFY_DISCOVERY_FANOUT_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_V2_APIFY_COMMENT_ENRICHMENT_ENABLED", "false")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "clockworks/tiktok-scraper,practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs
            self._run_actor_map: dict[str, str] = {}
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            _ = input_payload
            self._counter += 1
            run_id = f"run-{self._counter}"
            self._run_actor_map[run_id] = actor_id
            return {"id": run_id}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = limit
            run_id = dataset_id.replace("dataset-", "")
            actor_id = self._run_actor_map[run_id]
            if actor_id == "clockworks/tiktok-scraper":
                return [
                    {
                        "url": "https://www.tiktok.com/@duolingo/video/7300",
                        "caption": "Timing sequence fixed our bedtime collapse.",
                        "views": 1900,
                        "likes": 170,
                        "comments": 23,
                        "shares": 14,
                        "followers": 32000,
                        "createTimeISO": "2026-02-20T00:00:00+00:00",
                    }
                ]
            return [
                {
                    "source_url": "https://www.reddit.com/r/sleep/comments/xyz222",
                    "quote": "Switching timing order reduced wake-ups in week two.",
                    "likes": 21,
                    "replies": 6,
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_tiktok_01",
                "actor_id": "clockworks/tiktok-scraper",
                "input": {"profiles": ["https://www.tiktok.com/@duolingo"], "maxItems": 1},
                "metadata": {"platform": "TIKTOK", "mode": "VIRAL_DISCOVERY", "target_id": "HT-TIKTOK-01"},
            },
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-01"},
            },
        ],
        include_ads_context=False,
        include_social_video=True,
        include_external_voc=True,
    )

    raw_runs = payload.get("raw_runs")
    assert isinstance(raw_runs, list) and len(raw_runs) == 2
    assert {str(row.get("config_id")) for row in raw_runs} == {"cfg_tiktok_01", "cfg_reddit_01"}
    assert payload.get("summary", {}).get("run_count") == 2

    candidate_assets = payload.get("candidate_assets")
    assert isinstance(candidate_assets, list) and candidate_assets
    assert any(
        isinstance(row, dict)
        and str(row.get("raw_source_artifact_id") or "").startswith("cfg_tiktok_01:clockworks/tiktok-scraper:")
        for row in candidate_assets
    )


def test_run_strategy_v2_apify_ingestion_continues_when_single_actor_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_V2_APIFY_DISCOVERY_FANOUT_ENABLED", "false")
    monkeypatch.setenv("STRATEGY_V2_APIFY_COMMENT_ENRICHMENT_ENABLED", "false")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "clockworks/tiktok-scraper,practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs
            self._run_actor_map: dict[str, str] = {}
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            _ = input_payload
            if actor_id == "practicaltools/apify-reddit-api":
                raise RuntimeError("400 Bad Request")
            self._counter += 1
            run_id = f"run-{self._counter}"
            self._run_actor_map[run_id] = actor_id
            return {"id": run_id}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = limit
            run_id = dataset_id.replace("dataset-", "")
            actor_id = self._run_actor_map[run_id]
            if actor_id == "clockworks/tiktok-scraper":
                return [
                    {
                        "url": "https://www.tiktok.com/@duolingo/video/7300",
                        "caption": "Timing sequence fixed our bedtime collapse.",
                        "views": 1900,
                        "likes": 170,
                        "comments": 23,
                        "shares": 14,
                        "followers": 32000,
                        "createTimeISO": "2026-02-20T00:00:00+00:00",
                    }
                ]
            return []

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_tiktok_01",
                "actor_id": "clockworks/tiktok-scraper",
                "input": {"profiles": ["https://www.tiktok.com/@duolingo"], "maxItems": 1},
                "metadata": {"platform": "TIKTOK", "mode": "VIRAL_DISCOVERY", "target_id": "HT-TIKTOK-01"},
            },
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-01"},
            },
        ],
        include_ads_context=False,
        include_social_video=True,
        include_external_voc=True,
    )
    raw_runs = payload.get("raw_runs")
    assert isinstance(raw_runs, list)
    assert len(raw_runs) == 2
    statuses = {str(row.get("status") or "") for row in raw_runs if isinstance(row, dict)}
    assert statuses == {"SUCCEEDED", "FAILED"}
    assert payload.get("summary", {}).get("run_count") == 2


def test_run_strategy_v2_apify_ingestion_splits_video_hook_and_comment_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS", "clockworks/tiktok-scraper")
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            _ = actor_id
            _ = input_payload
            return {"id": "run-1"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "url": "https://www.tiktok.com/@duolingo/video/7300",
                    "caption": "Stop doing random bedtime hacks.",
                    "views": 400000,
                    "comments": [
                        {
                            "comment": "This worked when we fixed timing first.",
                            "author": "user_a",
                            "likes": 12,
                        }
                    ],
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_tiktok_01",
                "actor_id": "clockworks/tiktok-scraper",
                "input": {"postURLs": ["https://www.tiktok.com/@duolingo/video/7300"], "maxItems": 1},
                "metadata": {"platform": "TIKTOK", "mode": "VOC_MINING", "target_id": "HT-TIKTOK-02"},
            }
        ],
        include_ads_context=False,
        include_social_video=True,
        include_external_voc=True,
    )
    external_items = payload.get("external_voc_items")
    assert isinstance(external_items, list) and external_items
    source_types = {str(row.get("source_type") or "") for row in external_items if isinstance(row, dict)}
    assert "VIDEO_HOOK" in source_types
    assert "TIKTOK_COMMENT" in source_types


def test_run_strategy_v2_apify_ingestion_canonicalizes_reddit_strategy_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    started_payloads: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            started_payloads.append({"actor_id": actor_id, "input_payload": input_payload})
            return {"id": "run-1"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "source_url": "https://www.reddit.com/r/sleep/comments/xyz222",
                    "quote": "Sample quote for ingestion quality gate.",
                    "body": "Sample body text for ingestion quality gate.",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {
                    "directUrls": ["https://www.reddit.com/r/sleep/comments/xyz222"],
                    "resultsLimit": 2,
                    "sort": "new",
                },
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-02"},
            }
        ],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
    )
    assert payload["enabled"] is True
    assert len(started_payloads) == 1
    run_payload = started_payloads[0]["input_payload"]
    assert run_payload == {
        "startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/xyz222"}],
        "maxItems": 2,
    }


def test_run_strategy_v2_apify_ingestion_caps_reddit_max_items_to_actor_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    started_payloads: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            started_payloads.append({"actor_id": actor_id, "input_payload": input_payload})
            return {"id": "run-1"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "source_url": "https://www.reddit.com/r/sleep/comments/xyz222",
                    "quote": "Sample quote for ingestion quality gate.",
                    "body": "Sample body text for ingestion quality gate.",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {
                    "startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/xyz222"}],
                    "maxItems": 200,
                },
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-03"},
            }
        ],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
    )
    assert payload["enabled"] is True
    assert len(started_payloads) == 1
    run_payload = started_payloads[0]["input_payload"]
    assert run_payload == {
        "startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/xyz222"}],
        "maxItems": 100,
    }


def test_run_strategy_v2_apify_ingestion_canonicalizes_web_strategy_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "apify/web-scraper",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    started_payloads: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            started_payloads.append({"actor_id": actor_id, "input_payload": input_payload})
            return {"id": "run-1"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "url": "https://www.example.com/landing",
                    "bodyText": "Sample body text for ingestion quality gate.",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_web_01",
                "actor_id": "apify/web-scraper",
                "input": {
                    "startUrls": [{"url": "https://www.example.com/landing"}],
                    "maxRequestsPerCrawl": 7,
                    "pageFunction": (
                        "async function pageFunction(context) {\\n"
                        "  const { request, jQuery } = context;\\n"
                        "  return { url: request.url };\\n"
                        "}"
                    ),
                },
                "metadata": {"platform": "WEB", "mode": "DISCOVERY", "target_id": "HT-WEB-01"},
            }
        ],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
    )
    assert payload["enabled"] is True
    assert len(started_payloads) == 1
    run_payload = started_payloads[0]["input_payload"]
    assert run_payload["startUrls"] == [{"url": "https://www.example.com/landing"}]
    assert run_payload["maxCrawlPages"] == 7
    assert run_payload["maxResultsPerCrawl"] == 7
    assert isinstance(run_payload.get("pageFunction"), str)
    assert "\\n" not in run_payload["pageFunction"]


def test_run_strategy_v2_apify_ingestion_emits_progress_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    progress_events: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            _ = actor_id
            _ = input_payload
            return {"id": "run-1"}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            on_poll = kwargs.get("on_poll")
            if callable(on_poll):
                on_poll({"status": "RUNNING", "elapsed_seconds": 1.2})
            return {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "source_url": "https://www.reddit.com/r/sleep/comments/xyz222",
                    "quote": "Sample quote for ingestion quality gate.",
                    "body": "Sample body text for ingestion quality gate.",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-04"},
            }
        ],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
        progress_callback=lambda event: progress_events.append(dict(event)),
    )

    assert payload["enabled"] is True
    event_types = [str(row.get("event") or "") for row in progress_events]
    assert "actor_run_dispatch" in event_types
    assert "actor_run_started" in event_types
    assert "actor_run_poll" in event_types
    assert "actor_run_terminal" in event_types


def test_run_strategy_v2_apify_ingestion_progress_callbacks_run_on_caller_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api",
    )
    monkeypatch.setenv("STRATEGY_V2_APIFY_MAX_PARALLEL_RUNS", "4")
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    caller_thread_id = threading.get_ident()
    callback_thread_ids: list[int] = []
    progress_events: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = args
            _ = kwargs
            self._lock = threading.Lock()
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            _ = actor_id
            _ = input_payload
            with self._lock:
                self._counter += 1
                run_id = f"run-{self._counter}"
            return {"id": run_id}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = run_id
            on_poll = kwargs.get("on_poll")
            if callable(on_poll):
                on_poll({"status": "RUNNING", "elapsed_seconds": 0.1})
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return [
                {
                    "source_url": "https://www.reddit.com/r/sleep/comments/xyz222",
                    "quote": "Sample quote for ingestion quality gate.",
                    "body": "Sample body text for ingestion quality gate.",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    def _record_progress(event: dict[str, object]) -> None:
        callback_thread_ids.append(threading.get_ident())
        progress_events.append(dict(event))

    payload = run_strategy_v2_apify_ingestion(
        apify_configs=[
            {
                "config_id": "cfg_reddit_01",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/a"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-05"},
            },
            {
                "config_id": "cfg_reddit_02",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/b"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-06"},
            },
            {
                "config_id": "cfg_reddit_03",
                "actor_id": "practicaltools/apify-reddit-api",
                "input": {"startUrls": [{"url": "https://www.reddit.com/r/sleep/comments/c"}], "maxItems": 1},
                "metadata": {"platform": "REDDIT", "mode": "VOC_MINING", "target_id": "HT-REDDIT-07"},
            },
        ],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
        progress_callback=_record_progress,
    )

    assert payload["enabled"] is True
    assert callback_thread_ids
    assert set(callback_thread_ids) == {caller_thread_id}
    event_types = [str(row.get("event") or "") for row in progress_events]
    assert event_types.count("actor_run_dispatch") == 3
    assert event_types.count("actor_run_started") == 3
    assert event_types.count("actor_run_terminal") == 3


def test_merge_voc_corpus_for_agent2_keeps_prompt_budget_and_preserves_full_artifact_corpus() -> None:
    step4_rows = [
        {
            "voc_id": f"V{idx:03d}",
            "source_type": "existing_corpus",
            "source_url": f"https://step4.example/{idx}",
            "quote": f"Step4 quote {idx} with 3 details and 2 outcomes.",
            "date": "Unknown",
        }
        for idx in range(1, 261)
    ]
    external_rows = [
        {
            "voc_id": f"APIFY_V{idx:03d}",
            "source_type": "FORUM",
            "source_url": f"https://external.example/{idx}",
            "quote": f"External quote {idx} with 4 details and 1 timeline marker.",
            "date": "2026-02-01",
            "engagement": {"likes": idx, "replies": idx // 2},
        }
        for idx in range(1, 261)
    ]

    merged = strategy_v2_activities._merge_voc_corpus_for_agent2(
        step4_rows=step4_rows,
        external_rows=external_rows,
    )
    assert len(merged["prompt_rows"]) == 80
    assert len(merged["artifact_rows"]) == 520
    summary = merged["summary"]
    assert summary["step4_input_count"] == 260
    assert summary["external_input_count"] == 260


def test_build_agent2_evidence_rows_uses_merged_superset_without_silent_drops() -> None:
    row = {
        "voc_id": "V001",
        "source_type": "FORUM",
        "source_url": "https://example.com/thread/1",
        "quote": "I need a clear protocol because random advice keeps failing me.",
        "author": "user1",
        "date": "2026-02-01",
    }
    evidence_rows, diagnostics = strategy_v2_activities._build_agent2_evidence_rows(
        existing_corpus=[row],
        merged_voc_artifact_rows=[row],
        scraped_data_manifest={"raw_scraped_data_files": []},
    )
    assert len(evidence_rows) == 1
    assert diagnostics["existing_rows_in"] == 1
    assert diagnostics["merged_rows_in"] == 1
    assert diagnostics["existing_rows_skipped_due_merged_superset"] == 1
    assert diagnostics["merged_rows_used"] == 1
    assert diagnostics["accepted_rows"] == 1


def test_build_agent2_evidence_rows_errors_on_missing_required_fields() -> None:
    with pytest.raises(StrategyV2SchemaValidationError, match="missing required source_url/verbatim"):
        strategy_v2_activities._build_agent2_evidence_rows(
            existing_corpus=[
                {
                    "voc_id": "V001",
                    "source_type": "FORUM",
                    "source_url": "",
                    "quote": "",
                }
            ],
            merged_voc_artifact_rows=[],
            scraped_data_manifest={"raw_scraped_data_files": []},
        )


def test_build_proof_candidates_from_voc_requires_two_refs() -> None:
    voc_rows = [
        {
            "voc_id": "APIFY_V001",
            "source_url": "https://forum.example.com/thread-1",
            "quote": "We needed clearer timing and fewer random tactics.",
            "compliance_risk": "YELLOW",
            "date": "2026-02-01",
            "engagement": {"likes": 10, "replies": 3},
        }
    ]
    competitor_analysis = {
        "asset_observation_sheets": [
            {"source_ref": "https://competitor.example/asset-a"},
            {"source_ref": "https://competitor.example/asset-b"},
        ]
    }
    candidates = strategy_v2_activities._build_proof_candidates_from_voc(
        voc_rows=voc_rows,
        competitor_analysis=competitor_analysis,
    )
    assert candidates
    assert all(len(row.get("source_refs", [])) >= 2 for row in candidates)


def test_tiktok_payload_builder_uses_profiles_and_posts() -> None:
    payload = ingestion._build_tiktok_actor_input(
        urls=[
            "https://www.tiktok.com/@duolingo",
            "https://www.tiktok.com/@duolingo/video/7300",
            "https://www.tiktok.com/tag/languagelearning",
        ],
        max_items=2,
    )
    assert payload["maxItems"] == 2
    assert payload["profiles"] == ["https://www.tiktok.com/@duolingo"]
    assert payload["postURLs"] == ["https://www.tiktok.com/@duolingo/video/7300"]
    assert payload["hashtags"] == ["languagelearning"]
    assert "startUrls" not in payload


def test_web_payload_builder_includes_page_function() -> None:
    payload = ingestion._build_web_actor_input(
        urls=["https://offer.example.com/landing"],
        max_items=1,
    )
    assert payload["startUrls"] == [{"url": "https://offer.example.com/landing"}]
    assert payload["maxCrawlPages"] == 1
    assert payload["maxResultsPerCrawl"] == 1
    page_fn = payload.get("pageFunction")
    assert isinstance(page_fn, str) and "pageFunction" in page_fn


def test_extract_requested_urls_from_payload_supports_actor_shapes() -> None:
    payload = {
        "directUrls": ["https://www.instagram.com/duolingo/"],
        "profiles": ["https://www.tiktok.com/@duolingo"],
        "postURLs": ["https://www.tiktok.com/@duolingo/video/7300"],
        "startUrls": [{"url": "https://www.youtube.com/@duolingo"}],
    }
    refs = ingestion._extract_requested_urls_from_payload(payload)
    assert "https://www.instagram.com/duolingo" in refs
    assert "https://www.tiktok.com/@duolingo" in refs
    assert "https://www.tiktok.com/@duolingo/video/7300" in refs
    assert "https://www.youtube.com/@duolingo" in refs


def test_canonical_source_refs_adds_social_alias_for_the_prefixed_handles() -> None:
    refs = ingestion._canonical_source_refs(
        [
            "https://www.tiktok.com/@theherbalacademy",
            "https://www.instagram.com/theherbalacademy/",
        ]
    )
    assert "https://www.tiktok.com/@theherbalacademy" in refs
    assert "https://www.tiktok.com/@herbalacademy" in refs
    assert "https://www.instagram.com/theherbalacademy" in refs
    assert "https://www.instagram.com/herbalacademy" in refs


def test_meta_payload_enforces_actor_minimum_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_V2_APIFY_MAX_ITEMS_PER_DATASET", "1")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "curious_coder~facebook-ads-library-scraper",
    )
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    started_payloads: list[dict[str, object]] = []

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self._run_map: dict[str, str] = {}
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            self._counter += 1
            run_id = f"run-{self._counter}"
            self._run_map[run_id] = actor_id
            started_payloads.append({"actor_id": actor_id, "input_payload": input_payload})
            return {"id": run_id}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = dataset_id
            _ = limit
            return []

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        source_refs=["https://www.facebook.com/duolingo"],
        include_ads_context=True,
        include_social_video=False,
        include_external_voc=False,
    )
    assert payload["enabled"] is True
    assert len(started_payloads) == 1
    meta_input = started_payloads[0]["input_payload"]
    assert isinstance(meta_input, dict)
    assert meta_input["count"] == 10
    assert meta_input["limitPerSource"] == 10
    assert meta_input["maxItems"] == 10


def test_run_strategy_v2_apify_ingestion_handles_practicaltools_reddit_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "true")
    monkeypatch.setenv(
        "STRATEGY_V2_APIFY_ALLOWED_ACTOR_IDS",
        "practicaltools/apify-reddit-api,apify/web-scraper",
    )
    monkeypatch.setenv("STRATEGY_V2_APIFY_REDDIT_ACTOR_ID", "practicaltools/apify-reddit-api")
    monkeypatch.setenv("STRATEGY_V2_APIFY_WEB_ACTOR_ID", "apify/web-scraper")
    monkeypatch.setenv("STRATEGY_V2_APIFY_META_ACTOR_ID", "practicaltools/apify-reddit-api")
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")

    class _FakeApifyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self._run_map: dict[str, str] = {}
            self._counter = 0

        def start_actor_run(self, actor_id: str, *, input_payload: dict) -> dict:  # noqa: ANN001
            self._counter += 1
            run_id = f"run-{self._counter}"
            self._run_map[run_id] = actor_id
            return {"id": run_id}

        def poll_run_until_terminal(self, run_id: str, **kwargs) -> dict:  # noqa: ANN003
            _ = kwargs
            return {"status": "SUCCEEDED", "defaultDatasetId": f"dataset-{run_id}"}

        def fetch_dataset_items(self, dataset_id: str, *, limit: int | None = None) -> list[dict]:
            _ = limit
            if "run-1" in dataset_id:
                return [
                    {
                        "post": {
                            "url": "https://www.reddit.com/r/herbalism/comments/1expmex/beware_of_aigenerated_herb_books/",
                            "username": "PrimalBotanical",
                            "title": "Beware of AI-generated herb books!",
                            "body": "There is so much misinformation out there.",
                            "upVotes": 300,
                            "numberOfComments": 25,
                            "createdAt": "2024-08-21T13:26:57.000Z",
                        },
                        "comments": [
                            {
                                "url": "https://www.reddit.com/r/herbalism/comments/1expmex/beware_of_aigenerated_herb_books/lj7kikm/",
                                "username": "Snifhvide",
                                "body": "Report it to Amazon and ask them to remove it.",
                                "upVotes": 82,
                                "numberOfreplies": 0,
                                "createdAt": "2024-08-21T13:52:15.000Z",
                                "replies": [],
                            }
                        ],
                    }
                ]
            return [
                {
                    "url": "https://offer.example.com/page",
                    "text": "Landing page copy body",
                }
            ]

    monkeypatch.setattr("app.strategy_v2.apify_ingestion.ApifyClient", _FakeApifyClient)

    payload = run_strategy_v2_apify_ingestion(
        source_refs=["https://www.reddit.com/r/herbalism/comments/1expmex"],
        include_ads_context=False,
        include_social_video=False,
        include_external_voc=True,
    )
    candidate_assets = payload.get("candidate_assets")
    assert isinstance(candidate_assets, list)
    assert any(
        isinstance(row, dict)
        and "reddit.com/r/herbalism/comments/1expmex" in str(row.get("source_ref") or "")
        for row in candidate_assets
    )
    external_corpus = payload.get("external_voc_corpus")
    assert isinstance(external_corpus, list) and external_corpus
    assert any("Report it to Amazon" in str(row.get("quote") or "") for row in external_corpus)
    proof_candidates = payload.get("proof_asset_candidates")
    assert isinstance(proof_candidates, list) and proof_candidates


def test_extract_metrics_maps_youtube_aliases() -> None:
    metrics = ingestion._extract_metrics(
        {
            "viewCount": 156,
            "numberOfSubscribers": 170000,
            "commentsCount": 7,
            "likes": 11,
            "date": "2025-07-28T15:43:11.000Z",
        }
    )

    assert metrics.views == 156
    assert metrics.followers == 170000
    assert metrics.comments == 7
    assert metrics.likes == 11
    assert metrics.date_posted == "2025-07-28T15:43:11.000Z"


def test_infer_asset_kind_handles_instagram_image_and_reel() -> None:
    image_kind = ingestion._infer_asset_kind(
        platform="INSTAGRAM",
        raw={"type": "Image"},
        source_ref="https://www.instagram.com/p/DVRuOrtkq9F/",
    )
    reel_kind = ingestion._infer_asset_kind(
        platform="INSTAGRAM",
        raw={"type": "Video"},
        source_ref="https://www.instagram.com/reel/ABC123/",
    )

    assert image_kind == "IMAGE"
    assert reel_kind == "VIDEO"


def test_normalize_social_video_observations_allows_missing_followers() -> None:
    rows = ingestion._normalize_social_video_observations(
        [
            {
                "candidate_id": "https://www.youtube.com/watch?v=abc123",
                "platform": "YOUTUBE",
                "asset_kind": "VIDEO",
                "source_ref": "https://www.youtube.com/watch?v=abc123",
                "headline_or_caption": "herbal remedies explainer",
                "competitor_name": "Herbal Channel",
                "metrics": {
                    "views": 12345,
                    "followers": None,
                    "comments": 7,
                    "shares": 0,
                    "likes": 222,
                    "days_since_posted": 14,
                },
            }
        ]
    )

    assert len(rows) == 1
    assert rows[0]["video_id"] == "https://www.youtube.com/watch?v=abc123"
    assert rows[0]["views"] == 12345
    assert rows[0]["followers"] == 0


def test_filter_metric_video_rows_for_scoring_allows_missing_followers() -> None:
    filtered, diagnostics = strategy_v2_activities._filter_metric_video_rows_for_scoring(
        video_rows=[
            {
                "video_id": "https://www.youtube.com/watch?v=abc123",
                "platform": "YOUTUBE",
                "views": 12345,
                "comments": 7,
                "shares": 1,
                "likes": 222,
                "days_since_posted": 14,
                "description": "herbal remedies explainer",
                "author": "Herbal Channel",
                "source_ref": "https://www.youtube.com/watch?v=abc123",
            }
        ],
        source_allowlist={"youtube.com"},
        topic_keywords=["herbal"],
    )

    assert diagnostics["input_rows"] == 1
    assert diagnostics["kept_rows"] == 1
    assert len(filtered) == 1
    assert filtered[0]["followers"] == 0


def test_source_matches_allowlist_accepts_discovery_seed_paths() -> None:
    assert strategy_v2_activities._source_matches_allowlist(
        source_ref="https://www.instagram.com/p/ABC123/",
        allowlist={"instagram.com/explore"},
    )
    assert strategy_v2_activities._source_matches_allowlist(
        source_ref="https://www.youtube.com/watch?v=abc123",
        allowlist={"youtube.com/results"},
    )
    assert strategy_v2_activities._source_matches_allowlist(
        source_ref="https://www.tiktok.com/@brand/video/123",
        allowlist={"tiktok.com/tag/herbalism"},
    )


def test_extract_video_source_allowlist_includes_youtube_shorts_platform() -> None:
    allowlist = strategy_v2_activities._extract_video_source_allowlist(
        {
            "configurations": [
                {
                    "platform": "YOUTUBE_SHORTS",
                    "input": {"startUrls": [{"url": "https://www.youtube.com/results?search_query=herbal+shorts"}]},
                }
            ]
        }
    )
    assert "youtube.com/results" in allowlist
