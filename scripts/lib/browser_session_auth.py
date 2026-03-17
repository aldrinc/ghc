from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path
from typing import Any


class BrowserSessionAuth:
    def __init__(
        self,
        *,
        ui_url: str,
        jwt_template: str,
        profile_dir: Path,
        login_timeout_seconds: int = 300,
    ) -> None:
        self.ui_url = ui_url.rstrip("/")
        self.jwt_template = jwt_template
        self.profile_dir = profile_dir.expanduser().resolve()
        self.login_timeout_seconds = login_timeout_seconds
        self._playwright = None
        self._context = None
        self._page = None
        self._cached_token: str | None = None
        self._cached_expiry_epoch: int | None = None

    def __enter__(self) -> "BrowserSessionAuth":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
            self._page = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def get_token(self) -> str:
        now = int(time.time())
        if (
            self._cached_token
            and self._cached_expiry_epoch is not None
            and now < (self._cached_expiry_epoch - 30)
        ):
            return self._cached_token
        return self._acquire_token(force_relogin=False)

    def force_relogin(self) -> str:
        self.invalidate_token()
        return self._acquire_token(force_relogin=True)

    def invalidate_token(self) -> None:
        self._cached_token = None
        self._cached_expiry_epoch = None

    def token_claims(self) -> dict[str, Any]:
        token = self.get_token()
        payload = _jwt_payload(token)
        if not isinstance(payload, dict):
            raise RuntimeError("Failed to decode Clerk session token payload.")
        return payload

    def _acquire_token(self, *, force_relogin: bool) -> str:
        page = self._ensure_page()
        try:
            page.goto(self.ui_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to open MOS UI in Chrome: {exc}") from exc

        if force_relogin:
            print(
                "Session expired. Complete the login flow in the opened Chrome window.",
                file=sys.stderr,
            )
        else:
            print(
                "Complete the login flow in the opened Chrome window if prompted.",
                file=sys.stderr,
            )

        deadline = time.monotonic() + self.login_timeout_seconds
        last_error: str | None = None
        while time.monotonic() < deadline:
            try:
                token = self._fetch_token_from_page(page)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                token = None
            if isinstance(token, str) and token.strip():
                normalized = token.strip()
                claims = _jwt_payload(normalized)
                org_id = None
                if isinstance(claims, dict):
                    org_id = claims.get("org_id") or claims.get("organization_id")
                if not isinstance(org_id, str) or not org_id.strip():
                    raise RuntimeError(
                        "Clerk session token is missing org_id. Select the correct organization in the MOS UI and try again."
                    )
                self._cached_token = normalized
                self._cached_expiry_epoch = _jwt_expiry_epoch(normalized)
                return normalized
            time.sleep(2)

        detail = f" Last browser error: {last_error}" if last_error else ""
        raise RuntimeError(
            f"Timed out after {self.login_timeout_seconds} seconds waiting for a valid Clerk session token.{detail}"
        )

    def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is required for Chrome-backed login. Install the backend Python dependencies first."
            ) from exc

        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._context is None:
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1440, "height": 960},
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Failed to launch Google Chrome via Playwright. Ensure Chrome is installed and Playwright browsers are available."
                ) from exc
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()
        return self._page

    def _fetch_token_from_page(self, page) -> str | None:
        script = """
        async (templateName) => {
          const clerk = window.Clerk || window.__clerk;
          if (!clerk || !clerk.session || !clerk.session.getToken) {
            return null;
          }
          try {
            return await clerk.session.getToken({ template: templateName });
          } catch (error) {
            return null;
          }
        }
        """
        token = page.evaluate(script, self.jwt_template)
        if token is None:
            return None
        if not isinstance(token, str):
            raise RuntimeError("Clerk session returned a non-string token.")
        return token


def _jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _jwt_expiry_epoch(token: str) -> int | None:
    payload = _jwt_payload(token)
    if not isinstance(payload, dict):
        return None
    exp_raw = payload.get("exp")
    try:
        return int(exp_raw) if exp_raw is not None else None
    except (TypeError, ValueError):
        return None
