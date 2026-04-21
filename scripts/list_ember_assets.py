#!/usr/bin/env python3
"""List all mOS assets for the Ember product/client.

Uses the existing BrowserSessionAuth + MosApiClient libs (same auth flow as
testimonial_cli.py). If the cached chrome-profile has a valid Clerk session,
runs headless; otherwise opens a browser for the user to sign in once.

Output: pretty-printed markdown table + raw JSON dump alongside.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.browser_session_auth import BrowserSessionAuth
from lib.mos_api_client import MosApiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="List Ember assets on moshq.app")
    parser.add_argument("--api-base-url", default="https://moshq.app/api")
    parser.add_argument("--ui-url", default="https://moshq.app")
    parser.add_argument("--jwt-template", default="backend")
    parser.add_argument(
        "--profile-dir",
        default=str(Path.home() / ".testimonial-cli" / "chrome-profile"),
    )
    parser.add_argument("--client-id", help="Full clientId UUID for Ember (optional)")
    parser.add_argument("--product-id", help="Full productId UUID (optional)")
    parser.add_argument("--funnel-id", default=None, help="Optional funnelId filter")
    parser.add_argument(
        "--asset-kind",
        default=None,
        help='Optional assetKind filter (e.g. "image")',
    )
    parser.add_argument(
        "--output",
        default=str(SCRIPT_DIR.parent / ".local" / "ember-assets.json"),
    )
    args = parser.parse_args()

    with BrowserSessionAuth(
        ui_url=args.ui_url,
        jwt_template=args.jwt_template,
        profile_dir=Path(args.profile_dir),
    ) as auth:
        client = MosApiClient(base_url=args.api_base_url, auth=auth)

        # Step 1: discover clients so we can find Ember's full UUID
        clients = client.get_json("/clients") if not args.client_id else None
        ember_client = None
        if clients is not None:
            if not isinstance(clients, list):
                print("WARN: /clients returned non-list", file=sys.stderr)
            for c in clients or []:
                if not isinstance(c, dict):
                    continue
                name = (c.get("name") or c.get("slug") or "").lower()
                cid = c.get("id") or ""
                if "ember" in name or cid.startswith("070d6cf7"):
                    ember_client = c
                    break
            if ember_client is None:
                print("Could not locate Ember client. Candidates:", file=sys.stderr)
                for c in clients or []:
                    if isinstance(c, dict):
                        print(
                            f"  - id={c.get('id')} name={c.get('name')!r}",
                            file=sys.stderr,
                        )
                return 2
            print(f"Using client: {ember_client.get('name')} ({ember_client.get('id')})")

        client_id = args.client_id or (ember_client.get("id") if ember_client else None)
        if not client_id:
            print("ERROR: no clientId available", file=sys.stderr)
            return 2

        # Step 2: discover products for this client
        products = []
        if not args.product_id:
            try:
                products = client.get_json(f"/products?clientId={client_id}") or []
            except Exception as e:
                print(f"WARN: /products fetch failed: {e}", file=sys.stderr)
        print(f"Found {len(products)} product(s) for client {client_id}")
        for p in products:
            if isinstance(p, dict):
                print(f"  - product id={p.get('id')} name={p.get('name')!r}")

        # Step 3: list ALL assets for this client, no filter on kind
        query_params: dict[str, str] = {"clientId": client_id}
        if args.product_id:
            query_params["productId"] = args.product_id
        if args.funnel_id:
            query_params["funnelId"] = args.funnel_id
        if args.asset_kind:
            query_params["assetKind"] = args.asset_kind

        query = urlencode(query_params)
        print(f"\nQuerying /assets?{query}")
        assets = client.get_json(f"/assets?{query}")
        if not isinstance(assets, list):
            print(f"ERROR: /assets returned non-list: {type(assets)}", file=sys.stderr)
            return 2

        print(f"Got {len(assets)} asset(s)")

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "client": ember_client,
                    "products": products,
                    "assets": assets,
                },
                indent=2,
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Wrote raw JSON to {output_path}")

        # Print a compact markdown summary for images only
        print("\n## Image assets summary\n")
        print(
            "| # | id | kind | status | tags | filename | public_id |\n"
            "|---|---|---|---|---|---|---|"
        )
        for i, a in enumerate(assets, 1):
            if not isinstance(a, dict):
                continue
            kind = a.get("assetKind") or a.get("asset_kind") or ""
            mime = a.get("mimeType") or a.get("mime_type") or ""
            if "image" not in str(kind).lower() and "image" not in str(mime).lower():
                continue
            asset_id = a.get("id") or ""
            status = a.get("status") or ""
            tags = ",".join(a.get("tags") or []) or ""
            filename = a.get("filename") or a.get("name") or ""
            public_id = a.get("publicId") or a.get("public_id") or ""
            print(
                f"| {i} | `{asset_id[:8]}` | {kind} | {status} | {tags} | "
                f"{filename} | `{public_id}` |"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
