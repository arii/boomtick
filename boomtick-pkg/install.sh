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

# Dual-mode support for GitHub Actions
# If we are in the root of an extracted repo (no boomtick-pkg directory),
# create a symlink so that monolith-style GHA paths like './boomtick-pkg/mcp/actions' work.
if [ ! -d "boomtick-pkg" ]; then
    echo "Detected standalone mode. Creating boomtick-pkg symlink..."
    ln -s . boomtick-pkg
fi

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
