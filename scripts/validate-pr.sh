#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/mos/backend"
FRONTEND_DIR="$ROOT_DIR/mos/frontend"
TMP_DIR="$ROOT_DIR/.tmp/pre-push"
BACKEND_VENV_DIR="$TMP_DIR/backend-venv"
BACKEND_STAMP_PATH="$TMP_DIR/backend-pyproject.sha256"
FRONTEND_STAMP_PATH="$TMP_DIR/frontend-package-lock.sha256"
POSTGRES_CONTAINER_NAME="ghc-prepush-postgres"
POSTGRES_HOST_PORT="55432"

mkdir -p "$TMP_DIR"

log() {
  printf '[pr-checks] %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

select_python() {
  if command -v python3.11 >/dev/null 2>&1; then
    printf 'python3.11'
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf 'python3'
    return
  fi
  printf 'No suitable Python interpreter found (need python3.11 or python3).\n' >&2
  exit 1
}

file_hash() {
  local file_path="$1"
  "$PYTHON_BIN" - "$file_path" <<'PY'
import hashlib
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

ensure_backend_env() {
  local desired_hash
  local current_hash=""

  desired_hash="$(file_hash "$BACKEND_DIR/pyproject.toml")"
  if [[ -f "$BACKEND_STAMP_PATH" ]]; then
    current_hash="$(<"$BACKEND_STAMP_PATH")"
  fi

  if [[ ! -x "$BACKEND_VENV_DIR/bin/python" ]]; then
    log "Creating backend validation venv"
    "$PYTHON_BIN" -m venv "$BACKEND_VENV_DIR"
    current_hash=""
  fi

  if [[ "$current_hash" != "$desired_hash" ]]; then
    log "Installing backend validation dependencies"
    (
      cd "$BACKEND_DIR"
      "$BACKEND_VENV_DIR/bin/pip" install --upgrade pip >/dev/null
      "$BACKEND_VENV_DIR/bin/pip" install ".[dev]" >/dev/null
    )
    printf '%s' "$desired_hash" > "$BACKEND_STAMP_PATH"
  fi
}

ensure_frontend_deps() {
  local desired_hash
  local current_hash=""

  desired_hash="$(
    {
      file_hash "$FRONTEND_DIR/package-lock.json"
      file_hash "$FRONTEND_DIR/package.json"
    } | tr -d '\n'
  )"

  if [[ -f "$FRONTEND_STAMP_PATH" ]]; then
    current_hash="$(<"$FRONTEND_STAMP_PATH")"
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" || "$current_hash" != "$desired_hash" ]]; then
    log "Installing frontend dependencies"
    (
      cd "$FRONTEND_DIR"
      npm ci >/dev/null
    )
    printf '%s' "$desired_hash" > "$FRONTEND_STAMP_PATH"
  fi
}

cleanup_postgres() {
  docker rm -f "$POSTGRES_CONTAINER_NAME" >/dev/null 2>&1 || true
}

start_postgres() {
  cleanup_postgres
  log "Starting fresh Postgres 16 container"
  docker run -d \
    --name "$POSTGRES_CONTAINER_NAME" \
    -e POSTGRES_USER=app \
    -e POSTGRES_PASSWORD=app \
    -e POSTGRES_DB=app \
    -p "${POSTGRES_HOST_PORT}:5432" \
    postgres:16 >/dev/null

  for _ in $(seq 1 30); do
    if docker exec "$POSTGRES_CONTAINER_NAME" pg_isready -U app -d app >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  printf 'Postgres container did not become ready in time.\n' >&2
  exit 1
}

run_backend_checks() {
  log "Running backend migrations"
  (
    cd "$BACKEND_DIR"
    env \
      DATABASE_URL="postgresql+psycopg2://app:app@localhost:${POSTGRES_HOST_PORT}/app" \
      CLERK_JWT_ISSUER='https://example.com/issuer' \
      CLERK_JWKS_URL='https://example.com/.well-known/jwks.json' \
      CLERK_AUDIENCE='["mos"]' \
      BACKEND_CORS_ORIGINS='["http://localhost:5173"]' \
      TEMPORAL_ADDRESS='localhost:7234' \
      "$BACKEND_VENV_DIR/bin/alembic" upgrade head
  )

  log "Running backend tests"
  (
    cd "$BACKEND_DIR"
    env \
      DATABASE_URL="postgresql+psycopg2://app:app@localhost:${POSTGRES_HOST_PORT}/app" \
      CLERK_JWT_ISSUER='https://example.com/issuer' \
      CLERK_JWKS_URL='https://example.com/.well-known/jwks.json' \
      CLERK_AUDIENCE='["mos"]' \
      BACKEND_CORS_ORIGINS='["http://localhost:5173"]' \
      TEMPORAL_ADDRESS='localhost:7234' \
      "$BACKEND_VENV_DIR/bin/pytest" -q
  )
}

run_frontend_checks() {
  log "Running frontend semantic token check"
  (
    cd "$FRONTEND_DIR"
    node scripts/check-semantic-ui.mjs
  )

  log "Running frontend unit tests"
  (
    cd "$FRONTEND_DIR"
    npm run test:unit
  )

  log "Running frontend build"
  (
    cd "$FRONTEND_DIR"
    env \
      VITE_API_BASE_URL='http://localhost:8000' \
      VITE_CLERK_PUBLISHABLE_KEY='pk_test_placeholder' \
      VITE_CLERK_JWT_TEMPLATE='backend' \
      npm run build
  )
}

require_command docker
require_command npm
require_command node
PYTHON_BIN="$(select_python)"

ensure_backend_env
ensure_frontend_deps

trap cleanup_postgres EXIT
start_postgres
run_backend_checks
run_frontend_checks

log "All PR checks passed"
