from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from lib.browser_session_auth import BrowserSessionAuth


class MosApiClient:
    def __init__(self, *, base_url: str, auth: BrowserSessionAuth) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = auth

    def get_json(self, path: str) -> Any:
        raw, _ = self._request(method="GET", path=path, expect_json=True)
        return json.loads(raw.decode("utf-8"))

    def post_json(self, path: str, payload: Any) -> Any:
        raw, _ = self._request(method="POST", path=path, json_payload=payload, expect_json=True)
        return json.loads(raw.decode("utf-8"))

    def get_binary(self, path: str) -> tuple[bytes, str]:
        raw, headers = self._request(method="GET", path=path, expect_json=False)
        return raw, headers.get_content_type()

    def _request(
        self,
        *,
        method: str,
        path: str,
        json_payload: Any = None,
        expect_json: bool,
        retried_for_auth: bool = False,
    ) -> tuple[bytes, Any]:
        url = f"{self.base_url}{path}"
        body: bytes | None = None
        headers = {"Accept": "application/json" if expect_json else "*/*"}
        token = self.auth.get_token()
        headers["Authorization"] = f"Bearer {token}"
        if json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read(), response.headers
        except urllib.error.HTTPError as exc:
            detail_bytes = exc.read()
            detail_text = detail_bytes.decode("utf-8", errors="replace").strip()
            if exc.code in {401, 403} and not retried_for_auth:
                self.auth.force_relogin()
                return self._request(
                    method=method,
                    path=path,
                    json_payload=json_payload,
                    expect_json=expect_json,
                    retried_for_auth=True,
                )
            raise RuntimeError(
                f"{method} {path} failed with status {exc.code}: {detail_text or exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc
