#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CMD_TEMPORAL="cd \"$ROOT\" && ./scripts/start-temporal.sh"
CMD_BACKEND="cd \"$ROOT\" && ./scripts/start-backend.sh"
CMD_WORKER="cd \"$ROOT\" && SKIP_PIP_INSTALL=1 ./scripts/start-worker.sh"
CMD_FRONTEND="cd \"$ROOT\" && ./scripts/start-frontend.sh"
CMD_SHOPIFY_APP="cd \"$ROOT/shopify-funnel-app\" && if [ ! -d \".venv\" ]; then python3.11 -m venv .venv && .venv/bin/pip install --upgrade pip >/dev/null; fi && .venv/bin/pip install -e . >/dev/null && .venv/bin/uvicorn app.main:app --reload --port 8011"

if command -v osascript >/dev/null 2>&1; then
  # macOS Terminal
  osascript <<EOF
tell application "Terminal"
  do script "cd '$ROOT'; ./scripts/start-temporal.sh"
  do script "cd '$ROOT'; ./scripts/start-backend.sh"
  do script "cd '$ROOT'; ./scripts/start-worker.sh"
  do script "cd '$ROOT'; ./scripts/start-frontend.sh"
  do script "cd '$ROOT/shopify-funnel-app' && if [ ! -d \".venv\" ]; then python3.11 -m venv .venv && .venv/bin/pip install --upgrade pip >/dev/null; fi && .venv/bin/pip install -e . >/dev/null && .venv/bin/uvicorn app.main:app --reload --port 8011"
  activate
end tell
EOF
  exit 0
fi

if command -v gnome-terminal >/dev/null 2>&1; then
  gnome-terminal -- bash -lc "$CMD_TEMPORAL; exec bash" &
  gnome-terminal -- bash -lc "$CMD_BACKEND; exec bash" &
  gnome-terminal -- bash -lc "$CMD_WORKER; exec bash" &
  gnome-terminal -- bash -lc "$CMD_FRONTEND; exec bash" &
  gnome-terminal -- bash -lc "$CMD_SHOPIFY_APP; exec bash" &
  exit 0
fi

echo "Could not auto-launch terminals. Run these in separate shells:"
echo "$CMD_TEMPORAL"
echo "$CMD_BACKEND"
echo "$CMD_WORKER"
echo "$CMD_FRONTEND"
echo "$CMD_SHOPIFY_APP"
