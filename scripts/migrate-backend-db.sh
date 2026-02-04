#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-}"

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "[backend] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

if [ -z "$SKIP_PIP_INSTALL" ]; then
  echo "[backend] Installing/updating dependencies from pyproject.toml..."
  .venv/bin/pip install -e .
fi

echo "[backend] Running database migrations (alembic upgrade head)..."
.venv/bin/alembic upgrade head

echo "[backend] Migration status:"
.venv/bin/alembic current
