#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1
  pwd
)"

cd "${APP_DIR}"

fail() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  local name="$1"
  if ! command -v "${name}" >/dev/null 2>&1; then
    fail "Missing required command: ${name}"
  fi
}

require_cmd bash
require_cmd apt-get

if [[ ! -r /etc/os-release ]]; then
  fail "Unable to detect OS (missing /etc/os-release). This script targets Ubuntu 22.04."
fi

# shellcheck disable=SC1091
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  fail "Unsupported OS: expected ubuntu, got '${ID:-unknown}'."
fi
if [[ "${VERSION_ID:-}" != "22.04" ]]; then
  fail "Unsupported Ubuntu version: expected 22.04, got '${VERSION_ID:-unknown}'."
fi

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
  require_cmd sudo
  SUDO="sudo"
fi

echo "==> Installing system packages (Ubuntu 22.04)"
${SUDO} apt-get update
if ! ${SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  build-essential \
  python3.11 \
  python3.11-venv \
  python3.11-dev; then
  fail "Failed to install required packages (python3.11, venv, build tools). Ensure python3.11 is available in your apt repos, then re-run."
fi

PY_BIN="$(command -v python3.11 || true)"
if [[ -z "${PY_BIN}" ]]; then
  fail "python3.11 is not available after install."
fi

PY_VERSION="$("${PY_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PY_VERSION}" != "3.11" ]]; then
  fail "Expected Python 3.11, found ${PY_VERSION} at ${PY_BIN}."
fi

echo "==> Creating venv (.venv)"
if [[ -d ".venv" ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    fail "Found .venv but .venv/bin/python is missing. Delete .venv and re-run."
  fi
  VENV_VERSION="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "${VENV_VERSION}" != "3.11" ]]; then
    fail "Existing .venv is Python ${VENV_VERSION} (expected 3.11). Delete .venv and re-run."
  fi
else
  "${PY_BIN}" -m venv .venv
fi

echo "==> Installing Python dependencies"
if ! .venv/bin/pip install -U pip; then
  fail "pip upgrade failed."
fi
if ! .venv/bin/pip install .; then
  fail "Dependency install failed (pip install .)."
fi

echo "==> Done"
echo "Next: run ./scripts/run-prod.sh"

