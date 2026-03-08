#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHOPIFY_DIR="$ROOT/shopify-funnel-app"
SHOPIFY_ENV_FILE="$SHOPIFY_DIR/.env"
SHOPIFY_MANIFEST_FILE="$SHOPIFY_DIR/shopify.app.toml"
SHOPIFY_LOCAL_PORT="${SHOPIFY_FUNNEL_PORT:-8011}"

fail() {
  echo "[shopify-ngrok] error: $*" >&2
  exit 1
}

if ! command -v ngrok >/dev/null 2>&1; then
  fail "ngrok is required but not installed."
fi

if [ ! -f "$SHOPIFY_ENV_FILE" ]; then
  fail "Missing $SHOPIFY_ENV_FILE. Set SHOPIFY_APP_BASE_URL to your ngrok HTTPS URL."
fi

if [ ! -f "$SHOPIFY_MANIFEST_FILE" ]; then
  fail "Missing $SHOPIFY_MANIFEST_FILE."
fi

if ! [[ "$SHOPIFY_LOCAL_PORT" =~ ^[0-9]+$ ]] || (( SHOPIFY_LOCAL_PORT < 1 || SHOPIFY_LOCAL_PORT > 65535 )); then
  fail "Invalid SHOPIFY_FUNNEL_PORT '$SHOPIFY_LOCAL_PORT' (expected 1-65535)."
fi

NGROK_DOMAIN="$(
python3.11 - "$SHOPIFY_ENV_FILE" "$SHOPIFY_MANIFEST_FILE" <<'PY'
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import sys
import tomllib

env_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


env = read_env(env_path)
base_url = env.get("SHOPIFY_APP_BASE_URL")
if not base_url:
    raise SystemExit(
        "Missing SHOPIFY_APP_BASE_URL in shopify-funnel-app/.env."
    )

parsed_base = urlparse(base_url)
if parsed_base.scheme != "https":
    raise SystemExit(
        f"SHOPIFY_APP_BASE_URL must use https. Current value: {base_url!r}"
    )
if not parsed_base.hostname:
    raise SystemExit(
        f"SHOPIFY_APP_BASE_URL must include a hostname. Current value: {base_url!r}"
    )
if parsed_base.path not in ("", "/") or parsed_base.params or parsed_base.query or parsed_base.fragment:
    raise SystemExit(
        "SHOPIFY_APP_BASE_URL must be a bare origin (no path/query/fragment). "
        f"Current value: {base_url!r}"
    )

manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
manifest_app_url = str(manifest.get("application_url", "")).rstrip("/")
normalized_env_url = base_url.rstrip("/")
if manifest_app_url != normalized_env_url:
    raise SystemExit(
        "shopify.app.toml application_url must match SHOPIFY_APP_BASE_URL. "
        f"application_url={manifest_app_url!r}, SHOPIFY_APP_BASE_URL={normalized_env_url!r}"
    )

redirect_urls = (manifest.get("auth") or {}).get("redirect_urls") or []
expected_redirect = f"{normalized_env_url}/auth/callback"
if expected_redirect not in redirect_urls:
    raise SystemExit(
        "shopify.app.toml auth.redirect_urls must include "
        f"{expected_redirect!r}. Current redirect_urls={redirect_urls!r}"
    )

print(parsed_base.hostname)
PY
)"

echo "[shopify-ngrok] Starting ngrok tunnel https://${NGROK_DOMAIN} -> http://127.0.0.1:${SHOPIFY_LOCAL_PORT}"
exec ngrok http --domain="$NGROK_DOMAIN" "$SHOPIFY_LOCAL_PORT"
