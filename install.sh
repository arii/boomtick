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
    if [ "$FORCE" -eq 1 ]; then return 0; fi

    # Node.js validation (24.x)
    if command -v node >/dev/null 2>&1; then
        NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VER" != "24" ]; then
            echo "Error: Node.js version 24.x is required (found v$(node -v | tr -d '\n')). Use --force to bypass."
            exit 1
        fi
    else
        echo "Error: Node.js not found. Node.js 24.x is required."
        exit 1
    fi

    # Python validation (3.x)
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VER=$(python3 -c 'import sys; print(sys.version_info.major)')
        if [ "$PYTHON_VER" -lt 3 ]; then
            echo "Error: Python 3.x is required."
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

# Idempotency for CLI
if [ "$FORCE" -eq 1 ] || ! command -v td-cli >/dev/null 2>&1; then
    echo "Installing BoomTick CLI..."
    pip install -e ./cli --break-system-packages
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
        elif command -v npm &> /dev/null; then
            npm install
            npm run build
        else
            echo "Warning: Neither pnpm nor npm found. Skipping MCP build."
        fi
        cd ..
    else
        echo "BoomTick MCP already built. Skipping (use --force to rebuild)."
    fi
fi

echo "BoomTick installation complete!"
