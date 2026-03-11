#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
TASK_QUEUE="${TEMPORAL_TASK_QUEUE:-growth-agency}"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-}"
TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-localhost:7234}"
TEMPORAL_STARTUP_TIMEOUT="${TEMPORAL_STARTUP_TIMEOUT:-60}"

fail() {
  echo "[worker] error: $*" >&2
  exit 1
}

matching_worker_pid() {
  local matches
  local pid
  local cwd

  matches="$(pgrep -f "app.temporal.worker" || true)"
  if [ -z "$matches" ]; then
    return 0
  fi

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    cwd="$(lsof -a -d cwd -p "$pid" 2>/dev/null | awk 'NR==2 {print $NF}')"
    if [ "$cwd" = "$BACKEND_DIR" ]; then
      printf '%s\n' "$pid"
      return 0
    fi
  done <<< "$matches"
}

wait_for_temporal() {
  local python_cmd="$BACKEND_DIR/.venv/bin/python"
  if [ ! -x "$python_cmd" ]; then
    python_cmd="python3.11"
  fi

  "$python_cmd" - "$TEMPORAL_ADDRESS" "$TEMPORAL_STARTUP_TIMEOUT" <<'PY'
from __future__ import annotations

import socket
import sys
import time

address = sys.argv[1].strip()
timeout_seconds = float(sys.argv[2])

if ":" not in address:
    raise SystemExit(
        f"[worker] error: TEMPORAL_ADDRESS must be in host:port form. Current value: {address!r}"
    )

host, port_text = address.rsplit(":", 1)
try:
    port = int(port_text)
except ValueError as exc:
    raise SystemExit(
        f"[worker] error: TEMPORAL_ADDRESS port must be numeric. Current value: {address!r}"
    ) from exc

deadline = time.monotonic() + timeout_seconds
last_error: OSError | None = None

while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            print(f"[worker] Temporal reachable at {host}:{port}")
            raise SystemExit(0)
    except OSError as exc:
        last_error = exc
        time.sleep(1)

detail = "connection did not succeed"
if last_error is not None:
    detail = f"{last_error.__class__.__name__}: {last_error}"

raise SystemExit(
    f"[worker] error: Temporal did not become reachable at {host}:{port} "
    f"within {timeout_seconds:.0f}s ({detail})."
)
PY
}

cd "$BACKEND_DIR"

existing_worker_pid="$(matching_worker_pid)"
if [ -n "$existing_worker_pid" ]; then
  echo "[worker] Temporal worker already running on task queue ${TASK_QUEUE} (pid ${existing_worker_pid})."
  exit 0
fi

if [ ! -d ".venv" ] && ! command -v python3.11 >/dev/null 2>&1; then
  fail "python3.11 is required but not installed."
fi
if [ ! -d ".venv" ]; then
  echo "[worker] Creating Python 3.11 virtualenv..."
  python3.11 -m venv .venv
  .venv/bin/pip install --upgrade pip
fi

if [ -z "$SKIP_PIP_INSTALL" ]; then
  echo "[worker] Installing/updating dependencies from pyproject.toml..."
  .venv/bin/pip install -e .
fi

echo "[worker] Waiting for Temporal at ${TEMPORAL_ADDRESS}"
wait_for_temporal

echo "[worker] Starting Temporal worker on task queue ${TASK_QUEUE}"
exec .venv/bin/python "$ROOT/scripts/run_with_backend_env.py" \
  .venv/bin/python -m app.temporal.worker
