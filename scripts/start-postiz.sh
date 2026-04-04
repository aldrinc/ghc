#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT/mos/infra"
TEMPORAL_NAMESPACE="${POSTIZ_TEMPORAL_NAMESPACE:-default}"
WAIT_TIMEOUT_SECONDS="${POSTIZ_START_TIMEOUT_SECONDS:-120}"
BACKEND_ENV_FILES=(
  "$ROOT/.env"
  "$ROOT/.env.local.consolidated"
  "$ROOT/mos/backend/.env"
)

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "[postiz] docker compose is required (install Docker Desktop or docker-compose)." >&2
  exit 1
fi

cd "$INFRA_DIR"

wait_for_temporal_namespace() {
  local deadline
  deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))

  echo "[postiz] Waiting for Temporal namespace '$TEMPORAL_NAMESPACE'..."
  while (( SECONDS < deadline )); do
    if "${DOCKER_COMPOSE[@]}" exec -T postiz-temporal \
      temporal operator namespace describe -n "$TEMPORAL_NAMESPACE" --address postiz-temporal:7233 \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  echo "[postiz] Timed out waiting for Temporal namespace '$TEMPORAL_NAMESPACE'." >&2
  exit 1
}

wait_for_temporal_search_attributes() {
  local deadline
  deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))

  echo "[postiz] Waiting for Postiz Temporal search attributes..."
  while (( SECONDS < deadline )); do
    if "${DOCKER_COMPOSE[@]}" exec -T postiz-temporal \
      temporal operator search-attribute list -n "$TEMPORAL_NAMESPACE" --address postiz-temporal:7233 \
      2>/dev/null | grep -q "CustomStringField"; then
      return 0
    fi
    sleep 2
  done

  echo "[postiz] Timed out waiting for Postiz Temporal search attributes." >&2
  exit 1
}

wait_for_postiz_api() {
  local deadline
  local status
  deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))

  echo "[postiz] Waiting for Postiz API..."
  while (( SECONDS < deadline )); do
    status="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:4007/api/public/v1/is-connected || true)"
    if [[ "$status" != "000" && "$status" != "502" ]]; then
      echo "[postiz] Postiz API responded with HTTP $status."
      return 0
    fi
    sleep 2
  done

  echo "[postiz] Timed out waiting for the Postiz API to become available." >&2
  exit 1
}

env_var_present() {
  local name="$1"
  local file
  for file in "${BACKEND_ENV_FILES[@]}"; do
    if [ -f "$file" ] && rg -q "^[[:space:]]*${name}=.+$" "$file"; then
      return 0
    fi
  done
  return 1
}

report_mos_postiz_config() {
  local missing=()

  if ! env_var_present "POSTIZ_DEFAULT_BASE_URL"; then
    missing+=("POSTIZ_DEFAULT_BASE_URL")
  fi
  if ! env_var_present "POSTIZ_BROWSER_LOGIN_SECRET"; then
    missing+=("POSTIZ_BROWSER_LOGIN_SECRET")
  fi

  if [ "${#missing[@]}" -gt 0 ]; then
    echo "[postiz] warning: MOS automatic Postiz launch is not fully configured." >&2
    echo "[postiz] warning: Missing ${missing[*]} in local env files (.env, .env.local.consolidated, mos/backend/.env)." >&2
    echo "[postiz] warning: Expected local sidecar base URL: POSTIZ_DEFAULT_BASE_URL=http://localhost:4007/api" >&2
  fi
}

echo "[postiz] Starting dedicated Postgres/Redis/Temporal services..."
"${DOCKER_COMPOSE[@]}" up -d \
  postiz-db \
  postiz-redis \
  postiz-temporal-elasticsearch \
  postiz-temporal-postgresql \
  postiz-temporal \
  postiz-temporal-ui

wait_for_temporal_namespace
wait_for_temporal_search_attributes

echo "[postiz] Starting Postiz app container..."
"${DOCKER_COMPOSE[@]}" up -d --force-recreate postiz

wait_for_postiz_api
report_mos_postiz_config

echo "[postiz] Postiz UI: http://localhost:4007"
echo "[postiz] Postiz API: http://localhost:4007/api"
echo "[postiz] Temporal UI: http://localhost:8235"
