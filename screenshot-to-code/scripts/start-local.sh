#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"

has_env_value() {
  grep -Eq "^$1=.+$" "$ENV_FILE"
}

poetry_cmd() {
  if command -v poetry >/dev/null 2>&1; then
    echo "poetry"
    return
  fi

  if python3 -m poetry --version >/dev/null 2>&1; then
    echo "python3 -m poetry"
    return
  fi

  echo ""
}

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi

  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

ensure_poetry() {
  local cmd
  cmd="$(poetry_cmd)"
  if [ -n "$cmd" ]; then
    echo "$cmd"
    return
  fi

  echo "Poetry not found. Installing it with python3 -m pip --user." >&2
  python3 -m pip install --user poetry >/dev/null

  cmd="$(poetry_cmd)"
  if [ -n "$cmd" ]; then
    echo "$cmd"
    return
  fi

  echo "" >&2
}

ensure_frontend_dependencies() {
  if [ -d "$FRONTEND_DIR/node_modules" ]; then
    return
  fi

  if command -v yarn >/dev/null 2>&1; then
    (
      cd "$FRONTEND_DIR"
      yarn install
    )
    return
  fi

  if command -v corepack >/dev/null 2>&1; then
    (
      cd "$FRONTEND_DIR"
      corepack yarn install
    )
    return
  fi

  echo "Frontend dependencies are missing and Yarn is not available." >&2
  exit 1
}

POETRY_CMD="$(poetry_cmd)"
NPM_CMD="$(command -v npm || true)"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE." >&2
  echo "Populate it with ANTHROPIC_API_KEY or GEMINI_API_KEY before starting." >&2
  echo "Template: $BACKEND_DIR/.env.example" >&2
  exit 1
fi

if ! has_env_value "ANTHROPIC_API_KEY" && ! has_env_value "GEMINI_API_KEY" && ! has_env_value "OPENAI_API_KEY"; then
  echo "No API key found in $ENV_FILE." >&2
  echo "Set ANTHROPIC_API_KEY or GEMINI_API_KEY before starting the app." >&2
  exit 1
fi

if [ -z "$POETRY_CMD" ]; then
  POETRY_CMD="$(ensure_poetry)"
fi

if [ -z "$POETRY_CMD" ]; then
  echo "Poetry could not be installed automatically." >&2
  exit 1
fi

if [ -z "$NPM_CMD" ]; then
  echo "npm is not available." >&2
  exit 1
fi

(
  cd "$BACKEND_DIR"
  eval "$POETRY_CMD install --no-interaction" >/dev/null
)

ensure_frontend_dependencies

(
  cd "$BACKEND_DIR"
  eval "$POETRY_CMD run uvicorn main:app --reload --port 7001 --ws-max-size 268435456"
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  "$NPM_CMD" run dev
) &
FRONTEND_PID=$!

echo "Backend starting on http://127.0.0.1:7001"
echo "Frontend starting on http://127.0.0.1:5173"

while kill -0 "$BACKEND_PID" >/dev/null 2>&1 && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; do
  sleep 1
done

if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  wait "$BACKEND_PID"
  exit $?
fi

wait "$FRONTEND_PID"
exit $?
