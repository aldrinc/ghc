#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
TASK_QUEUE="${TEMPORAL_TASK_QUEUE:-growth-agency}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-}"

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "[worker] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

if [ -z "$SKIP_PIP_INSTALL" ]; then
  echo "[worker] Installing/updating dependencies from pyproject.toml..."
  .venv/bin/pip install -e .
fi

echo "[worker] Starting Temporal worker on task queue ${TASK_QUEUE}"
exec .venv/bin/python "$ROOT/scripts/run_with_backend_env.py" \
  .venv/bin/python -m app.temporal.worker
