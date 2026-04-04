#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/resolve-dev-access-url.sh <port> [path]

Print the canonical reachable URL for a private dev service on this machine.
Prefers DEV_ACCESS_HOST, then the resolved bind host, then the NetBird wt0 IP,
and falls back to 127.0.0.1.
USAGE
}

fail() {
  printf '[resolve-dev-access-url] error: %s\n' "$*" >&2
  exit 1
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

PORT="${1:-}"
PATH_SUFFIX="${2:-/}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  fail "invalid port '$PORT' (expected 1-65535)"
fi

case "$PATH_SUFFIX" in
  "") PATH_SUFFIX='/' ;;
  /*) ;;
  *) PATH_SUFFIX="/$PATH_SUFFIX" ;;
esac

resolve_host() {
  if [ -n "${DEV_ACCESS_HOST:-}" ] && [ "${DEV_ACCESS_HOST}" != "0.0.0.0" ]; then
    printf '%s\n' "$DEV_ACCESS_HOST"
    return 0
  fi

  if [ -n "${DEV_BIND_HOST:-}" ] && [ "${DEV_BIND_HOST}" != "0.0.0.0" ]; then
    printf '%s\n' "$DEV_BIND_HOST"
    return 0
  fi

  if [ -n "${BACKEND_HOST:-}" ] && [ "${BACKEND_HOST}" != "0.0.0.0" ]; then
    printf '%s\n' "$BACKEND_HOST"
    return 0
  fi

  local wt0_ip
  wt0_ip="$(ip -4 addr show wt0 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 | sed -n '1p')"
  if [ -n "$wt0_ip" ]; then
    printf '%s\n' "$wt0_ip"
    return 0
  fi

  printf '127.0.0.1\n'
}

HOST="$(resolve_host)"
printf 'http://%s:%s%s\n' "$HOST" "$PORT" "$PATH_SUFFIX"
