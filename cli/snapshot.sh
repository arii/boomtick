#!/bin/bash

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "=== DevTools Snapshot & Debug Utility ==="

CONFIG_FILE="project_config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo "Using configuration from $CONFIG_FILE"
    if command -v jq &> /dev/null; then
        echo "Configuration state:"
        jq '.' "$CONFIG_FILE"
    else
        echo "jq not installed. Raw configuration:"
        cat "$CONFIG_FILE"
    fi
else
    echo "⚠️ Warning: $CONFIG_FILE not found. Using defaults."
fi

# Basic environment check
echo "--- Environment ---"
echo "Python version: $(python3 --version 2>&1 || echo 'Not installed')"

# Node version validation
NODE_VERSION=$(node --version 2>&1 | sed 's/^v//' || echo 'Not installed')
echo "Node version: v$NODE_VERSION"

if [ -f ".nvmrc" ]; then
    PINNED_NODE=$(cat .nvmrc | sed 's/^v//')
    PINNED_MAJOR=$(echo "$PINNED_NODE" | cut -d. -f1)
    CURRENT_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    if [ "$CURRENT_MAJOR" != "$PINNED_MAJOR" ]; then
        echo "❌ Error: Node version mismatch!"
        echo "   Expected: v$PINNED_NODE (from .nvmrc)"
        echo "   Actual:   v$NODE_VERSION"
        echo "   Please install and use the pinned version."
    else
        echo "✅ Node major version matches .nvmrc"
    fi
fi

echo "pnpm version: $(pnpm --version 2>&1 || echo 'Not installed')"

# Token check (do not print token!)
if [ -n "$GITHUB_TOKEN" ]; then
    echo "GitHub token: Present"
else
    echo "GitHub token: Missing"
fi

if [ -n "$GEMINI_API_KEY" ]; then
    echo "Gemini API key: Present"
else
    echo "Gemini API key: Missing"
fi

echo "=== Snapshot Complete ==="
