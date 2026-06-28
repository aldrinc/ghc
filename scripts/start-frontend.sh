#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/mos/frontend"
FRONTEND_PORT="${FRONTEND_PORT:-5275}"
BACKEND_PORT="${BACKEND_PORT:-8008}"

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

resolve_dev_host() {
  if [ -n "${DEV_BIND_HOST:-}" ]; then
    printf '%s\n' "$DEV_BIND_HOST"
    return 0
  fi

  local wt0_ip
  wt0_ip="$(ip -4 addr show wt0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | sed -n '1p')"
  if [ -n "$wt0_ip" ]; then
    printf '%s\n' "$wt0_ip"
    return 0
  fi

  printf 'localhost\n'
}

env_file_defines() {
  local name="$1"
  local env_file="$FRONTEND_DIR/.env.local"

  if [ ! -f "$env_file" ]; then
    return 1
  fi

  grep -Eq "^[[:space:]]*(export[[:space:]]+)?${name}=" "$env_file"
}

is_loopback_host() {
  case "$1" in
    localhost|127.*|::1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

default_api_base_url() {
  local api_host="$BIND_HOST"

  if [ "$api_host" = "127.0.0.1" ]; then
    api_host="localhost"
  fi

  printf 'http://%s:%s\n' "$api_host" "$BACKEND_PORT"
}

cd "$FRONTEND_DIR"

if ! [[ "$FRONTEND_PORT" =~ ^[0-9]+$ ]] || (( FRONTEND_PORT < 1 || FRONTEND_PORT > 65535 )); then
  fail "Invalid FRONTEND_PORT '$FRONTEND_PORT' (expected 1-65535)."
fi

BIND_HOST="$(resolve_dev_host)"
if [ -z "${VITE_API_BASE_URL:-}" ]; then
  if ! is_loopback_host "$BIND_HOST"; then
    export VITE_API_BASE_URL="$(default_api_base_url)"
  elif ! env_file_defines "VITE_API_BASE_URL"; then
    export VITE_API_BASE_URL="$(default_api_base_url)"
  fi
fi

existing_frontend_pid="$(matching_frontend_pid "$FRONTEND_PORT")"
if [ -n "$existing_frontend_pid" ]; then
  echo "[frontend] Vite already running on http://${BIND_HOST}:${FRONTEND_PORT} (pid ${existing_frontend_pid})."
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

CANONICAL_URL="$(DEV_ACCESS_HOST="$BIND_HOST" "$ROOT/scripts/resolve-dev-access-url.sh" "$FRONTEND_PORT")"
echo "[frontend] Canonical access URL: ${CANONICAL_URL}"
echo "[frontend] Starting Vite dev server on http://${BIND_HOST}:${FRONTEND_PORT}"
exec npm run dev -- --host "$BIND_HOST" --port "$FRONTEND_PORT" --force
