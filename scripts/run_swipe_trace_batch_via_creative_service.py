#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BACKEND_VENV_PYTHON = ROOT / "mos" / "backend" / ".venv" / "bin" / "python"
RUN_WITH_ENV = ROOT / "scripts" / "run_with_backend_env.py"
RUN_BATCH = ROOT / "scripts" / "run_swipe_trace_batch.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run swipe trace batch through creative_service using cookie-backed Clerk auth."
    )
    parser.add_argument("--cookie-export", required=True)
    parser.add_argument("--ui-url", required=True)
    parser.add_argument("--creative-base-url", required=True)
    parser.add_argument("--template-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--org-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--product-id", required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--asset-brief-id", required=True)
    parser.add_argument("--requirement-index", type=int, default=0)
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--render-model-id", default=None)
    return parser.parse_args()


def _jwt_expiry_epoch(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + ("=" * (-len(parts[1]) % 4))
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        exp_raw = __import__("json").loads(decoded).get("exp")
        return int(exp_raw) if exp_raw is not None else None
    except Exception:
        return None


class CookieBackedClerkTokenProvider:
    def __init__(self, *, cookie_export: Path, ui_url: str) -> None:
        self.cookie_export = cookie_export
        self.ui_url = ui_url.rstrip("/")
        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._cached_token: str | None = None
        self._cached_expiry_epoch: int | None = None

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def get_token(self) -> str:
        now = int(time.time())
        if (
            self._cached_token
            and self._cached_expiry_epoch is not None
            and now < (self._cached_expiry_epoch - 10)
        ):
            return self._cached_token

        page = self._ensure_page()
        page.goto(self.ui_url, wait_until="networkidle", timeout=60000)
        token = page.evaluate(
            """
            async () => {
              const clerk = window.Clerk || window.__clerk;
              if (!clerk || !clerk.session || !clerk.session.getToken) {
                return null;
              }
              try {
                return await clerk.session.getToken();
              } catch (error) {
                return null;
              }
            }
            """
        )
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError(
                "Failed to derive Clerk bearer token from cookie-backed browser session. "
                "Ensure the cookie export contains a live authenticated localhost session."
            )
        self._cached_token = token.strip()
        self._cached_expiry_epoch = _jwt_expiry_epoch(self._cached_token)
        return self._cached_token

    def _ensure_page(self) -> Page:
        if self._page is not None:
            return self._page

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        context = self._browser.new_context()
        context.add_cookies(self._load_browser_cookies())
        self._context = context
        self._page = context.new_page()
        return self._page

    def _load_browser_cookies(self) -> list[dict[str, Any]]:
        ui_host = urllib.parse.urlparse(self.ui_url).hostname or ""
        if not ui_host:
            raise RuntimeError(f"Unable to resolve hostname from ui_url={self.ui_url!r}")

        cookies: dict[tuple[str, str, str], dict[str, Any]] = {}
        for line in self.cookie_export.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, _, path, secure_flag, expiry_raw, name, value = parts
            normalized_domain = domain.lstrip(".").lower()
            if not (
                normalized_domain == ui_host.lower()
                or ui_host.lower().endswith("." + normalized_domain)
            ):
                continue
            if not (
                name.startswith("__session")
                or name.startswith("__client")
                or name.startswith("__clerk")
                or name.startswith("clerk_")
            ):
                continue
            cookie: dict[str, Any] = {
                "name": name,
                "value": value,
                "domain": normalized_domain,
                "path": path or "/",
                "httpOnly": False,
                "secure": secure_flag.upper() == "TRUE",
                "sameSite": "Lax",
            }
            try:
                expiry = int(expiry_raw)
            except ValueError:
                expiry = 0
            if expiry > 0:
                cookie["expires"] = expiry
            cookies[(normalized_domain, cookie["path"], name)] = cookie

        if not cookies:
            raise RuntimeError(
                f"No usable Clerk cookies were found for ui host {ui_host!r} in {self.cookie_export}"
            )
        return list(cookies.values())


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    proxy_base_url: str = ""
    token_provider: CookieBackedClerkTokenProvider | None = None

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def do_PUT(self) -> None:  # noqa: N802
        self._forward()

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward()

    def _forward(self) -> None:
        if self.token_provider is None:
            self.send_error(500, "Proxy token provider is not configured.")
            return

        upstream_url = self.proxy_base_url.rstrip("/") + self.path
        content_length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else None
        content_type = self.headers.get("Content-Type") or ""
        if (
            self.command == "POST"
            and self.path == "/v1/marketing/image-ads"
            and "application/json" in content_type.lower()
            and body
        ):
            body = self._rewrite_image_ads_request_body(body)

        headers = {}
        for key, value in self.headers.items():
            lowered = key.lower()
            if lowered in {"host", "authorization", "content-length", "connection", "accept-encoding"}:
                continue
            headers[key] = value
        headers["Authorization"] = f"Bearer {self.token_provider.get_token()}"

        request = urllib.request.Request(
            upstream_url,
            data=body,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                response_body = response.read()
                response_headers = response.headers.items()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
            response_headers = exc.headers.items()
        except Exception as exc:  # noqa: BLE001
            payload = str(exc).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(status)
        for key, value in response_headers:
            lowered = key.lower()
            if lowered in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    @staticmethod
    def _rewrite_image_ads_request_body(body: bytes) -> bytes:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return body
        if not isinstance(payload, dict):
            return body
        model_id = payload.get("model_id")
        return body


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _run_batch(*, args: argparse.Namespace, proxy_base_url: str) -> int:
    env = os.environ.copy()
    env["CREATIVE_SERVICE_BASE_URL"] = proxy_base_url
    env["CREATIVE_SERVICE_BEARER_TOKEN"] = "cookie-proxy-session"

    command = [
        str(BACKEND_VENV_PYTHON),
        str(RUN_WITH_ENV),
        str(BACKEND_VENV_PYTHON),
        str(RUN_BATCH),
        "--template-dir",
        args.template_dir,
        "--output-root",
        args.output_root,
        "--org-id",
        args.org_id,
        "--client-id",
        args.client_id,
        "--product-id",
        args.product_id,
        "--campaign-id",
        args.campaign_id,
        "--asset-brief-id",
        args.asset_brief_id,
        "--requirement-index",
        str(args.requirement_index),
        "--aspect-ratio",
        args.aspect_ratio,
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if args.render_model_id:
        command.extend(["--render-model-id", args.render_model_id])
    if args.clean:
        command.append("--clean")
    if args.model:
        command.extend(["--model", args.model])

    completed = subprocess.run(command, cwd=str(ROOT), env=env)
    return completed.returncode


def main() -> int:
    args = _parse_args()
    provider = CookieBackedClerkTokenProvider(
        cookie_export=Path(args.cookie_export).expanduser().resolve(),
        ui_url=args.ui_url,
    )

    handler = functools.partial(_ProxyHandler)
    server = _ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.RequestHandlerClass.proxy_base_url = args.creative_base_url.rstrip("/")
    server.RequestHandlerClass.token_provider = provider

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proxy_host, proxy_port = server.server_address
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    print(f"[creative-proxy] base={args.creative_base_url} proxy={proxy_url}", file=sys.stderr, flush=True)

    try:
        return _run_batch(args=args, proxy_base_url=proxy_url)
    finally:
        server.shutdown()
        server.server_close()
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
