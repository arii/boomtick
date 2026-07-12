#!/usr/bin/env bash
set -e

# Flags
BUILD_MCP=1
FORCE=0

for arg in "$@"; do
    if [ "$arg" == "--no-mcp" ]; then
        BUILD_MCP=0
    elif [ "$arg" == "--force" ]; then
        FORCE=1
    fi
done

# Validation Helper
validate_env() {
    # Initialize .env if it doesn't exist
    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
        echo "Initializing .env from .env.example..."
        cp .env.example .env
    fi

    if [ "$FORCE" -eq 1 ]; then return 0; fi

    # workspace.json is treated as a trusted repository configuration file.
    echo "Validating workspace configuration..."
    if [ -f "scripts/validate_workspace.py" ]; then
        ENGINES_JSON=$(python3 scripts/validate_workspace.py --get-engines | sed -n '/ENGINES_START/,/ENGINES_END/p' | sed '1d;$d')
    elif [ -f "boomtick-pkg/scripts/validate_workspace.py" ]; then
        ENGINES_JSON=$(python3 boomtick-pkg/scripts/validate_workspace.py --get-engines | sed -n '/ENGINES_START/,/ENGINES_END/p' | sed '1d;$d')
    fi

    # Extract versions from JSON if possible, otherwise use defaults
    REQ_NODE=$(echo "$ENGINES_JSON" | grep -o '"node": *"[^"]*"' | cut -d'"' -f4 | sed 's/>=//')
    REQ_PNPM=$(echo "$ENGINES_JSON" | grep -o '"pnpm": *"[^"]*"' | cut -d'"' -f4)
    REQ_PYTHON=$(echo "$ENGINES_JSON" | grep -o '"python": *"[^"]*"' | cut -d'"' -f4 | sed 's/>=//')

    REQ_NODE=${REQ_NODE:-24}
    REQ_PYTHON=${REQ_PYTHON:-3.10}

    # Node.js validation
    if command -v node >/dev/null 2>&1; then
        NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VER" -lt "${REQ_NODE%%.*}" ]; then
            echo "Error: Node.js version >=$REQ_NODE is required (found v$(node -v | tr -d '\n')). Use --force to bypass."
            exit 1
        fi
    else
        echo "Error: Node.js not found. Node.js >=$REQ_NODE is required."
        exit 1
    fi

    # Python validation
    if command -v python3 >/dev/null 2>&1; then
        # Check python version
        python3 -c "import sys; ver=sys.version_info; req='${REQ_PYTHON}'.split('.'); exit(0) if (ver.major > int(req[0]) or (ver.major == int(req[0]) and ver.minor >= int(req[1]))) else exit(1)"
        if [ $? -ne 0 ]; then
             echo "Error: Python >=$REQ_PYTHON is required (found $(python3 --version))."
             exit 1
        fi
    else
        echo "Error: python3 not found."
        exit 1
    fi
}

validate_env

# Check if we are inside the boomtick-pkg dir or root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Try to find resolve-cli.sh in standard locations
if [ -f "scripts/resolve-cli.sh" ]; then
    CLI_ROOT="$(bash scripts/resolve-cli.sh)"
elif [ -f "../scripts/resolve-cli.sh" ]; then
    CLI_ROOT="$(bash ../scripts/resolve-cli.sh)"
else
    # Fallback if scripts are missing
    if [ -d "cli" ]; then CLI_ROOT="$(pwd)/cli"; else CLI_ROOT="$(pwd)"; fi
fi
export CLI_ROOT

# Environment Isolation (venv)
VENV_PATH=""
if [ -d "../.venv" ]; then
    VENV_PATH="../.venv"
elif [ -d ".venv" ]; then
    VENV_PATH=".venv"
else
    # Prefer a local venv to avoid polluting global environment
    if [ -f "../package.json" ]; then
        VENV_PATH="../.venv"
    else
        VENV_PATH=".venv"
    fi
    if [ ! -d "$VENV_PATH" ]; then
        echo "Creating virtual environment in $VENV_PATH..."
        python3 -m venv "$VENV_PATH"
    fi
fi

PIP_OPTS=""
if [ -n "$VENV_PATH" ]; then
    PYTHON_BIN="$VENV_PATH/bin/python3"
    PIP_CMD="$VENV_PATH/bin/pip"
    echo "Using virtual environment: $VENV_PATH"
else
    PYTHON_BIN="python3"
    PIP_CMD="pip"
    PIP_OPTS="--break-system-packages"
fi

# Idempotency for CLI
if [ "$FORCE" -eq 1 ] || ! command -v td-cli >/dev/null 2>&1 || [ -n "$VENV_PATH" ]; then
    echo "Installing BoomTick CLI..."
    timeout 600 $PIP_CMD install -e "${CLI_ROOT}" $PIP_OPTS
    if [ -f "${CLI_ROOT}/requirements-dev.txt" ]; then
        timeout 600 $PIP_CMD install -r "${CLI_ROOT}/requirements-dev.txt" $PIP_OPTS
    fi
else
    echo "BoomTick CLI already installed. Skipping (use --force to reinstall)."
fi

if [ "$BUILD_MCP" -eq 1 ]; then
    # Idempotency for MCP
    if [ "$FORCE" -eq 1 ] || [ ! -d "mcp/node_modules" ]; then
        echo "Building BoomTick MCP..."
        cd mcp
        if command -v pnpm &> /dev/null; then
            pnpm install --engine-strict=false
            pnpm run build
            pnpm run sync:mcp-schemas
        elif command -v npm &> /dev/null; then
            npm install
            npm run build
            npm run sync:mcp-schemas
        else
            echo "Warning: Neither pnpm nor npm found. Skipping MCP build."
        fi
        cd ..
    else
        echo "BoomTick MCP already built. Skipping (use --force to rebuild)."
    fi
fi

echo "BoomTick installation complete!"

echo "Running post-installation diagnostics..."
if [ -n "$VENV_PATH" ]; then
    $PYTHON_BIN -m dev_tools.cli doctor
else
    td-cli doctor || python3 -m dev_tools.cli doctor
fi
