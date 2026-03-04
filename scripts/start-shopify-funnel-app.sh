#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHOPIFY_APP_DIR="$ROOT/shopify-funnel-app"
SHOPIFY_FUNNEL_PORT="${SHOPIFY_FUNNEL_PORT:-8011}"

_listener_pid() {
  local pids
  pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return 0
  fi
  printf '%s\n' "$pids" | sed -n '1p'
}

_matching_shopify_pid() {
  local matches
  matches="$(pgrep -f "uvicorn app.main:app .*--port $1( |$)" || true)"
  if [ -z "$matches" ]; then
    return 0
  fi
  printf '%s\n' "$matches" | sed -n '1p'
}

cd "$SHOPIFY_APP_DIR"

existing_shopify_pid="$(_matching_shopify_pid "$SHOPIFY_FUNNEL_PORT")"
if [ -n "$existing_shopify_pid" ]; then
  echo "[shopify-funnel-app] Uvicorn already running on http://localhost:${SHOPIFY_FUNNEL_PORT} (pid ${existing_shopify_pid})."
  exit 0
fi

existing_pid="$(_listener_pid "$SHOPIFY_FUNNEL_PORT")"
if [ -n "$existing_pid" ]; then
  existing_cmd="$(ps -p "$existing_pid" -o command= | sed 's/^ *//')"
  echo "[shopify-funnel-app] Port ${SHOPIFY_FUNNEL_PORT} is in use by pid ${existing_pid}: ${existing_cmd}" >&2
  echo "[shopify-funnel-app] Stop that process or set SHOPIFY_FUNNEL_PORT to a free port." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[shopify-funnel-app] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

echo "[shopify-funnel-app] Installing/updating dependencies from pyproject.toml..."
.venv/bin/pip install -e .

echo "[shopify-funnel-app] Starting uvicorn on http://localhost:${SHOPIFY_FUNNEL_PORT}"
exec .venv/bin/uvicorn app.main:app --reload --port "$SHOPIFY_FUNNEL_PORT"
