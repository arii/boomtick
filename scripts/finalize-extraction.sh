#!/usr/bin/env bash
# This script should be run in the standalone repository after extraction
# to fix up internal paths that were maintained for monorepo compatibility.

echo "Finalizing boomtick-pkg extraction..."

# Update internal GitHub Action references (from monorepo-relative to package-relative)
# Inside the extracted repo, mcp/actions/ becomes mcp/actions/
# and .github/workflows/ becomes .github/workflows/
find mcp/actions/ -name "action.yml" -exec sed -i 's|uses: ./mcp/actions/|uses: ./mcp/actions/|g' {} +
find .github/workflows/ -name "*.yml" -exec sed -i 's|uses: ./mcp/actions/|uses: ./mcp/actions/|g' {} +

echo "Extraction finalized. Internal paths updated."
