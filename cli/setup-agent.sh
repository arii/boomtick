#!/usr/bin/env bash
set -Eeuo pipefail

# Agent setup script for the BoomTick / Tech Dancer repo.

# -------- repo root detection --------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P || pwd)"
START_DIR="$(pwd -P)"

find_repo_root() {
  local dir="$1"
  if git -C "$dir" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$dir" rev-parse --show-toplevel
    return 0
  fi

  while [ "$dir" != "/" ] && [ -n "$dir" ]; do
    if [ -d "$dir/.git" ] || [ -f "$dir/package.json" ] || [ -f "$dir/pnpm-lock.yaml" ]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

REPO_ROOT="$(find_repo_root "$START_DIR" || find_repo_root "$SCRIPT_DIR" || pwd -P)"
cd "$REPO_ROOT"

# -------- configuration --------
PNPM_VERSION="${PNPM_VERSION:-10.28.2}"
NODE_MAJOR="${NODE_MAJOR:-24}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_PLAYWRIGHT="${SKIP_PLAYWRIGHT:-0}"
SKIP_VALIDATION="${SKIP_VALIDATION:-0}"
SKIP_REMOTE_CONFIG="${SKIP_REMOTE_CONFIG:-0}"

export CI="${CI:-1}"
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-}"

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
  export NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-$HOME/.npm-global}"
  export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"
  mkdir -p "$NPM_CONFIG_PREFIX/bin"
fi

# Ensure local python bin is on path for td-cli
# We add these unconditionally so that even if the directories don't exist yet,
# they are present on the PATH for when pip later creates them during installation.
for bin_dir in "$HOME/.local/bin" "/github/home/.local/bin"; do
  case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) export PATH="$bin_dir:$PATH" ;;
  esac
done

# -------- helpers --------
log() { echo "[setup-agent] $*"; }
warn() { echo "[setup-agent] WARNING: $*" >&2; }
err() { echo "[setup-agent] ERROR: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

run_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    warn "No sudo/root available; cannot run: $*"
    return 127
  fi
}

pip_install() {
  # Ubuntu/Debian images may enable PEP 668. Try normal install first, then the
  # distro-compatible override, without masking genuine package errors.
  if python3 -m pip install --disable-pip-version-check "$@"; then
    return 0
  fi
  python3 -m pip install --disable-pip-version-check --break-system-packages "$@"
}

# -------- install steps --------
install_apt_tools() {
  if [ "$SKIP_APT" = "1" ]; then
    warn "SKIP_APT=1; skipping OS package install."
    return 0
  fi
  if ! have apt-get; then
    warn "apt-get not available; skipping OS package install."
    return 0
  fi

  log "Installing system tools..."
  run_sudo apt-get update -y || return 0
  run_sudo apt-get install -y \
    ca-certificates curl git jq unzip xz-utils gpg \
    python3 python3-pip python3-venv python3-setuptools python3-wheel \
    build-essential || warn "Some OS packages could not be installed. Continuing with available tools."

  if ! have gh; then
    log "Installing GitHub CLI (gh)..."
    # Ensure /usr/share/keyrings exists as a standard location for system keyrings
    if run_sudo mkdir -p /usr/share/keyrings; then
      curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | run_sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg >/dev/null || true
      run_sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg || true
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | run_sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null || true
      run_sudo apt-get update -y || true
      run_sudo apt-get install -y gh || warn "Unable to install gh; continuing."
    else
      warn "Unable to configure GitHub CLI apt repository; continuing."
    fi
  fi

  if ! have node; then
    log "Installing Node.js ${NODE_MAJOR}.x..."
    # Semgrep-ignore: bash.curl.security.curl-pipe-bash.curl-pipe-bash
    if curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" > nodesource_setup.sh && run_sudo bash nodesource_setup.sh; then
      rm nodesource_setup.sh
      run_sudo apt-get install -y nodejs || warn "Unable to install nodejs via apt."
    else
      rm -f nodesource_setup.sh
      warn "Unable to configure NodeSource repository."
    fi
  fi
}

ensure_node() {
  have node || err "node is required. Install Node.js or leave SKIP_APT unset on a Debian/Ubuntu image."
  have npm || err "npm is required but was not found with node."
  log "Node: $(node --version); npm: $(npm --version)"
}


normalize_nvmrc_for_snapshot() {
  # dev-tools/snapshot.sh currently compares .nvmrc literally against `node --version`.
  # Agent runtimes often pin only a major version such as `v22`, while Node reports
  # a full version such as `v24.16.0`. Normalize major-only pins so validation
  # does not report a false mismatch in Agent/Jules.
  [ -f ".nvmrc" ] || return 0
  have node || return 0

  local desired actual
  desired="$(tr -d '[:space:]' < .nvmrc)"
  actual="$(node --version)"

  case "$desired" in
    v[0-9]*|[0-9]*)
      # Only rewrite when .nvmrc is a major-only pin: v22 or 22.
      if printf '%s' "$desired" | grep -Eq '^v?[0-9]+$'; then
        local desired_major actual_major
        desired_major="${desired#v}"
        actual_major="${actual#v}"
        actual_major="${actual_major%%.*}"
        if [ "$desired_major" = "$actual_major" ]; then
          log "Normalizing .nvmrc from ${desired} to ${actual} for repo validation."
          printf '%s\n' "$actual" > .nvmrc
        else
          warn ".nvmrc requests ${desired}, but active Node is ${actual}."
        fi
      fi
      ;;
  esac
}

ensure_corepack_pnpm() {
  ensure_node
  normalize_nvmrc_for_snapshot
  log "Ensuring pnpm ${PNPM_VERSION} is available..."
  if have corepack; then
    corepack enable || warn "corepack enable failed; falling back to npm global pnpm."
    corepack prepare "pnpm@${PNPM_VERSION}" --activate || warn "corepack prepare failed; falling back to npm global pnpm."
  fi
  have pnpm || npm install -g "pnpm@${PNPM_VERSION}"
  log "pnpm: $(pnpm --version)"
}

install_python_deps() {
  have python3 || err "python3 is required."
  log "Installing Python dependencies for dev tools..."
  python3 -m pip --version || err "pip is required."
  pip_install --root-user-action=ignore --upgrade pip setuptools wheel

  if [ -f "boomtick-pkg/cli/pyproject.toml" ]; then
    (cd "${REPO_ROOT}/boomtick-pkg" && bash install.sh --no-mcp)
    have td-cli || err "td-cli not found on PATH after editable install of dev-tools."
  else
    pip_install --root-user-action=ignore requests google-genai python-dotenv pydantic click PyGithub
  fi

  if [ -f "etl/requirements.txt" ]; then
    pip_install --root-user-action=ignore -r etl/requirements.txt
  fi
}

install_node_deps() {
  have pnpm || err "pnpm is required."
  if [ ! -f "package.json" ]; then
    warn "package.json not found in ${REPO_ROOT}; skipping pnpm install."
    return 0
  fi

  log "Installing Node dependencies..."
  if [ -f "pnpm-lock.yaml" ]; then
    pnpm install --frozen-lockfile || pnpm install --no-frozen-lockfile
  else
    pnpm install
  fi
}

install_playwright() {
  if [ "$SKIP_PLAYWRIGHT" = "1" ]; then
    warn "SKIP_PLAYWRIGHT=1; skipping Playwright browser install."
    return 0
  fi
  if [ ! -f "package.json" ]; then
    warn "package.json not found; skipping Playwright install."
    return 0
  fi

  log "Installing Playwright system dependencies..."
  run_sudo env "PATH=$PATH" pnpm exec playwright install-deps || \
    run_sudo env "PATH=$PATH" npx --yes playwright install-deps || \
    warn "Playwright install-deps failed; continuing."

  log "Installing Playwright browsers (all)..."
  pnpm exec playwright install || \
    npx --yes playwright install || \
    warn "Playwright install failed; continuing."
}

configure_remote_origin() {
  if [ "$SKIP_REMOTE_CONFIG" = "1" ]; then
    warn "SKIP_REMOTE_CONFIG=1; skipping remote origin configuration."
    return 0
  fi
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Not a git repository; skipping remote origin configuration."
    return 0
  fi

  local current
  current="$(git remote get-url origin 2>/dev/null || true)"
  if [ -n "$current" ]; then
    log "remote.origin already configured: ${current}"
    return 0
  fi

  local repo_slug="${GITHUB_REPOSITORY:-}"
  if [ -z "$repo_slug" ]; then
    warn "GITHUB_REPOSITORY not set; skipping remote.origin configuration instead of guessing incorrectly."
    return 0
  fi

  git remote add origin "https://github.com/${repo_slug}.git"
  log "Configured remote.origin => https://github.com/${repo_slug}.git"
}

configure_git_hooks() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    warn "Not a git repository; skipping git hooks configuration."
    return 0
  fi

  log "Configuring git hooks path to .githooks..."
  git config core.hooksPath .githooks
}

run_validation() {
  if [ "$SKIP_VALIDATION" = "1" ]; then
    warn "SKIP_VALIDATION=1; skipping validation."
    return 0
  fi

  log "Validation snapshot"
  node --version
  npm --version
  pnpm --version
  python3 --version
  have gh && gh --version | head -n 1 || warn "gh not installed."

  [ -x "dev-tools/snapshot.sh" ] && bash dev-tools/snapshot.sh || warn "dev-tools/snapshot.sh not found/executable; skipped."
  if have pnpm; then
    pnpm run check:runtime-files || warn "Runtime file check failed."
    pnpm run doctor || warn "Runtime doctor check failed."
  fi
  command -v td && td gh --help > /dev/null
  log "Setup complete."
}

main() {
  echo "=== BoomTick Agent Environment Setup ==="
  echo "Repository: ${REPO_ROOT}"
  install_apt_tools
  ensure_corepack_pnpm
  install_python_deps
  configure_remote_origin
  configure_git_hooks
  install_node_deps
  install_playwright
  run_validation
}

main "$@"
