#!/usr/bin/env bash
# Start the local Medusa B2B backend for development
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDUSA_DIR="$ROOT/.tmp/medusa-b2b-starter/backend"
TMP_ROOT="$ROOT/.tmp/runtime"
TMPDIR_ROOT="$TMP_ROOT/tmp"
COREPACK_HOME_ROOT="$TMP_ROOT/corepack"
YARN_GLOBAL_ROOT="$TMP_ROOT/yarn-global"

fail() {
    echo "[medusa] error: $*" >&2
    exit 1
}

prepare_runtime_dirs() {
    mkdir -p "$TMPDIR_ROOT" "$COREPACK_HOME_ROOT" "$YARN_GLOBAL_ROOT"
    chmod 700 "$TMPDIR_ROOT" "$COREPACK_HOME_ROOT" "$YARN_GLOBAL_ROOT" 2>/dev/null || true
    export TMPDIR="$TMPDIR_ROOT/"
    export COREPACK_HOME="$COREPACK_HOME_ROOT"
    export YARN_GLOBAL_FOLDER="$YARN_GLOBAL_ROOT"
}

run_yarn() {
    if command -v corepack >/dev/null 2>&1; then
        corepack yarn "$@"
        return
    fi
    if command -v yarn >/dev/null 2>&1; then
        yarn "$@"
        return
    fi
    fail "Neither corepack nor yarn is available on PATH."
}

echo "================================================"
echo "Starting Medusa B2B Backend"
echo "================================================"
echo ""

# Check if Medusa directory exists
if [ ! -d "$MEDUSA_DIR" ]; then
    echo "[medusa] error: Medusa B2B starter not found at $MEDUSA_DIR"
    echo "Please clone it first:"
    echo "  git clone https://github.com/medusajs/medusa-starter-b2b.git .tmp/medusa-b2b-starter"
    exit 1
fi

prepare_runtime_dirs

# Check if node_modules exists
if [ ! -d "$MEDUSA_DIR/node_modules" ]; then
    echo "Installing Medusa dependencies..."
    cd "$MEDUSA_DIR"
    run_yarn install
fi

# Check if Redis is running
echo "Checking Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "WARNING: Redis is not running. Starting Redis..."
    brew services start redis 2>/dev/null || redis-server --daemonize yes 2>/dev/null || true
    sleep 2
fi

# Check if PostgreSQL is running on port 5433
echo "Checking PostgreSQL on port 5433..."
if ! pg_isready -h localhost -p 5433 > /dev/null 2>&1; then
    echo "WARNING: PostgreSQL not running on port 5433."
    echo "Please ensure PostgreSQL is running with the medusa_backend database."
    echo "The mOS backend startup script should handle this."
fi

echo ""
echo "Starting Medusa development server..."
echo "Backend URL: http://localhost:9000"
echo "Admin URL: http://localhost:9000/admin"
echo "Admin credentials: admin@test.com / supersecret"
echo ""

cd "$MEDUSA_DIR"
if ! command -v node >/dev/null 2>&1; then
    fail "node is not available on PATH. Ensure your Node 20+ environment is active before starting Medusa."
fi
if [ ! -x "$MEDUSA_DIR/node_modules/.bin/medusa" ]; then
    fail "Medusa CLI is missing at $MEDUSA_DIR/node_modules/.bin/medusa. Reinstall dependencies."
fi

exec "$MEDUSA_DIR/node_modules/.bin/medusa" develop
