#!/usr/bin/env bash
# Start the local Medusa B2B backend for development
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDUSA_DIR="$ROOT/.tmp/medusa-b2b-starter/backend"

echo "================================================"
echo "Starting Medusa B2B Backend"
echo "================================================"
echo ""

# Check if Medusa directory exists
if [ ! -d "$MEDUSA_DIR" ]; then
    echo "ERROR: Medusa B2B starter not found at $MEDUSA_DIR"
    echo "Please clone it first:"
    echo "  git clone https://github.com/medusajs/medusa-starter-b2b.git .tmp/medusa-b2b-starter"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "$MEDUSA_DIR/node_modules" ]; then
    echo "Installing Medusa dependencies..."
    cd "$MEDUSA_DIR"
    yarn install
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
yarn dev