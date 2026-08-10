# Design: Migrate Boomtick to Standalone Distribution (Remove Submodule)

# Problem Statement

Currently, consumer repositories must integrate Boomtick as a Git submodule to use its GitHub composite actions (e.g., `mcp/actions/impact-analysis`) and scripts. This approach, as documented in `docs/onboarding.md` ("Step 1: Add Boomtick as a Submodule"), causes configuration drift and burdens consumer repositories with maintaining redundant `package.json` scripts (e.g., `impact:analysis`, `impact:build-main`). Furthermore, `mcp/actions/impact-analysis/action.yml` uses a hardcoded `node -e` check on the consumer's `package.json`, forcing them to mirror Boomtick's internal script definitions exactly.

# Goal

Distribute Boomtick components via standard package managers (NPM and PyPI) so that consumer repositories can execute Boomtick workflows (like Impact Analysis) without requiring a Git submodule or redundant local `package.json` script mirroring.

# Non-Goals

*   Rewriting the core implementation of the impact analysis logic (`scripts/impact-analysis.ts`, etc.).
*   Removing the monorepo structure for local Boomtick development.
*   Supporting alternative package managers beyond NPM/pnpm and PyPI/pip.

# Proposed Approach

1.  **NPM Packaging for Scripts**:
    Update `@arii/boomtick-mcp` (or create a sibling `@arii/boomtick-scripts` package) to explicitly export the contents of `scripts/` (e.g., `impact-analysis.ts`, `impact-build-main.ts`) as executable bins.
2.  **PyPI Packaging for CLI**:
    Ensure the `cli/` directory (`td-cli`) is configured for publishing to PyPI as `boomtick-cli` (as noted in `.release-please-config.json`).
3.  **Refactor GitHub Actions**:
    Remove the `node -e "const pkg = require('./package.json')..."` checks from `mcp/actions/impact-analysis/action.yml`. Change step executions from `pnpm run impact:analysis` to direct toolchain invocations (e.g., `npx @arii/boomtick-mcp impact-analysis`).
4.  **Documentation Updates**:
    Update `docs/onboarding.md` and `docs/impact-analysis-integration.md` to remove submodule Git commands, replacing them with standard dependency installation instructions.

# Alternatives Considered

*   **GitHub Releases with Pre-compiled Binaries**: Distributing standalone binaries using tools like `pkg` or PyInstaller. *Rejected* because it adds significant build complexity, and NPM/PyPI are well-integrated into the target ecosystem workflows.
*   **Keeping the Submodule but Simplifying Scripts**: Injecting scripts via a bash wrapper inside the submodule. *Rejected* as it does not resolve the core friction of Git submodule drift and manual pointer updates.

# Architectural Impact

*   **Consumer Decoupling**: Consumer repositories are fully decoupled from Boomtick's internal source tree structure.
*   **Version Management**: Consumers will manage Boomtick versions via standard tools (Dependabot, `package.json`, `requirements.txt`) rather than Git submodule pointers.
*   **Workflow Execution**: GitHub Actions will download binaries on-demand or use cached global installations rather than executing scripts out of a local cloned directory.

# Scope

This migration covers modifying the packaging configurations (NPM/PyPI), updating step executions within GitHub Action YAML files (`mcp/actions/impact-analysis/action.yml`, `.github/actions/setup-workspace/action.yml`), and updating end-user documentation (`docs/onboarding.md` and `docs/impact-analysis-integration.md`).

# UNDERSTAND THE ISSUE

The current deployment model forces tight coupling via Git submodules. Consumers must mirror Boomtick's `package.json` scripts to utilize its Actions because workflows like `impact-analysis/action.yml` execute `pnpm run impact:analysis` directly in the consumer's root. This creates friction during onboarding and maintenance, as updates to Boomtick scripts require synchronized updates to consumer repository files.

# DETERMINE APPROACH

The solution leverages the existing multi-package architecture defined in `.release-please-config.json` (which already tracks `boomtick-cli` and `@arii/boomtick-mcp`). By expanding `@arii/boomtick-mcp` to include `"bin"` exports for the TypeScript scripts, GitHub Actions can be refactored to execute these tools dynamically (e.g., via `npx`). The Python CLI is similarly packaged for distribution via PyPI, eliminating the need to source it from a local file path.

# SPECIFY SCOPE

1.  Update `mcp/package.json` to include `"bin"` mappings exposing the scripts currently defined under `scripts/`.
2.  Verify and finalize Python packaging in `cli/pyproject.toml` for `td-cli`.
3.  Modify `mcp/actions/impact-analysis/action.yml` (lines 40-52) to remove `package.json` script validation and use published binaries.
4.  Update `docs/onboarding.md` (remove Submodule Step 1) and `docs/impact-analysis-integration.md`.

# DEFINITION OF DONE

1.  NPM package configuration is updated to expose impact analysis scripts as binaries.
2.  PyPI package configuration for `td-cli` is verified and documented for publishing.
3.  `mcp/actions/impact-analysis/action.yml` executes tools without relying on consumer `package.json` scripts.
4.  `docs/onboarding.md` and `docs/impact-analysis-integration.md` no longer contain Git submodule integration instructions.
5.  All CI tests, validations, and schema checks pass successfully.