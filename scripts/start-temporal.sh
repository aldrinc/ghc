#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT/ghc-platform/infra"

if docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE=(docker-compose)
else
  echo "[temporal] docker compose is required (install Docker Desktop or docker-compose)." >&2
  exit 1
fi

cd "$INFRA_DIR"

echo "[temporal] Starting Temporal + Postgres stack..."
"${DOCKER_COMPOSE[@]}" up -d temporal temporal-ui postgres

echo "[temporal] Temporal server: localhost:7234 (UI at http://localhost:8234)"
