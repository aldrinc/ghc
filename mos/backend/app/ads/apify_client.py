from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

import httpx


_TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def _parse_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got {value}.")
    return value


def _parse_positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got {raw!r}.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got {value}.")
    return value


class ApifyClient:
    """Minimal Apify REST client for actor runs and dataset fetches."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        base_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.token = token or os.getenv("APIFY_API_TOKEN") or ""
        self.base_url = base_url or os.getenv("APIFY_API_URL", "https://api.apify.com/v2")
        self.timeout_seconds = timeout_seconds
        self.http_max_attempts = _parse_positive_int_env("APIFY_HTTP_MAX_ATTEMPTS", 5)
        self.http_retry_base_seconds = _parse_positive_float_env("APIFY_HTTP_RETRY_BASE_SECONDS", 1.0)
        self.http_retry_max_seconds = _parse_positive_float_env("APIFY_HTTP_RETRY_MAX_SECONDS", 8.0)
        if not self.token:
            raise RuntimeError("APIFY_API_TOKEN is required for Apify client")

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    def _sleep_for_retry(self, attempt: int) -> None:
        retry_seconds = min(self.http_retry_base_seconds * (2 ** max(attempt - 1, 0)), self.http_retry_max_seconds)
        time.sleep(retry_seconds)

    def _request_data(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        for attempt in range(1, self.http_max_attempts + 1):
            try:
                response = httpx.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code in _TRANSIENT_HTTP_STATUS_CODES and attempt < self.http_max_attempts:
                    self._sleep_for_retry(attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in _TRANSIENT_HTTP_STATUS_CODES and attempt < self.http_max_attempts:
                    self._sleep_for_retry(attempt)
                    continue
                raise
            except httpx.RequestError:
                if attempt < self.http_max_attempts:
                    self._sleep_for_retry(attempt)
                    continue
                raise
        raise RuntimeError("Apify request retry loop exited unexpectedly.")

    def start_actor_run(self, actor_id: str, *, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        encoded_actor_id = quote(actor_id, safe="~")
        url = f"{self.base_url}/acts/{encoded_actor_id}/runs"
        params = {"token": self.token}
        body = self._request_data("POST", url, params=params, json_payload=input_payload)
        if not isinstance(body, dict):
            return {}
        return body.get("data", {}) if isinstance(body.get("data"), dict) else {}

    def fetch_run(self, run_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/actor-runs/{run_id}"
        params = {"token": self.token}
        body = self._request_data("GET", url, params=params)
        if not isinstance(body, dict):
            return {}
        return body.get("data", {}) if isinstance(body.get("data"), dict) else {}

    def poll_run_until_terminal(
        self,
        run_id: str,
        *,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 300,
        on_poll: Callable[[Dict[str, Any]], None] | None = None,
    ) -> Dict[str, Any]:
        start = time.time()
        while True:
            data = self.fetch_run(run_id)
            status = (data.get("status") or "").upper()
            if on_poll is not None:
                on_poll(
                    {
                        "run_id": run_id,
                        "status": status or "UNKNOWN",
                        "elapsed_seconds": max(time.time() - start, 0.0),
                    }
                )
            if status in {"SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"}:
                return data
            if time.time() - start > max_wait_seconds:
                raise TimeoutError(f"Apify run {run_id} did not complete in time")
            time.sleep(poll_interval_seconds)

    def fetch_dataset_items(self, dataset_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/datasets/{dataset_id}/items"
        params: Dict[str, Any] = {"token": self.token, "format": "json"}
        if limit:
            params["limit"] = limit
        data = self._request_data("GET", url, params=params)
        return data if isinstance(data, list) else []
