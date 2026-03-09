#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "[backend] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

echo "[backend] Installing/updating dependencies from pyproject.toml..."
.venv/bin/pip install -e .

echo "[backend] Starting uvicorn on http://0.0.0.0:8008"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload
