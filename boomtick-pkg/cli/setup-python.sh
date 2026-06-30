#!/bin/bash
set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "=== Setting up Python ETL Environment ==="

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
  echo "Installing Python dependencies with uv..."
  if ! uv pip install -r etl/requirements.txt; then
    echo "❌ Error: uv pip install failed."
    exit 1
  fi
elif check_tool python3; then
  echo "uv not found, falling back to python3 -m venv..."
  if ! python3 -m venv .venv; then
    echo "❌ Error: Failed to create virtual environment with venv."
    exit 1
  fi
  source .venv/bin/activate
  echo "Installing Python dependencies with pip..."
  if ! pip install -r etl/requirements.txt; then
    echo "❌ Error: pip install failed."
    exit 1
  fi
else
  echo "❌ Error: Neither uv nor python3 is available. Cannot set up Python environment."
  exit 1
fi

echo "=== Python Setup Complete! ==="
echo "To activate the environment, run: source .venv/bin/activate"
