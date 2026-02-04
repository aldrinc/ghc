from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import httpx


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
        if not self.token:
            raise RuntimeError("APIFY_API_TOKEN is required for Apify client")

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    def start_actor_run(self, actor_id: str, *, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/acts/{actor_id}/runs"
        params = {"token": self.token}
        response = httpx.post(url, params=params, json=input_payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json().get("data", {})

    def fetch_run(self, run_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/actor-runs/{run_id}"
        params = {"token": self.token}
        response = httpx.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json().get("data", {})

    def poll_run_until_terminal(
        self, run_id: str, *, poll_interval_seconds: int = 5, max_wait_seconds: int = 300
    ) -> Dict[str, Any]:
        start = time.time()
        while True:
            data = self.fetch_run(run_id)
            status = (data.get("status") or "").upper()
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
        response = httpx.get(url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
