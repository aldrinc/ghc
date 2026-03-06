#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHOPIFY_DIR="$ROOT/shopify-funnel-app"

fail() {
  echo "[shopify-funnel] error: $*" >&2
  exit 1
}

if ! command -v python3.11 >/dev/null 2>&1; then
  fail "python3.11 is required but not installed."
fi

if [ ! -d "$SHOPIFY_DIR" ]; then
  fail "Shopify app directory not found at $SHOPIFY_DIR"
fi

cd "$SHOPIFY_DIR"

if [ ! -f ".env" ]; then
  fail "Missing $SHOPIFY_DIR/.env. Copy .env.example and set required values."
fi

if [ ! -f "shopify.app.toml" ]; then
  fail "Missing $SHOPIFY_DIR/shopify.app.toml."
fi

if [ ! -d ".venv" ]; then
  echo "[shopify-funnel] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

echo "[shopify-funnel] Installing/updating dependencies from pyproject.toml..."
.venv/bin/pip install -e .

echo "[shopify-funnel] Validating app config and Shopify manifest..."
.venv/bin/python - <<'PY'
from __future__ import annotations

from pathlib import Path
import sys
import tomllib

try:
    from app.config import settings
except Exception as exc:  # pragma: no cover - startup guard
    raise SystemExit(f"Invalid .env configuration: {exc}") from exc

manifest_path = Path("shopify.app.toml")
try:
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
except Exception as exc:  # pragma: no cover - startup guard
    raise SystemExit(f"Unable to parse {manifest_path}: {exc}") from exc

manifest_app_url = str(manifest.get("application_url", "")).rstrip("/")
expected_app_url = settings.app_base_url
if manifest_app_url != expected_app_url:
    raise SystemExit(
        "shopify.app.toml application_url must match SHOPIFY_APP_BASE_URL in .env. "
        f"application_url={manifest_app_url!r}, SHOPIFY_APP_BASE_URL={expected_app_url!r}"
    )

if not expected_app_url.startswith("https://"):
    raise SystemExit(
        "SHOPIFY_APP_BASE_URL must use https for Shopify callbacks/webhooks."
    )

redirect_urls = (manifest.get("auth") or {}).get("redirect_urls") or []
expected_redirect = f"{expected_app_url}/auth/callback"
if expected_redirect not in redirect_urls:
    raise SystemExit(
        "shopify.app.toml auth.redirect_urls must include the OAuth callback URL "
        f"{expected_redirect!r}. Current redirect_urls={redirect_urls!r}"
    )


def scope_set(csv: str) -> set[str]:
    return {item.strip() for item in csv.split(",") if item.strip()}


manifest_scopes_csv = (manifest.get("access_scopes") or {}).get("scopes")
if not isinstance(manifest_scopes_csv, str) or not manifest_scopes_csv.strip():
    raise SystemExit("shopify.app.toml access_scopes.scopes must be a non-empty string.")

manifest_scopes = scope_set(manifest_scopes_csv)
env_scopes = scope_set(settings.admin_scopes_csv)
if manifest_scopes != env_scopes:
    raise SystemExit(
        "Scope mismatch between shopify.app.toml and .env SHOPIFY_APP_SCOPES. "
        f"manifest_scopes={sorted(manifest_scopes)!r}, env_scopes={sorted(env_scopes)!r}"
    )

print("[shopify-funnel] Config validation passed.")
PY

HOST="${SHOPIFY_FUNNEL_HOST:-127.0.0.1}"
PORT="${SHOPIFY_FUNNEL_PORT:-8011}"
FORWARDED_ALLOW_IPS="${SHOPIFY_FUNNEL_FORWARDED_ALLOW_IPS:-127.0.0.1}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  fail "Invalid SHOPIFY_FUNNEL_PORT '$PORT' (expected 1-65535)."
fi

echo "[shopify-funnel] Starting uvicorn on http://${HOST}:${PORT}"
exec .venv/bin/uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --reload \
  --proxy-headers \
  --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
