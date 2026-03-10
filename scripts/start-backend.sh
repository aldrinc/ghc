#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
BACKEND_PORT="${BACKEND_PORT:-8008}"

fail() {
  echo "[backend] error: $*" >&2
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

matching_backend_pid() {
  local matches
  matches="$(pgrep -f "$BACKEND_DIR/.venv/bin/uvicorn app.main:app .*--port $1( |$)" || true)"
  if [ -z "$matches" ]; then
    return 0
  fi
  printf '%s\n' "$matches" | sed -n '1p'
}

cd "$BACKEND_DIR"

if [ ! -d ".venv" ] && ! command -v python3.11 >/dev/null 2>&1; then
  fail "python3.11 is required but not installed."
fi

if ! [[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] || (( BACKEND_PORT < 1 || BACKEND_PORT > 65535 )); then
  fail "Invalid BACKEND_PORT '$BACKEND_PORT' (expected 1-65535)."
fi

existing_backend_pid="$(matching_backend_pid "$BACKEND_PORT")"
if [ -n "$existing_backend_pid" ]; then
  echo "[backend] Uvicorn already running on http://localhost:${BACKEND_PORT} (pid ${existing_backend_pid})."
  exit 0
fi

existing_pid="$(listener_pid "$BACKEND_PORT")"
if [ -n "$existing_pid" ]; then
  existing_cmd="$(ps -p "$existing_pid" -o command= | sed 's/^ *//')"
  fail "Port ${BACKEND_PORT} is in use by pid ${existing_pid}: ${existing_cmd}"
fi

if [ ! -d ".venv" ]; then
  echo "[backend] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

echo "[backend] Installing/updating dependencies from pyproject.toml..."
.venv/bin/pip install -e .

echo "[backend] Starting uvicorn on http://0.0.0.0:${BACKEND_PORT}"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload
