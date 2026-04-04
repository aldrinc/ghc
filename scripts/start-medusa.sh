#!/usr/bin/env bash
# Start the local Medusa B2B backend for development
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDUSA_DIR="$ROOT/.tmp/medusa-b2b-starter/backend"
TMP_ROOT="$ROOT/.tmp/runtime"
TMPDIR_ROOT="$TMP_ROOT/tmp"
COREPACK_HOME_ROOT="$TMP_ROOT/corepack"
YARN_GLOBAL_ROOT="$TMP_ROOT/yarn-global"
POSTGRES_BOOTSTRAP_DB="${POSTGRES_BOOTSTRAP_DB:-postgres}"
MEDUSA_ADMIN_EMAIL="${MEDUSA_ADMIN_EMAIL:-admin@test.com}"
MEDUSA_ADMIN_PASSWORD="${MEDUSA_ADMIN_PASSWORD:-supersecret}"
MEDUSA_ADMIN_ID="${MEDUSA_ADMIN_ID:-admin}"
MEDUSA_DB_ADMIN_USER="${MEDUSA_DB_ADMIN_USER:-$(id -un)}"
MEDUSA_DB_ADMIN_PASSWORD="${MEDUSA_DB_ADMIN_PASSWORD:-}"

DB_HOST=""
DB_PORT=""
DB_USER=""
DB_PASSWORD=""
DB_NAME=""

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

load_medusa_env() {
    if [ ! -f "$MEDUSA_DIR/.env" ]; then
        fail "Medusa environment file not found at $MEDUSA_DIR/.env"
    fi

    set -a
    # shellcheck disable=SC1090
    . "$MEDUSA_DIR/.env"
    set +a

    if [ -z "${DATABASE_URL:-}" ]; then
        fail "DATABASE_URL is not set in $MEDUSA_DIR/.env"
    fi
}

parse_database_url() {
    local -a parsed_parts

    while IFS= read -r line; do
        parsed_parts+=("$line")
    done < <(DATABASE_URL="$DATABASE_URL" node <<'EOF'
const raw = process.env.DATABASE_URL

if (!raw) {
  process.exit(1)
}

const url = new URL(raw)

const hostname = url.hostname || "localhost"
const port = url.port || "5432"
const username = decodeURIComponent(url.username || "")
const password = decodeURIComponent(url.password || "")
const database = decodeURIComponent(url.pathname.replace(/^\/+/, ""))

if (!username || !database) {
  process.exit(2)
}

process.stdout.write([hostname, port, username, password, database].join("\n") + "\n")
EOF
)

    if [ "${#parsed_parts[@]}" -ne 5 ]; then
        fail "Unable to parse DATABASE_URL from $MEDUSA_DIR/.env"
    fi

    DB_HOST="${parsed_parts[0]}"
    DB_PORT="${parsed_parts[1]}"
    DB_USER="${parsed_parts[2]}"
    DB_PASSWORD="${parsed_parts[3]}"
    DB_NAME="${parsed_parts[4]}"

    if [ -z "$DB_HOST" ] || [ -z "$DB_PORT" ] || [ -z "$DB_USER" ] || [ -z "$DB_NAME" ]; then
        fail "DATABASE_URL is missing required connection details"
    fi
}

run_psql() {
    local user="$1"
    local database="$2"
    local sql="$3"

    PGPASSWORD="${DB_PASSWORD:-}" PSQLRC=/dev/null psql -w -X -h "$DB_HOST" -p "$DB_PORT" -U "$user" -d "$database" -Atqc "$sql"
}

sql_quote() {
    printf "%s" "$1" | sed "s/'/''/g"
}

database_exists() {
    local result

    result="$(PGPASSWORD="${DB_PASSWORD:-}" PSQLRC=/dev/null psql -w -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$POSTGRES_BOOTSTRAP_DB" -Atqc "select 1 from pg_database where datname = '$(sql_quote "$DB_NAME")';" 2>/dev/null || true)"
    [ "$result" = "1" ]
}

ensure_database_exists() {
    if database_exists; then
        return
    fi

    echo "Creating Medusa database '$DB_NAME' via PostgreSQL role '$MEDUSA_DB_ADMIN_USER'..."
    if ! PGPASSWORD="${MEDUSA_DB_ADMIN_PASSWORD:-}" createdb -w -h "$DB_HOST" -p "$DB_PORT" -U "$MEDUSA_DB_ADMIN_USER" -O "$DB_USER" "$DB_NAME"; then
        fail "Unable to create PostgreSQL database '$DB_NAME'. Ensure role '$MEDUSA_DB_ADMIN_USER' exists and has CREATEDB, or pre-create the database."
    fi
}

ensure_plpgsql_available() {
    if PGPASSWORD="${DB_PASSWORD:-}" PSQLRC=/dev/null psql -w -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Atqc 'DO $$ BEGIN NULL; END $$ LANGUAGE plpgsql;' >/dev/null 2>&1; then
        return
    fi

    fail "PostgreSQL on $DB_HOST:$DB_PORT cannot execute PL/pgSQL blocks. Medusa migrations require plpgsql."
}

has_seed_data() {
    local result

    result="$(run_psql "$DB_USER" "$DB_NAME" 'select 1 from product limit 1;' 2>/dev/null || true)"
    [ "$result" = "1" ]
}

admin_user_exists() {
    local result

    result="$(PGPASSWORD="${DB_PASSWORD:-}" PSQLRC=/dev/null psql -w -X -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Atqc "select 1 from \"user\" where email = '$(sql_quote "$MEDUSA_ADMIN_EMAIL")' limit 1;" 2>/dev/null || true)"
    [ "$result" = "1" ]
}

bootstrap_medusa() {
    echo "Bootstrapping Medusa database..."
    ensure_database_exists
    ensure_plpgsql_available

    echo "Applying Medusa migrations..."
    "$MEDUSA_DIR/node_modules/.bin/medusa" db:migrate --execute-safe-links

    if ! has_seed_data; then
        echo "Seeding Medusa sample data..."
        "$MEDUSA_DIR/node_modules/.bin/medusa" exec ./src/scripts/seed.ts
    fi

    if ! admin_user_exists; then
        echo "Creating Medusa admin user..."
        "$MEDUSA_DIR/node_modules/.bin/medusa" user -e "$MEDUSA_ADMIN_EMAIL" -p "$MEDUSA_ADMIN_PASSWORD" -i "$MEDUSA_ADMIN_ID"
    fi
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
if ! command -v node >/dev/null 2>&1; then
    fail "node is not available on PATH. Ensure your Node 20+ environment is active before starting Medusa."
fi
load_medusa_env
parse_database_url

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

# Check if PostgreSQL is running on the configured host and port
echo "Checking PostgreSQL on $DB_HOST:$DB_PORT..."
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    echo "WARNING: PostgreSQL not running on $DB_HOST:$DB_PORT."
    echo "Please ensure PostgreSQL is running before starting Medusa."
fi

echo ""
cd "$MEDUSA_DIR"
bootstrap_medusa

echo ""
echo "Starting Medusa development server..."
echo "Backend URL: http://localhost:9000"
echo "Admin App URL: http://localhost:9000/app"
echo "Admin API URL: http://localhost:9000/admin"
echo "Admin credentials: $MEDUSA_ADMIN_EMAIL / $MEDUSA_ADMIN_PASSWORD"
echo ""

if [ ! -x "$MEDUSA_DIR/node_modules/.bin/medusa" ]; then
    fail "Medusa CLI is missing at $MEDUSA_DIR/node_modules/.bin/medusa. Reinstall dependencies."
fi

exec "$MEDUSA_DIR/node_modules/.bin/medusa" develop
