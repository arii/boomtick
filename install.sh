#!/usr/bin/env bash
set -e

# Support for --no-mcp and other flags
BUILD_MCP=1
for arg in "$@"; do
    if [ "$arg" == "--no-mcp" ]; then
        BUILD_MCP=0
    fi
done

# Check if we are inside the boomtick-pkg dir or root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "Installing BoomTick CLI..."
pip install -e ./cli --break-system-packages

if [ "$BUILD_MCP" -eq 1 ]; then
    echo "Building BoomTick MCP..."
    cd mcp
    if command -v pnpm &> /dev/null; then
        pnpm install --engine-strict=false
        npx tsc
    elif command -v npm &> /dev/null; then
        npm install
        npm run build
    else
        echo "Warning: Neither pnpm nor npm found. Skipping MCP build."
    fi
fi

echo "BoomTick installation complete!"
