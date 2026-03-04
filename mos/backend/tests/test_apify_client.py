from __future__ import annotations

import httpx
import pytest

from app.ads.apify_client import ApifyClient


def _response(method: str, url: str, status_code: int, payload: object) -> httpx.Response:
    request = httpx.Request(method, url)
    return httpx.Response(status_code=status_code, request=request, json=payload)


def test_fetch_run_retries_transient_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    monkeypatch.setenv("APIFY_HTTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("APIFY_HTTP_RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("APIFY_HTTP_RETRY_MAX_SECONDS", "4")

    responses = [
        _response("GET", "https://api.apify.com/v2/actor-runs/run-1", 502, {"error": "bad gateway"}),
        _response(
            "GET",
            "https://api.apify.com/v2/actor-runs/run-1",
            200,
            {"data": {"status": "RUNNING", "defaultDatasetId": "dataset-1"}},
        ),
    ]
    call_count = {"value": 0}
    sleep_calls: list[float] = []

    def _fake_request(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = kwargs
        idx = call_count["value"]
        call_count["value"] += 1
        return responses[idx]

    monkeypatch.setattr("app.ads.apify_client.httpx.request", _fake_request)
    monkeypatch.setattr("app.ads.apify_client.time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = ApifyClient()
    run = client.fetch_run("run-1")

    assert run.get("status") == "RUNNING"
    assert call_count["value"] == 2
    assert sleep_calls == [1.0]


def test_fetch_run_fails_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    monkeypatch.setenv("APIFY_HTTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("APIFY_HTTP_RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("APIFY_HTTP_RETRY_MAX_SECONDS", "4")

    response = _response("GET", "https://api.apify.com/v2/actor-runs/run-2", 502, {"error": "bad gateway"})
    call_count = {"value": 0}
    sleep_calls: list[float] = []

    def _fake_request(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = args, kwargs
        call_count["value"] += 1
        return response

    monkeypatch.setattr("app.ads.apify_client.httpx.request", _fake_request)
    monkeypatch.setattr("app.ads.apify_client.time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = ApifyClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_run("run-2")

    assert call_count["value"] == 3
    assert sleep_calls == [1.0, 2.0]


def test_fetch_dataset_items_retries_transient_502(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APIFY_API_TOKEN", "test-token")
    monkeypatch.setenv("APIFY_HTTP_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("APIFY_HTTP_RETRY_BASE_SECONDS", "1")
    monkeypatch.setenv("APIFY_HTTP_RETRY_MAX_SECONDS", "4")

    responses = [
        _response("GET", "https://api.apify.com/v2/datasets/dataset-1/items", 502, {"error": "bad gateway"}),
        _response(
            "GET",
            "https://api.apify.com/v2/datasets/dataset-1/items",
            200,
            [{"url": "https://example.com/a", "text": "sample"}],
        ),
    ]
    call_count = {"value": 0}
    sleep_calls: list[float] = []

    def _fake_request(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = kwargs
        idx = call_count["value"]
        call_count["value"] += 1
        return responses[idx]

    monkeypatch.setattr("app.ads.apify_client.httpx.request", _fake_request)
    monkeypatch.setattr("app.ads.apify_client.time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = ApifyClient()
    rows = client.fetch_dataset_items("dataset-1", limit=25)

    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.com/a"
    assert call_count["value"] == 2
    assert sleep_calls == [1.0]
