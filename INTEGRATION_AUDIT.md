# BoomTick Integration Issues Log

This document tracks issues, bugs, and blockers identified during the integration of `boomtick-pkg` from the `tech-dancer` repository. These should be addressed in the upstream source to improve future extractions.

## Critical Bugs
- **Recursive Symlink**: The package contained a symlink at `boomtick-pkg/boomtick-pkg` pointing to `.`, causing infinite recursion for any directory-traversing tools (find, grep, linters).
- **Binary Artifacts**: Compiled Python files (`.pyc`) and `__pycache__` directories were present in the source tree and had to be manually purged.
- **Invalid Action Versions**: Composite actions in `mcp/actions/setup-workspace/action.yml` referenced non-existent versions of standard actions (e.g., `actions/setup-node@v6` instead of `v4`).

## Implementation Flaws
- **Redundant Configuration**: A duplicate `current_config.py` was present in the root of the source package, which mirrored logic already contained within the `dev_tools_sdk`.
- **Import Errors**:
    - `verify_versions.py`: Incorrect `sys.path` logic prevented importing the local `utils` module.
    - `ai_service.py`: Used `requests` in the Gemini fallback path without importing it.
- **Path Resolution**: `boomtick-pkg/mcp/src/config.ts` had an off-by-one error in its default `repoPath` calculation, pointing one level above the repository root.
- **Dependency Gaps**: `duckduckgo-search` was required by MCP tools but missing from `cli/pyproject.toml`.

## CI & Environment Blockers
- **Node Engine Strictness**: The `package.json` in both root and MCP package enforced `24.x`, while the runner environment provided `v22.22.1`. Relaxed to `>=22.0.0`.
- **Missing Root Scripts**: The `td gh pre-submit` command expects `type-check`, `lint`, and `test` scripts to be available at the repository root. These were added as delegations to the MCP subpackage.
- **Missing Root Configs**: Shared setup actions assumed `.node-version` and `.npmrc` were present in the repository root.
- **Git History Depth**: Automated version checks (`td gh pre-submit`) require `fetch-depth: 0` in CI to access `origin/main` for diff operations.
- **Missing Validation Scripts**: `scripts/detect-antipatterns.mjs` was required by the CLI's pre-submit check but was not included within the `boomtick-pkg` subdirectory in the source repo.
- **pnpm Filter Support**: The CI setup uses `pnpm --filter`, which requires a `pnpm-workspace.yaml` in the root that was previously missing.
