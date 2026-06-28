#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/mos/backend"
FRONTEND_DIR="$ROOT/mos/frontend"
SHOPIFY_DIR="$ROOT/shopify-funnel-app"

SUDO=()
DOCKER_GROUP_CHANGED=0

usage() {
  cat <<'EOF'
Usage: ./scripts/setup-ubuntu-dev.sh

Bootstraps the local Ubuntu dev environment required by this repository's
existing startup scripts.

What it does:
  - verifies Ubuntu 22.04 or 24.04
  - installs Python 3.11, Node.js/npm, Docker Engine + Compose plugin, ngrok
  - bootstraps backend/shopify Python virtualenvs and frontend npm dependencies
  - validates required local env-file presence without generating placeholders

What it does not do:
  - start application services
  - create fake .env files or credentials

After this succeeds, start services with:
  ./scripts/open-dev-terminals.sh

If GUI terminals are unavailable, run these manually in separate shells:
  ./scripts/start-shopify-funnel.sh
  ./scripts/start-shopify-ngrok.sh
  ./scripts/start-temporal.sh
  ./scripts/start-postiz.sh
  ./scripts/start-backend.sh
  SKIP_PIP_INSTALL=1 ./scripts/start-worker.sh
  ./scripts/start-frontend.sh
EOF
}

log() {
  printf '[setup-ubuntu-dev] %s\n' "$*"
}

fail() {
  printf '[setup-ubuntu-dev] error: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "Missing required command: $name"
  fi
}

run_root() {
  if [ "${#SUDO[@]}" -gt 0 ]; then
    "${SUDO[@]}" "$@"
    return
  fi
  "$@"
}

write_root_file() {
  local path="$1"
  local content="$2"
  printf '%s\n' "$content" | run_root tee "$path" >/dev/null
}

require_supported_ubuntu() {
  local version_id

  [ -r /etc/os-release ] || fail "Unable to detect OS (missing /etc/os-release)."

  # shellcheck disable=SC1091
  . /etc/os-release

  [ "${ID:-}" = "ubuntu" ] || fail "Unsupported OS '${ID:-unknown}'. Expected Ubuntu."
  version_id="${VERSION_ID:-}"
  case "$version_id" in
    22.04|24.04) ;;
    *) fail "Unsupported Ubuntu version '$version_id'. Expected 22.04 or 24.04." ;;
  esac

  log "Detected ${PRETTY_NAME:-Ubuntu $version_id}"
}

init_sudo() {
  if [ "${EUID}" -eq 0 ]; then
    return
  fi
  need_cmd sudo
  SUDO=(sudo)
}

apt_install() {
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
}

ensure_base_packages() {
  log "Installing base system packages"
  run_root apt-get update
  apt_install \
    apt-transport-https \
    build-essential \
    ca-certificates \
    curl \
    git \
    gnupg \
    lsb-release \
    lsof \
    software-properties-common
}

have_python311() {
  if ! command -v python3.11 >/dev/null 2>&1; then
    return 1
  fi
  [ "$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11" ]
}

ensure_deadsnakes_ppa() {
  if compgen -G '/etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-*.list' >/dev/null; then
    return
  fi
  log "Adding deadsnakes PPA for Python 3.11"
  run_root add-apt-repository -y ppa:deadsnakes/ppa
}

ensure_python311() {
  if have_python311; then
    log "Python 3.11 already available"
    return
  fi

  log "Installing Python 3.11"
  if ! apt-cache show python3.11 >/dev/null 2>&1; then
    ensure_deadsnakes_ppa
    run_root apt-get update
  fi

  apt_install python3.11 python3.11-dev python3.11-venv
  have_python311 || fail "python3.11 is still unavailable after installation."
}

node_major_version() {
  node -p 'process.versions.node.split(".")[0]'
}

ensure_nodesource_repo() {
  local keyring="/etc/apt/keyrings/nodesource.gpg"
  local source_list="/etc/apt/sources.list.d/nodesource.list"
  local tmp_key

  log "Configuring NodeSource Node.js 20 repository"
  run_root install -d -m 0755 /etc/apt/keyrings
  tmp_key="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o "$tmp_key"
  run_root gpg --dearmor --yes -o "$keyring" "$tmp_key"
  rm -f "$tmp_key"
  write_root_file "$source_list" "deb [signed-by=$keyring] https://deb.nodesource.com/node_20.x nodistro main"
}

ensure_nodejs() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    if [ "$(node_major_version)" -ge 20 ]; then
      log "Node.js $(node -v) and npm $(npm -v) already available"
      return
    fi
    log "Upgrading existing Node.js $(node -v) to Node.js 20"
  fi

  ensure_nodesource_repo
  run_root apt-get update
  apt_install nodejs

  command -v node >/dev/null 2>&1 || fail "node is unavailable after installation."
  command -v npm >/dev/null 2>&1 || fail "npm is unavailable after installation."
  [ "$(node_major_version)" -ge 20 ] || fail "Installed Node.js $(node -v), but expected 20+."
}

ensure_docker_repo() {
  local arch codename keyring source_list tmp_key

  arch="$(dpkg --print-architecture)"
  codename="$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")"
  keyring="/etc/apt/keyrings/docker.gpg"
  source_list="/etc/apt/sources.list.d/docker.list"

  log "Configuring Docker APT repository"
  run_root install -d -m 0755 /etc/apt/keyrings
  tmp_key="$(mktemp)"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$tmp_key"
  run_root gpg --dearmor --yes -o "$keyring" "$tmp_key"
  rm -f "$tmp_key"
  write_root_file "$source_list" "deb [arch=$arch signed-by=$keyring] https://download.docker.com/linux/ubuntu $codename stable"
}

add_current_user_to_docker_group() {
  local target_user

  if [ "${EUID}" -eq 0 ]; then
    target_user="${SUDO_USER:-}"
  else
    target_user="$(id -un)"
  fi

  [ -n "$target_user" ] || return

  if id -nG "$target_user" | tr ' ' '\n' | grep -Fxq docker; then
    return
  fi

  log "Adding $target_user to docker group"
  run_root usermod -aG docker "$target_user"
  DOCKER_GROUP_CHANGED=1
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker and Docker Compose plugin already available"
    need_cmd systemctl
    run_root systemctl enable --now docker
    add_current_user_to_docker_group
    return
  fi

  ensure_docker_repo
  run_root apt-get update
  apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  need_cmd systemctl
  run_root systemctl enable --now docker
  command -v docker >/dev/null 2>&1 || fail "docker is unavailable after installation."
  docker compose version >/dev/null 2>&1 || fail "docker compose plugin is unavailable after installation."
  add_current_user_to_docker_group
}

ensure_ngrok_repo() {
  local keyring="/etc/apt/keyrings/ngrok.gpg"
  local source_list="/etc/apt/sources.list.d/ngrok.list"
  local tmp_key

  log "Configuring ngrok APT repository"
  run_root install -d -m 0755 /etc/apt/keyrings
  tmp_key="$(mktemp)"
  curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc -o "$tmp_key"
  run_root gpg --dearmor --yes -o "$keyring" "$tmp_key"
  rm -f "$tmp_key"
  write_root_file "$source_list" "deb [signed-by=$keyring] https://ngrok-agent.s3.amazonaws.com buster main"
}

ensure_ngrok() {
  if command -v ngrok >/dev/null 2>&1; then
    log "ngrok already available"
    return
  fi

  ensure_ngrok_repo
  run_root apt-get update
  apt_install ngrok
  command -v ngrok >/dev/null 2>&1 || fail "ngrok is unavailable after installation."
}

ensure_repo_venv() {
  local dir="$1"
  local label="$2"
  local venv_python="$dir/.venv/bin/python"

  if [ -d "$dir/.venv" ]; then
    [ -x "$venv_python" ] || fail "$label has an invalid .venv (missing $venv_python). Delete it and re-run."
    if [ "$("$venv_python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.11" ]; then
      fail "$label has a non-3.11 virtualenv at $dir/.venv. Delete it and re-run."
    fi
  else
    log "Creating $label virtualenv"
    python3.11 -m venv "$dir/.venv"
  fi

  log "Installing $label Python dependencies"
  "$dir/.venv/bin/pip" install --upgrade pip
  "$dir/.venv/bin/pip" install -e "$dir"
}

bootstrap_frontend() {
  log "Installing frontend npm dependencies"
  npm --prefix "$FRONTEND_DIR" install --include=dev

  [ -x "$FRONTEND_DIR/node_modules/.bin/vite" ] || fail "Frontend install completed, but vite is still unavailable."
}

validate_env_setup() {
  local missing=0

  if [ ! -f "$BACKEND_DIR/.env" ] && [ ! -f "$ROOT/.env" ] && [ ! -f "$ROOT/.env.local.consolidated" ]; then
    printf '[setup-ubuntu-dev] configuration missing: backend env not found.\n' >&2
    printf '  Create one of:\n' >&2
    printf '    - %s/.env\n' "$BACKEND_DIR" >&2
    printf '    - %s/.env\n' "$ROOT" >&2
    printf '    - %s/.env.local.consolidated\n' "$ROOT" >&2
    printf '  Use %s/.env.example as the source of required keys.\n' "$BACKEND_DIR" >&2
    missing=1
  fi

  if [ ! -f "$FRONTEND_DIR/.env.local" ]; then
    printf '[setup-ubuntu-dev] configuration missing: frontend env file %s/.env.local\n' "$FRONTEND_DIR" >&2
    printf '  Add at least VITE_CLERK_PUBLISHABLE_KEY, VITE_API_BASE_URL, and VITE_CLERK_JWT_TEMPLATE.\n' >&2
    missing=1
  fi

  if [ ! -f "$SHOPIFY_DIR/.env" ]; then
    printf '[setup-ubuntu-dev] configuration missing: Shopify env file %s/.env\n' "$SHOPIFY_DIR" >&2
    printf '  Use %s/.env.example as the source of required keys.\n' "$SHOPIFY_DIR" >&2
    missing=1
  fi

  if [ ! -f "$SHOPIFY_DIR/shopify.app.toml" ]; then
    printf '[setup-ubuntu-dev] configuration missing: %s/shopify.app.toml\n' "$SHOPIFY_DIR" >&2
    missing=1
  fi

  if [ "$missing" -ne 0 ]; then
    fail "Tooling/bootstrap finished, but required local configuration is incomplete. Fill the env files above and re-run this script."
  fi
}

print_success_next_steps() {
  log "Ubuntu dev setup complete"
  printf '\nNext steps:\n'
  printf '  1. Start a new shell session if you were just added to the docker group.\n'
  printf '  2. Launch services with ./scripts/open-dev-terminals.sh\n'
  printf '  3. If GUI terminals are unavailable, run the start-* scripts manually.\n'
  printf '  4. If ngrok is not authenticated yet, run: ngrok config add-authtoken <token>\n'
}

main() {
  if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    usage
    exit 0
  fi

  [ "$#" -eq 0 ] || fail "Unexpected arguments. Use --help for usage."

  require_supported_ubuntu
  init_sudo
  ensure_base_packages
  ensure_python311
  ensure_nodejs
  ensure_docker
  ensure_ngrok
  ensure_repo_venv "$BACKEND_DIR" "backend"
  ensure_repo_venv "$SHOPIFY_DIR" "shopify-funnel-app"
  bootstrap_frontend
  validate_env_setup
  print_success_next_steps

  if [ "$DOCKER_GROUP_CHANGED" -ne 0 ]; then
    printf '\n[setup-ubuntu-dev] note: docker group membership changed. Log out/in or start a fresh shell before running docker without sudo.\n'
  fi
}

main "$@"
