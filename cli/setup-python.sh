#!/bin/bash
set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "=== Setting up Python CLI Environment ==="

# Helper for tool checks
check_tool() {
  if ! command -v "$1" &> /dev/null; then
    return 1
  fi
  return 0
}

# 1. Setup Virtual Environment
rm -rf .venv
if check_tool uv; then
  echo "Using uv for high-speed setup..."
  if ! uv venv .venv; then
    echo "❌ Error: uv failed to create virtual environment."
    exit 1
  fi
  source .venv/bin/activate
  echo "Installing CLI package in editable mode with uv..."
  pip uninstall -y setuptools 2>/dev/null || true
  uv pip install "setuptools<81.0.0" wheel
  if ! uv pip install -e cli/; then
    echo "❌ Error: uv pip install failed."
    exit 1
  fi
  if [ -f "cli/requirements-dev.txt" ]; then
    uv pip install -r cli/requirements-dev.txt || true
  fi
elif check_tool python3; then
  echo "uv not found, falling back to python3 -m venv..."
  if ! python3 -m venv .venv; then
    echo "❌ Error: Failed to create virtual environment with venv."
    exit 1
  fi
  source .venv/bin/activate
  echo "Installing CLI package in editable mode with pip..."
  pip uninstall -y setuptools 2>/dev/null || true
  pip install "setuptools<81.0.0" wheel
  if ! pip install -e cli/; then
    echo "❌ Error: pip install failed."
    exit 1
  fi
  if [ -f "cli/requirements-dev.txt" ]; then
    pip install -r cli/requirements-dev.txt || true
  fi
else
  echo "❌ Error: Neither uv nor python3 is available. Cannot set up Python environment."
  exit 1
fi

echo "=== Python Setup Complete! ==="
echo "To activate the environment, run: source .venv/bin/activate"
