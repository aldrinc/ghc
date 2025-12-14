#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/ghc-platform/frontend"

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  echo "[frontend] Installing npm dependencies..."
  npm install
fi

echo "[frontend] Starting Vite dev server on http://localhost:5173"
exec npm run dev -- --host --port 5173
