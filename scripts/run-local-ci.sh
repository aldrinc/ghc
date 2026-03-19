#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_root/mos/backend"
frontend_dir="$repo_root/mos/frontend"
compose_file="$repo_root/mos/infra/docker-compose.yml"
ci_database_name="app_ci_local_$$"

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$command_name" >&2
    exit 1
  fi
}

require_file() {
  local path="$1"

  if [ ! -f "$path" ]; then
    printf 'Required file is missing: %s\n' "$path" >&2
    exit 1
  fi
}

require_directory() {
  local path="$1"

  if [ ! -d "$path" ]; then
    printf 'Required directory is missing: %s\n' "$path" >&2
    exit 1
  fi
}

require_executable() {
  local path="$1"

  if [ ! -x "$path" ]; then
    printf 'Required executable is missing: %s\n' "$path" >&2
    exit 1
  fi
}

wait_for_postgres() {
  local container_id
  local status
  local attempts

  container_id="$(docker compose -f "$compose_file" ps -q postgres)"
  if [ -z "$container_id" ]; then
    printf 'Failed to resolve the local Postgres container from %s.\n' "$compose_file" >&2
    exit 1
  fi

  attempts=0
  while [ "$attempts" -lt 30 ]; do
    status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
    if [ "$status" = "healthy" ]; then
      return 0
    fi
    if [ "$status" = "dead" ] || [ "$status" = "exited" ]; then
      printf 'Local Postgres container is not healthy (status: %s).\n' "$status" >&2
      exit 1
    fi

    attempts=$((attempts + 1))
    sleep 1
  done

  printf 'Timed out waiting for local Postgres to become healthy.\n' >&2
  exit 1
}

run_postgres_sql() {
  local database_name="$1"
  local sql="$2"

  docker compose -f "$compose_file" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U app -d "$database_name" -c "$sql" >/dev/null
}

cleanup_ci_database() {
  run_postgres_sql "postgres" "DROP DATABASE IF EXISTS \"$ci_database_name\" WITH (FORCE);" || true
}

require_command docker
require_command node
require_command npm
require_file "$compose_file"
require_file "$frontend_dir/package-lock.json"
require_directory "$frontend_dir/node_modules"
require_executable "$backend_dir/.venv/bin/alembic"
require_executable "$backend_dir/.venv/bin/pytest"

if ! docker compose version >/dev/null 2>&1; then
  printf 'docker compose is required for local CI validation.\n' >&2
  exit 1
fi

trap cleanup_ci_database EXIT

printf 'Starting local Postgres...\n'
docker compose -f "$compose_file" up -d postgres >/dev/null
wait_for_postgres
run_postgres_sql "postgres" "DROP DATABASE IF EXISTS \"$ci_database_name\" WITH (FORCE);"
run_postgres_sql "postgres" "CREATE DATABASE \"$ci_database_name\";"

printf 'Running backend CI checks...\n'
(
  cd "$backend_dir"
  export DATABASE_URL="postgresql+psycopg2://app:app@localhost:5433/$ci_database_name"
  export CLERK_JWT_ISSUER="https://example.com/issuer"
  export CLERK_JWKS_URL="https://example.com/.well-known/jwks.json"
  export CLERK_AUDIENCE='["mos"]'
  export BACKEND_CORS_ORIGINS='["http://localhost:5173"]'
  export TEMPORAL_ADDRESS="localhost:7234"

  ./.venv/bin/alembic upgrade head
  ./.venv/bin/pytest
)

printf 'Running frontend CI checks...\n'
(
  cd "$frontend_dir"
  export VITE_API_BASE_URL="http://localhost:8000"
  export VITE_CLERK_PUBLISHABLE_KEY="pk_test_placeholder"
  export VITE_CLERK_JWT_TEMPLATE="backend"

  npm run check:semantic-ui
  npm run build
)

printf 'Local CI validation passed.\n'
