#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/mos/frontend"
FRONTEND_PORT="${FRONTEND_PORT:-5275}"

fail() {
  echo "[frontend] error: $*" >&2
  exit 1
}

listener_pid() {
  local pids
  pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return 0
  fi
  printf '%s\n' "$pids" | sed -n '1p'
}

matching_frontend_pid() {
  local matches
  matches="$(pgrep -f "$FRONTEND_DIR/node_modules/.bin/vite .*--port $1( |$)" || true)"
  if [ -z "$matches" ]; then
    return 0
  fi
  printf '%s\n' "$matches" | sed -n '1p'
}

cd "$FRONTEND_DIR"

if ! [[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || (( FRONTEND_PORT < 1 || FRONTEND_PORT > 65535 )); then
  fail "Invalid FRONTEND_PORT '$FRONTEND_PORT' (expected 1-65535)."
fi

existing_frontend_pid="$(matching_frontend_pid "$FRONTEND_PORT")"
if [ -n "$existing_frontend_pid" ]; then
  echo "[frontend] Vite already running on http://localhost:${FRONTEND_PORT} (pid ${existing_frontend_pid})."
  exit 0
fi

existing_pid="$(listener_pid "$FRONTEND_PORT")"
if [ -n "$existing_pid" ]; then
  existing_cmd="$(ps -p "$existing_pid" -o command= | sed 's/^ *//')"
  fail "Port ${FRONTEND_PORT} is in use by pid ${existing_pid}: ${existing_cmd}"
fi

if [ ! -x "node_modules/.bin/vite" ]; then
  echo "[frontend] Frontend dependencies are missing (vite binary not found). Installing npm dependencies with dev packages..."
  npm install --include=dev
fi

if [ ! -x "node_modules/.bin/vite" ]; then
  echo "[frontend] Error: vite is still unavailable after npm install. Check npm output and local Node/npm configuration." >&2
  exit 1
fi

echo "[frontend] Starting Vite dev server on http://localhost:${FRONTEND_PORT} (forced dep re-optimize)"
exec npm run dev -- --host --port "$FRONTEND_PORT" --force
