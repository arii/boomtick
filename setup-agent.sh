#!/usr/bin/env bash
set -Eeuo pipefail

# Agent setup script for the BoomTick repo.

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

# CLI_ROOT is now at the root cli/ directory
CLI_ROOT="${REPO_ROOT}/cli"
export CLI_ROOT

# -------- configuration --------
PNPM_VERSION="${PNPM_VERSION:-10.28.2}"
NODE_MAJOR="${NODE_MAJOR:-24}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_PLAYWRIGHT="${SKIP_PLAYWRIGHT:-0}"
SKIP_NODE_DEPS="${SKIP_NODE_DEPS:-0}"
SKIP_PYTHON_DEPS="${SKIP_PYTHON_DEPS:-0}"
SKIP_GH_INSTALL="${SKIP_GH_INSTALL:-0}"
SKIP_NODE_INSTALL="${SKIP_NODE_INSTALL:-0}"
SKIP_VALIDATION="${SKIP_VALIDATION:-0}"
SKIP_REMOTE_CONFIG="${SKIP_REMOTE_CONFIG:-0}"

export CI="${CI:-1}"
export DEBIAN_FRONTEND="${DEBIAN_FRONTEND:-noninteractive}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-}"

# Global status tracking
STATUS_APT="PENDING"
STATUS_PYTHON="PENDING"
STATUS_NODE="PENDING"
STATUS_GIT="PENDING"
STATUS_PLAYWRIGHT="PENDING"

if [ "$(id -u)" -ne 0 ] && ! command -v sudo >/dev/null 2>&1; then
  export NPM_CONFIG_PREFIX="${NPM_CONFIG_PREFIX:-$HOME/.npm-global}"
  export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"
  mkdir -p "$NPM_CONFIG_PREFIX/bin"
fi

# Ensure local python bin is on path for td-cli
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
  # Ubuntu/Debian images may enable PEP 668.
  # Use a 600s timeout to prevent hangs while allowing for slow networks.
  local PIP_CMD="python3 -m pip"
  local PIP_OPTS=""
  if [ -n "${VENV_PATH:-}" ]; then
    PIP_CMD="${VENV_PATH}/bin/pip"
  else
    PIP_OPTS="--break-system-packages"
  fi

  local max_retries=3
  local attempt=1
  while [ $attempt -le $max_retries ]; do
    log "pip install attempt $attempt/$max_retries: $*"
    if timeout 600 $PIP_CMD install --disable-pip-version-check "$@"; then
      return 0
    fi

    if [ -z "${VENV_PATH:-}" ]; then
      if timeout 600 $PIP_CMD install --disable-pip-version-check $PIP_OPTS "$@"; then
        return 0
      fi
    fi

    warn "pip install failed on attempt $attempt"
    attempt=$((attempt + 1))
    [ $attempt -le $max_retries ] && sleep 5
  done

  return 1
}

# -------- install steps --------
install_apt_tools() {
  if [ "$SKIP_APT" = "1" ]; then
    STATUS_APT="SKIPPED (SKIP_APT=1)"
    return 0
  fi
  if ! have apt-get; then
    STATUS_APT="SKIPPED (apt-get not found)"
    return 0
  fi

  local missing=()
  for pkg in curl git jq unzip xz-utils gpg python3 python3-pip python3-venv python3-setuptools python3-wheel build-essential; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done

  if [ ${#missing[@]} -eq 0 ]; then
    STATUS_APT="INSTALLED (Guarded)"
    log "All core system tools already installed."
  else
    log "Installing missing system tools: ${missing[*]}"
      if ! run_sudo timeout 300 apt-get update -y; then
      STATUS_APT="FAILED (apt-get update)"
      return 0
    fi
      if ! run_sudo timeout 600 apt-get install -y ca-certificates "${missing[@]}"; then
      STATUS_APT="WARNING (Partial apt install)"
      warn "Some OS packages could not be installed."
    else
      STATUS_APT="INSTALLED"
    fi
  fi

  # GitHub CLI
  if [ "$SKIP_GH_INSTALL" = "1" ]; then
    log "SKIP_GH_INSTALL=1; skipping gh install."
  elif ! have gh; then
    log "Installing GitHub CLI (gh)..."
    if run_sudo mkdir -p /usr/share/keyrings; then
      curl --connect-timeout 10 --max-time 60 -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | run_sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg >/dev/null || true
      run_sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg || true
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | run_sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null || true
      run_sudo timeout 300 apt-get update -y || true
      run_sudo timeout 600 apt-get install -y gh || warn "Unable to install gh."
    fi
  fi

  # Node.js
  if [ "$SKIP_NODE_INSTALL" = "1" ]; then
    log "SKIP_NODE_INSTALL=1; skipping node install."
  elif ! have node; then
    log "Installing Node.js ${NODE_MAJOR}.x..."
    if curl --connect-timeout 10 --max-time 60 -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" > nodesource_setup.sh && run_sudo bash nodesource_setup.sh; then
      rm nodesource_setup.sh
      run_sudo timeout 600 apt-get install -y nodejs || warn "Unable to install nodejs via apt."
    else
      rm -f nodesource_setup.sh
      warn "Unable to configure NodeSource repository."
    fi
  fi
}

ensure_node() {
  have node || err "node is required."
  have npm || err "npm is required."
  log "Node: $(node --version); npm: $(npm --version)"
}

ensure_corepack_pnpm() {
  log "Ensuring corepack and pnpm..."
  ensure_node
  log "Ensuring pnpm ${PNPM_VERSION} is available..."
  if have corepack; then
    corepack enable || true
    corepack prepare "pnpm@${PNPM_VERSION}" --activate || true
  fi
  have pnpm || npm install -g "pnpm@${PNPM_VERSION}"
  log "pnpm: $(pnpm --version)"
}

install_python_deps() {
  log "Installing Python dependencies..."
  have python3 || err "python3 is required."

  if [ ! -d "$VENV_PATH" ]; then
      log "Creating virtual environment in $VENV_PATH..."
      python3 -m venv "$VENV_PATH"
  fi
  export PATH="${VENV_PATH}/bin:$PATH"

  log "Installing Python dependencies for dev tools..."
  # satisfy boomtick-cli requirement of setuptools < 81
  python3 -m pip uninstall -y setuptools || true
  pip_install --root-user-action=ignore --upgrade pip "setuptools<81.0.0" wheel

  if [ -f "cli/pyproject.toml" ]; then
    log "Performing editable install of cli package..."
    pip_install --root-user-action=ignore -e cli/
    export PATH="$HOME/.local/bin:$PATH"
    if ! have td-cli && ! have td; then
      warn "td/td-cli not found on PATH after editable install. Path: $PATH"
    fi
    STATUS_PYTHON="INSTALLED (td-cli)"
  else
    pip_install --root-user-action=ignore requests google-genai python-dotenv pydantic click PyGithub
    STATUS_PYTHON="INSTALLED (minimal)"
  fi

  if [ -f "cli/requirements-dev.txt" ]; then
    pip_install --root-user-action=ignore -r cli/requirements-dev.txt
    STATUS_PYTHON="${STATUS_PYTHON} + DEV"
  fi
}

install_node_deps() {
  log "Installing Node.js dependencies..."
  if [ "$SKIP_NODE_DEPS" = "1" ]; then
    STATUS_NODE="SKIPPED (SKIP_NODE_DEPS=1)"
    return 0
  fi
  if [ ! -f "package.json" ]; then
    STATUS_NODE="SKIPPED (no package.json)"
    return 0
  fi

  log "Installing Node dependencies..."
  if [ -f "pnpm-lock.yaml" ]; then
    pnpm install --frozen-lockfile || pnpm install --no-frozen-lockfile
  else
    pnpm install
  fi
  STATUS_NODE="INSTALLED"
}

install_playwright() {
  log "Installing Playwright..."
  if [ "$SKIP_PLAYWRIGHT" = "1" ]; then
    STATUS_PLAYWRIGHT="SKIPPED (SKIP_PLAYWRIGHT=1)"
    return 0
  fi
  if [ ! -f "package.json" ]; then
    STATUS_PLAYWRIGHT="SKIPPED (no package.json)"
    return 0
  fi

  log "Installing Playwright browsers..."
  if pnpm exec playwright install --with-deps 2>/dev/null || npx --yes playwright install --with-deps 2>/dev/null; then
    STATUS_PLAYWRIGHT="INSTALLED"
  else
    STATUS_PLAYWRIGHT="FAILED"
  fi
}

configure_remote_origin() {
  if [ "$SKIP_REMOTE_CONFIG" = "1" ]; then
    STATUS_GIT="SKIPPED (SKIP_REMOTE_CONFIG=1)"
    return 0
  fi
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    STATUS_GIT="SKIPPED (not a git repo)"
    return 0
  fi

  local current
  current="$(git remote get-url origin 2>/dev/null || true)"
  if [ -n "$current" ]; then
    STATUS_GIT="INSTALLED (Guarded)"
    return 0
  fi

  local repo_slug="${GITHUB_REPOSITORY:-}"
  if [ -n "$repo_slug" ]; then
    git remote add origin "https://github.com/${repo_slug}.git"
    STATUS_GIT="INSTALLED"
  else
    STATUS_GIT="SKIPPED (missing GITHUB_REPOSITORY)"
  fi
}

persist_environment() {
  log "Persisting environment settings to ~/.config/boomtick/env.sh..."
  local env_file="$HOME/.config/boomtick/env.sh"
  local current_venv="${VENV_PATH-}"
  local target_rc=""

  # Detect user shell to determine appropriate RC file
  local user_shell
  user_shell=$(basename "${SHELL:-/bin/bash}")

  case "$user_shell" in
    bash) target_rc="$HOME/.bashrc" ;;
    zsh)  target_rc="$HOME/.zshrc" ;;
    *)
      warn "Persistence not automatically supported for shell: $user_shell. Manual setup required."
      target_rc="$HOME/.bashrc" # Fallback to bashrc
      ;;
  esac

  mkdir -p "$(dirname "$env_file")"

  # Create or overwrite the env file with current settings
  cat << EOE > "$env_file"
# BoomTick Environment Settings
export NODE_MAJOR="${NODE_MAJOR}"
export NVM_DIR="\$HOME/.nvm"
[ -s "\$NVM_DIR/nvm.sh" ] && \. "\$NVM_DIR/nvm.sh"

export PATH="\$HOME/.local/bin:\$PATH"
if [ -n "${current_venv}" ]; then
  export PATH="${current_venv}/bin:\$PATH"
fi
export PNPM_HOME="\$HOME/.local/share/pnpm"
export PATH="\$PNPM_HOME:\$PATH"
export CLI_ROOT="${CLI_ROOT}"
EOE

  # Source the env file in target RC if not already present
  if [ -f "$target_rc" ]; then
    if ! grep -Fq "source \"$env_file\"" "$target_rc"; then
      echo "" >> "$target_rc"
      echo "# Load BoomTick environment settings" >> "$target_rc"
      echo "[ -f \"$env_file\" ] && source \"$env_file\"" >> "$target_rc"
      log "Updated $target_rc with BoomTick environment loader."
    fi
  else
    warn "RC file $target_rc not found. Environment may not persist across sessions."
  fi

  # Apply to current session
  source "$env_file"

  # Ensure PATH is updated in the current session
  export PATH="$HOME/.local/bin:$PATH"
  if [ -n "${current_venv}" ]; then
    export PATH="${current_venv}/bin:$PATH"
  fi
  export PNPM_HOME="$HOME/.local/share/pnpm"
  export PATH="$PNPM_HOME:$PATH"
}

run_validation() {
  if [ "$SKIP_VALIDATION" = "1" ]; then return 0; fi
  log "Validation snapshot"
  node --version || true
  npm --version || true
  pnpm --version || true
  python3 --version || true
  have gh && gh --version | head -n 1 || true
  if have pnpm; then
    pnpm run doctor || true
    if have python3 && [ -f "$CLI_ROOT/dev_tools/schema_gen.py" ]; then
      log "Generating CLI schemas and contracts..."
      (
        export PYTHONPATH="$CLI_ROOT:${PYTHONPATH:-}"
        python3 "$CLI_ROOT/dev_tools/schema_gen.py"
        pnpm --filter @arii/boomtick-mcp exec tsx scripts/sync-contracts.ts
      ) || warn "Failed to generate schemas/contracts."
    fi
    pnpm --filter @arii/boomtick-mcp run sync:mcp-schemas || true
  fi
}

main() {
  echo "=== BoomTick Agent Environment Setup ==="
  echo "Repository: ${REPO_ROOT}"

  # Ensure VENV_PATH is set and exported for all blocks
  export VENV_PATH="${REPO_ROOT}/.venv"

  install_apt_tools

  log "Starting installation blocks..."

  # Sequential execution for stability in CI if needed, but keeping separate logic
  ensure_corepack_pnpm
  install_node_deps
  install_playwright
  STATUS_NODE="INSTALLED"

  install_python_deps
  STATUS_PYTHON="INSTALLED"

  configure_remote_origin
  STATUS_GIT="INSTALLED"

  persist_environment
  run_validation

  echo ""
  echo "=== Setup Summary ==="
  echo "OS Packages:       $STATUS_APT"
  echo "Python Tooling:    $STATUS_PYTHON"
  echo "Node.js & pnpm:    $STATUS_NODE"
  echo "Playwright:        $STATUS_PLAYWRIGHT"
  echo "Git Configuration: $STATUS_GIT"
  echo "======================"

  log "Setup complete."
}

main "$@"
