#!/usr/bin/env python3
"""Pull a full Ember-product asset inventory from moshq.app.

Requires cookies exported from moshq.app (Netscape format). Uses the
__clerk_db_jwt cookie to mint a fresh backend-template JWT via Clerk's
frontend API, then queries the mOS backend.

Usage: ember_asset_inventory.py [cookies.txt] [output.json]
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

COOKIES_DEFAULT = "/Users/auggieclement/Downloads/moshq.app_cookies (7).txt"
OUT_DEFAULT = "/Users/auggieclement/Downloads/mos_strategy/.local/ember-asset-inventory.json"
CLERK_HOST = "https://immune-turtle-79.clerk.accounts.dev"
API_HOST = "https://api.moshq.app"


def parse_cookies(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        name, value = parts[5], parts[6]
        # Prefer the first occurrence (no overwrite)
        out.setdefault(name, value)
    return out


def jwt_payload(jwt: str) -> dict:
    payload = jwt.split(".")[1]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(payload + padding))


def mint_backend_jwt(session_id: str, dev_session_token: str) -> str:
    # Use curl because Clerk's Cloudflare-shielded endpoint 403s urllib's UA.
    url = (
        f"{CLERK_HOST}/v1/client/sessions/{session_id}/tokens/backend"
        f"?_clerk_js_version=5.50.0&__dev_session={dev_session_token}"
    )
    result = subprocess.run(
        [
            "curl",
            "-fsS",
            "-X",
            "POST",
            "-H",
            "Origin: https://moshq.app",
            "-H",
            "Referer: https://moshq.app/",
            "-H",
            "Content-Type: application/x-www-form-urlencoded",
            url,
        ],
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)["jwt"]


def api_get(path: str, jwt: str, **query) -> object:
    qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    url = f"{API_HOST}{path}"
    if qs:
        url += "?" + qs
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {jwt}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    cookies_path = Path(sys.argv[1] if len(sys.argv) > 1 else COOKIES_DEFAULT)
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else OUT_DEFAULT)

    cookies = parse_cookies(cookies_path)
    db_jwt = cookies.get("__clerk_db_jwt") or cookies.get("__clerk_db_jwt_aKtkncZL")
    sess_jwt = cookies.get("__session") or cookies.get("__session_aKtkncZL")
    if not db_jwt or not sess_jwt:
        print(f"Missing __clerk_db_jwt or __session in {cookies_path}", file=sys.stderr)
        return 2

    session_id = jwt_payload(sess_jwt)["sid"]
    print(f"clerk session id: {session_id}")
    jwt = mint_backend_jwt(session_id, db_jwt)
    print(f"minted backend jwt (len {len(jwt)})")

    # Find Ember client
    clients = api_get("/clients", jwt)
    assert isinstance(clients, list)
    ember = next(
        (
            c
            for c in clients
            if isinstance(c, dict)
            and (
                "ember" in (c.get("name") or "").lower()
                or (c.get("id") or "").startswith("070d6cf7")
            )
        ),
        None,
    )
    if not ember:
        print("Ember client not found. Candidates:", file=sys.stderr)
        for c in clients:
            if isinstance(c, dict):
                print(
                    f"  - {c.get('name')!r} id={c.get('id')}",
                    file=sys.stderr,
                )
        return 3
    print(f"Ember client: {ember['name']} ({ember['id']})")

    # Products
    products = api_get("/products", jwt, clientId=ember["id"]) or []
    print(f"products: {len(products)}")
    for p in products:
        print(f"  - {p.get('name')!r} id={p.get('id')}")

    # Assets — fetch per-product + top-level client-only, then union by id
    by_id: dict[str, dict] = {}
    top = api_get("/assets", jwt, clientId=ember["id"])
    if isinstance(top, list):
        for a in top:
            if isinstance(a, dict) and a.get("id"):
                by_id[a["id"]] = a
    print(f"client-scope assets: {len(by_id)}")

    for p in products:
        pid = p.get("id")
        if not pid:
            continue
        rows = api_get("/assets", jwt, clientId=ember["id"], productId=pid)
        if isinstance(rows, list):
            added = 0
            for a in rows:
                if isinstance(a, dict) and a.get("id") and a["id"] not in by_id:
                    by_id[a["id"]] = a
                    added += 1
            print(f"  product {pid[:8]}: +{added} new (total in response {len(rows)})")

    # Try per-funnel too (we know the Ember funnel id from the deployed meta)
    for funnel_id in ("18ac0fe1-1e27-4579-ad94-9a1e6c9530fe",):
        try:
            rows = api_get(
                "/assets", jwt, clientId=ember["id"], funnelId=funnel_id
            )
        except Exception as e:
            print(f"  funnel {funnel_id[:8]} lookup failed: {e}")
            continue
        if isinstance(rows, list):
            added = 0
            for a in rows:
                if isinstance(a, dict) and a.get("id") and a["id"] not in by_id:
                    by_id[a["id"]] = a
                    added += 1
            print(f"  funnel {funnel_id[:8]}: +{added} new (total in response {len(rows)})")

    assets = list(by_id.values())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"client": ember, "products": products, "assets": assets},
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out_path} — {len(assets)} unique assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
