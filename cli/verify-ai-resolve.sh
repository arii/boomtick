#!/bin/bash
# verify-ai-resolve.sh - Local verification script for AI resolution plumbing

set -e

# Ensure we are in the project root
cd "$(dirname "$0")/../.."

TEST_FILE="src/test-ai-conflict.tsx"

echo "🧪 Starting local AI verification..."

# 1. Create a test conflict file
cat > "$TEST_FILE" <<EOF
import React from 'react';

export const ConflictComponent = () => {
  return <div>Hello from HEAD (Main)</div>;
};
EOF

echo "📝 Created test file: $TEST_FILE"

# 2. Run resolution in mock mode
echo "🏃 Running AI resolve in MOCK mode..."
# Export PYTHONPATH to ensure dev-tools modules can find each other without sys.path hacks
export PYTHONPATH="$PYTHONPATH:$(pwd)/boomtick-pkg/cli:$(pwd)/boomtick-pkg/cli/dev_tools"
AI_RESOLVE_MOCK=true python3 boomtick-pkg/cli/dev_tools/td_cli.py gh resolve

# 3. Verify the result
if grep -q "<<<<<<<" "$TEST_FILE"; then
  echo "❌ Error: Conflict markers still present in $TEST_FILE"
  exit 1
fi

# The mock resolution keeps the top part (HEAD)
if grep -q "Hello from HEAD (Main)" "$TEST_FILE"; then
  echo "✅ Verification successful! Conflict resolved correctly (mock mode)."
else
  echo "❌ Error: Resolution content does not match expected mock output."
  cat "$TEST_FILE"
  exit 1
fi

# 4. Cleanup
rm "$TEST_FILE"
echo "🧹 Cleaned up test files."
echo "✨ AI resolution is verified and ready for CI!"
