#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_ROUTES = ["/", "/sign-in", "/workspaces/overview"]
REQUIRED_MARKERS = ('<div id="root"></div>', "<title>mOS Frontend</title>")
FORBIDDEN_MARKERS = ("<title>Error response</title>", "Message: File not found.")


def _normalize_route(route: str) -> str:
    stripped = route.strip()
    if not stripped:
        raise ValueError("Routes must be non-empty.")
    return stripped if stripped.startswith("/") else f"/{stripped}"


def _fetch(url: str, timeout_seconds: float) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": "mos-spa-route-smoke/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
        return response.getcode(), response.headers.get_content_type(), body


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that SPA deep links return the frontend app shell.")
    parser.add_argument("--base-url", required=True, help="Public origin to validate, for example https://moshq.app")
    parser.add_argument(
        "--route",
        action="append",
        dest="routes",
        default=[],
        help="Route to check. Repeat to validate multiple routes. Defaults to core SPA routes.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=20.0,
        help="Request timeout in seconds. Defaults to 20.",
    )
    args = parser.parse_args()

    base_url = str(args.base_url or "").strip()
    if not base_url:
        print("Base URL is required.", file=sys.stderr)
        return 1

    routes = args.routes or list(DEFAULT_ROUTES)
    failures: list[str] = []

    for raw_route in routes:
        try:
            route = _normalize_route(raw_route)
        except ValueError as exc:
            failures.append(str(exc))
            continue

        url = urllib.parse.urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))
        try:
            status, content_type, body = _fetch(url, args.timeout_seconds)
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            failures.append(
                f"{route}: expected HTTP 200 but got {exc.code}. "
                f"Body preview: {response_body[:200].strip()!r}"
            )
            continue
        except urllib.error.URLError as exc:
            failures.append(f"{route}: request failed: {exc.reason}")
            continue

        if status != 200:
            failures.append(f"{route}: expected HTTP 200 but got {status}.")
            continue
        if content_type != "text/html":
            failures.append(f"{route}: expected text/html but got {content_type}.")
            continue

        missing_markers = [marker for marker in REQUIRED_MARKERS if marker not in body]
        present_forbidden = [marker for marker in FORBIDDEN_MARKERS if marker in body]
        if missing_markers or present_forbidden:
            problems: list[str] = []
            if missing_markers:
                problems.append(f"missing app-shell markers {missing_markers!r}")
            if present_forbidden:
                problems.append(f"found error markers {present_forbidden!r}")
            failures.append(f"{route}: {'; '.join(problems)}.")
            continue

        print(f"OK {route} -> 200 text/html app shell")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
