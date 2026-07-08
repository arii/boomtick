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
SKIP_NODE_DEPS="${SKIP_NODE_DEPS:-0}"
SKIP_PYTHON_DEPS="${SKIP_PYTHON_DEPS:-0}"
SKIP_ETL_DEPS="${SKIP_ETL_DEPS:-0}"
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
  if timeout 600 python3 -m pip install --disable-pip-version-check "$@"; then
    return 0
  fi
  timeout 600 python3 -m pip install --disable-pip-version-check --break-system-packages "$@"
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

normalize_nvmrc_for_snapshot() {
  [ -f ".nvmrc" ] || return 0
  have node || return 0
  local desired actual
  desired="$(tr -d '[:space:]' < .nvmrc)"
  actual="$(node --version)"
  case "$desired" in
    v[0-9]*|[0-9]*)
      if printf '%s' "$desired" | grep -Eq '^v?[0-9]+$'; then
        local desired_major actual_major
        desired_major="${desired#v}"
        actual_major="${actual#v}"
        actual_major="${actual_major%%.*}"
        if [ "$desired_major" = "$actual_major" ]; then
          log "Normalizing .nvmrc from ${desired} to ${actual}."
          printf '%s\n' "$actual" > .nvmrc
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
    corepack enable || true
    corepack prepare "pnpm@${PNPM_VERSION}" --activate || true
  fi
  have pnpm || npm install -g "pnpm@${PNPM_VERSION}"
  log "pnpm: $(pnpm --version)"
}

install_python_deps() {
  have python3 || err "python3 is required."
  log "Installing Python dependencies for dev tools..."
  # satisfy boomtick-cli requirement of setuptools < 81
  pip_install --root-user-action=ignore --upgrade pip "setuptools<81.0.0" wheel

  if [ -f "requirements-dev.txt" ]; then
    log "Installing from requirements-dev.txt..."
    pip_install --root-user-action=ignore -r requirements-dev.txt
  fi

  if [ -f "boomtick-pkg/cli/pyproject.toml" ]; then
    log "Installing boomtick-cli in editable mode..."
    # Use standard user prefix to ensure deterministic binary location
    python3 -m pip install --user -e "${REPO_ROOT}/boomtick-pkg/cli" --break-system-packages

    export PATH="$HOME/.local/bin:$PATH"

    if ! have td-cli || ! have td; then
      err "td/td-cli not found on PATH after editable install. Path: $PATH"
    fi
    STATUS_PYTHON="INSTALLED (td-cli)"
  else
    pip_install --root-user-action=ignore requests google-genai python-dotenv pydantic click PyGithub
    STATUS_PYTHON="INSTALLED (minimal)"
  fi

  if [ -f "requirements-dev.txt" ]; then
    pip_install --root-user-action=ignore -r requirements-dev.txt
    STATUS_PYTHON="${STATUS_PYTHON} + DEV"
  fi

  if [ -f "etl/requirements.txt" ] && [ "$SKIP_ETL_DEPS" != "1" ]; then
    pip_install --root-user-action=ignore -r etl/requirements.txt
    STATUS_PYTHON="${STATUS_PYTHON} + ETL"
  fi
}

install_node_deps() {
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
  if [ "$SKIP_PLAYWRIGHT" = "1" ]; then
    STATUS_PLAYWRIGHT="SKIPPED (SKIP_PLAYWRIGHT=1)"
    return 0
  fi
  if [ ! -f "package.json" ]; then
    STATUS_PLAYWRIGHT="SKIPPED (no package.json)"
    return 0
  fi

  log "Installing Playwright browsers..."
  if pnpm exec playwright install --with-deps || npx --yes playwright install --with-deps; then
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

configure_git_hooks() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then return 0; fi
  log "Configuring git hooks path to .githooks..."
  if git config core.hooksPath .githooks; then
    if [ "$STATUS_GIT" = "PENDING" ]; then
      STATUS_GIT="INSTALLED"
    fi
  else
    STATUS_GIT="FAILED (git config)"
  fi
}

persist_environment() {
  log "Persisting environment settings to ~/.config/boomtick/env.sh..."
  local env_file="$HOME/.config/boomtick/env.sh"
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
nvm use ${NODE_MAJOR} >/dev/null 2>&1 || nvm install ${NODE_MAJOR} >/dev/null 2>&1
nvm alias default ${NODE_MAJOR} >/dev/null 2>&1

export PATH="\$HOME/.local/bin:\$PATH"
export PNPM_HOME="\$HOME/.local/share/pnpm"
export PATH="\$PNPM_HOME:\$PATH"
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
}

run_validation() {
  if [ "$SKIP_VALIDATION" = "1" ]; then return 0; fi
  log "Validation snapshot"
  node --version || true
  npm --version || true
  pnpm --version || true
  python3 --version || true
  have gh && gh --version | head -n 1 || true
  [ -x "$SCRIPT_DIR/snapshot.sh" ] && bash "$SCRIPT_DIR/snapshot.sh" || true
  if have pnpm; then
    pnpm run check:runtime-files || true
    pnpm run doctor || true
  fi
}

main() {
  echo "=== BoomTick Agent Environment Setup ==="
  echo "Repository: ${REPO_ROOT}"

  install_apt_tools

  log "Starting installation blocks..."
  pid_python=""
  pid_node=""
  pid_git=""

  # Python Block
  if [ "$SKIP_PYTHON_DEPS" = "1" ]; then
    STATUS_PYTHON="SKIPPED (SKIP_PYTHON_DEPS=1)"
  else
    (
      install_python_deps
      echo "$STATUS_PYTHON" > .status_python
    ) &
    pid_python=$!
  fi

  # Node Block
  if [ "$SKIP_NODE_DEPS" = "1" ] && [ "$SKIP_PLAYWRIGHT" = "1" ] && [ "$SKIP_NODE_INSTALL" = "1" ]; then
    STATUS_NODE="SKIPPED"
    STATUS_PLAYWRIGHT="SKIPPED"
  else
    (
      ensure_corepack_pnpm
      install_node_deps
      install_playwright
      echo "$STATUS_NODE" > .status_node
      echo "$STATUS_PLAYWRIGHT" > .status_playwright
    ) &
    pid_node=$!
  fi

  # Git Block
  if [ "$SKIP_REMOTE_CONFIG" = "1" ]; then
    STATUS_GIT="SKIPPED"
  else
    (
      configure_remote_origin
      configure_git_hooks
      echo "$STATUS_GIT" > .status_git
    ) &
    pid_git=$!
  fi

  local failed=0
  [ -n "$pid_python" ] && { wait $pid_python || { warn "Python block failed"; failed=1; }; }
  [ -n "$pid_node" ] && { wait $pid_node || { warn "Node block failed"; failed=1; }; }
  [ -n "$pid_git" ] && { wait $pid_git || { warn "Git block failed"; failed=1; }; }

  persist_environment

  [ -f .status_python ] && STATUS_PYTHON=$(cat .status_python) && rm .status_python || { [ -n "$pid_python" ] && STATUS_PYTHON="FAILED"; }
  [ -f .status_node ] && STATUS_NODE=$(cat .status_node) && rm .status_node || { [ -n "$pid_node" ] && STATUS_NODE="FAILED"; }
  [ -f .status_playwright ] && STATUS_PLAYWRIGHT=$(cat .status_playwright) && rm .status_playwright || { [ -n "$pid_node" ] && STATUS_PLAYWRIGHT="FAILED"; }
  [ -f .status_git ] && STATUS_GIT=$(cat .status_git) && rm .status_git || { [ -n "$pid_git" ] && STATUS_GIT="FAILED"; }

  run_validation

  echo ""
  echo "=== Setup Summary ==="
  echo "OS Packages:       $STATUS_APT"
  echo "Python Tooling:    $STATUS_PYTHON"
  echo "Node.js & pnpm:    $STATUS_NODE"
  echo "Playwright:        $STATUS_PLAYWRIGHT"
  echo "Git Configuration: $STATUS_GIT"
  echo "======================"

  if [ $failed -ne 0 ]; then
    echo "Rerun suggest: SKIP_APT=1 SKIP_VALIDATION=1 bash setup-agent.sh"
    err "Setup failed."
  fi
  log "Setup complete."
}

main "$@"
