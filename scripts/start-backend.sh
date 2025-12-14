#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/ghc-platform/backend"

cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
  echo "[backend] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

echo "[backend] Installing/updating dependencies from pyproject.toml..."
.venv/bin/pip install -e .

echo "[backend] Starting uvicorn on http://localhost:8000"
exec .venv/bin/uvicorn app.main:app --port 8000 --reload
