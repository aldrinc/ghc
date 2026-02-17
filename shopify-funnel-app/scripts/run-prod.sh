#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/apps/shopify-funnel/shopify-funnel-app"

cd "${APP_DIR}"

fail() {
  echo "error: $*" >&2
  exit 1
}

UVICORN_BIN="${SHOPIFY_FUNNEL_UVICORN_BIN:
-${APP_DIR}/.venv/bin/uvicorn}"
if [[ ! -x "${UVICORN_BIN}" ]]; then
  fail "Uvicorn not found at '${UVICORN_BIN}'. Install dependencies into .venv (or set SHOPIFY_FUNNEL_UVICORN_BIN)."
fi

PYTHON_BIN="${SHOPIFY_FUNNEL_PYTHON_BIN:-${APP_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  fail "Python not found at '${PYTHON_BIN}'. Install dependencies into .venv (or set SHOPIFY_FUNNEL_PYTHON_BIN)."
fi

# Validate configuration (loads .env via pydantic-settings).
if ! "${PYTHON_BIN}" - <<'PY'
import sys

try:
    from app.config import settings  # noqa: F401
except Exception as exc:
    print(f"error: invalid configuration: {exc}", file=sys.stderr)
    sys.exit(1)
PY
then
  exit 1
fi

HOST="${SHOPIFY_FUNNEL_HOST:-127.0.0.1}"
PORT="${SHOPIFY_FUNNEL_PORT:-8011}"
WORKERS="${SHOPIFY_FUNNEL_WORKERS:-1}"
LOG_LEVEL="${SHOPIFY_FUNNEL_LOG_LEVEL:-info}"
FORWARDED_ALLOW_IPS="${SHOPIFY_FUNNEL_FORWARDED_ALLOW_IPS:-127.0.0.1}"

if ! [[ "${PORT}" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  fail "Invalid SHOPIFY_FUNNEL_PORT: '${PORT}' (expected 1-65535)"
fi
if ! [[ "${WORKERS}" =~ ^[0-9]+$ ]] || (( WORKERS < 1 )); then
  fail "Invalid SHOPIFY_FUNNEL_WORKERS: '${WORKERS}' (expected >= 1)"
fi

echo "Starting shopify-funnel-app (production)"
echo "  host=${HOST} port=${PORT} workers=${WORKERS} log_level=${LOG_LEVEL}"
echo "  forwarded_allow_ips=${FORWARDED_ALLOW_IPS}"

exec "${UVICORN_BIN}" app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --log-level "${LOG_LEVEL}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}"
