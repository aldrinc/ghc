#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
FRONTEND_DIR="$ROOT/mos/frontend"
INFRA_DIR="$ROOT/mos/infra"
BACKEND_PORT="${BACKEND_PORT:-8008}"
FRONTEND_PORT="${FRONTEND_PORT:-5275}"
SHOPIFY_FUNNEL_PORT="${SHOPIFY_FUNNEL_PORT:-8011}"

listener_pids() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true
}

matching_pids() {
  pgrep -f "$1" || true
}

worker_pids() {
  local matches
  local pid
  local cwd

  matches="$(pgrep -f "app.temporal.worker" || true)"
  if [ -z "$matches" ]; then
    return 0
  fi

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    cwd="$(lsof -a -d cwd -p "$pid" 2>/dev/null | awk 'NR==2 {print $NF}')"
    if [ "$cwd" = "$BACKEND_DIR" ]; then
      printf '%s\n' "$pid"
    fi
  done <<< "$matches"
}

merge_pids() {
  printf '%s\n' "$@" | awk 'NF && !seen[$0]++'
}

wait_for_exit() {
  local pids="$1"
  local attempt
  for attempt in $(seq 1 20); do
    local alive=""
    local pid
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        alive="${alive} ${pid}"
      fi
    done
    if [ -z "$alive" ]; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

stop_processes() {
  local label="$1"
  local pids="$2"
  if [ -z "$pids" ]; then
    echo "[stop-dev-services] ${label}: not running."
    return 0
  fi

  echo "[stop-dev-services] ${label}: stopping pids $(printf '%s ' $pids)"
  kill $pids 2>/dev/null || true

  if wait_for_exit "$pids"; then
    return 0
  fi

  local remaining=""
  local pid
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      remaining="${remaining} ${pid}"
    fi
  done

  remaining="$(printf '%s\n' $remaining | awk 'NF && !seen[$0]++')"
  if [ -n "$remaining" ]; then
    echo "[stop-dev-services] ${label}: force stopping pids $(printf '%s ' $remaining)"
    kill -KILL $remaining 2>/dev/null || true
  fi
}

frontend_pids="$(merge_pids \
  "$(listener_pids "$FRONTEND_PORT")" \
  "$(matching_pids "$FRONTEND_DIR/node_modules/.bin/vite .*--port $FRONTEND_PORT( |$)")" \
  "$(matching_pids "npm run dev -- .*--port $FRONTEND_PORT( |$)")")"
backend_pids="$(merge_pids \
  "$(listener_pids "$BACKEND_PORT")" \
  "$(matching_pids "$BACKEND_DIR/.venv/bin/uvicorn app.main:app .*--port $BACKEND_PORT( |$)")")"
worker_pids="$(worker_pids)"
shopify_pids="$(merge_pids \
  "$(listener_pids "$SHOPIFY_FUNNEL_PORT")" \
  "$(matching_pids "$ROOT/shopify-funnel-app/.venv/bin/uvicorn app.main:app .*--port $SHOPIFY_FUNNEL_PORT( |$)")")"
ngrok_pids="$(matching_pids "ngrok http .* $SHOPIFY_FUNNEL_PORT( |$)")"

stop_processes "frontend" "$frontend_pids"
stop_processes "backend" "$backend_pids"
stop_processes "worker" "$worker_pids"
stop_processes "shopify-funnel" "$shopify_pids"
stop_processes "shopify-ngrok" "$ngrok_pids"

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "[stop-dev-services] temporal stack: docker compose unavailable, skipping."
  exit 0
fi

if [ -d "$INFRA_DIR" ]; then
  (
    cd "$INFRA_DIR"
    "${DOCKER_COMPOSE[@]}" down
  )
  echo "[stop-dev-services] temporal stack: stopped."
fi
