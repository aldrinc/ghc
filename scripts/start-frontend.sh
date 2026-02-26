#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/mos/frontend"

cd "$FRONTEND_DIR"

if [ ! -x "node_modules/.bin/vite" ]; then
  echo "[frontend] Frontend dependencies are missing (vite binary not found). Installing npm dependencies with dev packages..."
  npm install --include=dev
fi

if [ ! -x "node_modules/.bin/vite" ]; then
  echo "[frontend] Error: vite is still unavailable after npm install. Check npm output and local Node/npm configuration." >&2
  exit 1
fi

echo "[frontend] Starting Vite dev server on http://localhost:5275"
exec npm run dev -- --host --port 5275
