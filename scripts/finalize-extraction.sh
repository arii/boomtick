#!/usr/bin/env bash
# This script should be run in the standalone repository after extraction
# to fix up internal paths that were maintained for monorepo compatibility.

echo "Finalizing boomtick-pkg extraction..."

# Update internal GitHub Action references
grep -l "uses: ./boomtick-pkg/.github/actions/" .github/actions/*/action.yml | xargs sed -i 's|uses: ./boomtick-pkg/.github/actions/|uses: ./.github/actions/|g'

echo "Extraction finalized. Internal paths updated."
