# Problem Statement
Environment setup (Node, Python, caching, dependency installation) is duplicated across multiple workflow files. Furthermore, the release pipeline is fragmented across `release-logic.yml`, `release-please.yml`, and `release.yml`, with reusable workflows unnecessarily cluttering the GitHub Actions sidebar.

# Goal
Create a master `.github/actions/setup-all` composite action to centralize environment setup, and consolidate the release workflows into a single `.github/workflows/release.yml` file, moving reusable logic out of the `.github/workflows/` directory.

# Non-Goals
- We will not change how `release-please` functions or how packages are published to npm/PyPI.
- We will not address CI or Issue ChatOps workflows here.

# Proposed Approach
1. Create a top-level composite action at `.github/actions/setup-all/action.yml` that handles Node/pnpm setup, optional Python setup, caching, and dependency installation.
2. Update existing workflows to use `uses: ./.github/actions/setup-all` instead of their duplicated setup steps or the older `setup-env` action.
3. Consolidate `release-logic.yml` and `release-please.yml` into a single `.github/workflows/release.yml`.
4. Move any purely reusable deployment logic into local composite actions within `.github/actions/` to remove them from the Actions UI sidebar.
5. Update `release-please-config.json` to map the new `.github/actions/setup-all` component.
6. Delete the deprecated workflow files (`release-logic.yml`, `release-please.yml`).

# Alternatives Considered
- Keeping the monorepo setup duplicated: Rejected due to maintenance overhead and slower workflow execution times.
- Using reusable workflows instead of composite actions for setup: Composite actions are preferred for environment setup as they run in the same runner context as the caller, preserving environment variables and paths.

# Architectural Impact
This refactor drastically simplifies workflow definitions across the repository. It centralizes dependency caching and runtime setup, ensuring consistency. It also removes reusable workflows from the top-level Actions UI, resulting in a cleaner sidebar.

# Scope
Creation of `.github/actions/setup-all/action.yml`, consolidation of release workflows into `.github/workflows/release.yml`, and updating references across the repository to use the new master setup action.

# SPECIFY SCOPE
Creation of `.github/actions/setup-all/action.yml`, consolidation of release workflows into `.github/workflows/release.yml`, and updating references across the repository to use the new master setup action.

# DEFINITION OF DONE
- Master setup action is created and tested.
- Existing workflows are updated to use the new action.
- Release pipelines are unified and legacy workflows are removed.

# UNDERSTAND THE ISSUE
- Review the current `setup-env` action (if it exists) and the setup steps scattered across various workflows.
- Review `release-logic.yml` and `release-please.yml` to understand the full release lifecycle.

# DETERMINE APPROACH
- Define the inputs for the `setup-all` composite action (e.g., `setup-python: boolean`).
- Structure `release.yml` to trigger `release-please` on push to main, and trigger the publishing logic on tag creation.