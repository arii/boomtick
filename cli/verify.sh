#!/bin/bash

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "=== DevTools Verification & Setup Utility ==="

check_tool() {
  if ! command -v "$1" &> /dev/null; then
    return 1
  fi
  return 0
}

echo "--- 1. Checking Environment Variables ---"
if [ -z "$GITHUB_TOKEN" ]; then
    echo "⚠️ Warning: GITHUB_TOKEN is not set. GitHub Operations will fail."
else
    echo "✅ GitHub token is present."
fi

echo "--- 2. Checking Python Environment ---"
if check_tool python3; then
    echo "✅ Python is available."
else
    echo "❌ Error: python3 is required."
    return 1
fi

echo "--- 3. Setting up Python Virtual Environment ---"
if [ ! -d ".venv" ]; then
    if check_tool uv; then
      echo "Using uv for high-speed setup..."
      uv venv .venv
      source .venv/bin/activate
      uv pip install -e ./cli/
    elif check_tool python3; then
      echo "Falling back to python3 -m venv..."
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -e ./cli/
    else
      echo "❌ Error: Cannot set up Python environment."
      return 1
    fi
else
    source .venv/bin/activate
    echo "✅ Python environment already set up."
fi

echo "--- 4. Checking CLI Tooling ---"
# Just test if the CLI runs
if PYTHONPATH=./cli:./cli/dev_tools python3 ./cli/dev_tools/cli.py --help > /dev/null; then
    echo "✅ dev_tools CLI is functional."
else
    echo "❌ Error: dev_tools CLI failed to execute."
    return 1
fi

echo "--- 5. Checking Node Environment ---"
if check_tool pnpm; then
    echo "✅ pnpm is available."
else
    echo "⚠️ Warning: pnpm is not installed. Node builds may fail."
fi

echo "=== Verification Complete! ==="
