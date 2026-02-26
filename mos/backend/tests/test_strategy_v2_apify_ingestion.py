from __future__ import annotations

import json

import pytest

from app.strategy_v2 import apify_ingestion as ingestion
from app.strategy_v2.apify_ingestion import run_strategy_v2_apify_ingestion
from app.temporal.activities import strategy_v2_activities


def test_run_strategy_v2_apify_ingestion_disabled_uses_seed_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRATEGY_V2_APIFY_ENABLED", "false")
    payload = run_strategy_v2_apify_ingestion(
        source_refs=["https://competitor-a.example/landing"],
        include_ads_context=True,
        include_social_video=True,
        include_external_voc=True,
    )
    assert payload["enabled"] is False
    assert isinstance(payload.get("candidate_assets"), list)
    assert len(payload["candidate_assets"]) >= 1
    ads_context = payload.get("ads_context")
    assert isinstance(ads_context, str) and ads_context.strip()
    parsed = json.loads(ads_context)
    assert parsed["source"] == "seed_urls_only"


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
        "trudax/reddit-scraper,apify/web-scraper",
    )
    monkeypatch.setenv("STRATEGY_V2_APIFY_REDDIT_ACTOR_ID", "trudax/reddit-scraper")
    monkeypatch.setenv("STRATEGY_V2_APIFY_WEB_ACTOR_ID", "apify/web-scraper")
    monkeypatch.setenv("STRATEGY_V2_APIFY_META_ACTOR_ID", "trudax/reddit-scraper")
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
    proof_candidates = payload.get("proof_asset_candidates")
    assert isinstance(proof_candidates, list) and proof_candidates
    assert all(len(row.get("source_refs", [])) >= 2 for row in proof_candidates)


def test_merge_voc_corpus_for_agent2_keeps_prompt_budget() -> None:
    step4_rows = [
        {
            "voc_id": f"V{idx:03d}",
            "source_type": "existing_corpus",
            "source_url": f"https://step4.example/{idx}",
            "quote": f"Step4 quote {idx} with 3 details and 2 outcomes.",
            "date": "Unknown",
        }
        for idx in range(1, 61)
    ]
    external_rows = [
        {
            "voc_id": f"APIFY_V{idx:03d}",
            "source_type": "apify_comment",
            "source_url": f"https://external.example/{idx}",
            "quote": f"External quote {idx} with 4 details and 1 timeline marker.",
            "date": "2026-02-01",
            "engagement": {"likes": idx, "replies": idx // 2},
        }
        for idx in range(1, 61)
    ]

    merged = strategy_v2_activities._merge_voc_corpus_for_agent2(
        step4_rows=step4_rows,
        external_rows=external_rows,
    )
    assert len(merged["prompt_rows"]) == 80
    assert len(merged["artifact_rows"]) <= 400
    summary = merged["summary"]
    assert summary["step4_input_count"] == 60
    assert summary["external_input_count"] == 60


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
