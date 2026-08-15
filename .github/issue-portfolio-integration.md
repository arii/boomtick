---
title: "Align GitHub Workflows with Boomtick Zero-Submodule Integration and Configs"
---

# Problem Statement
The GitHub workflows in this repository utilize Boomtick composite actions but are currently pinned to a static commit hash (`605eebb56880a5ab47330f1e1eb2f9b9bbb4fd92`) instead of tracking the `main` branch. Furthermore, the repository is missing explicit initialization configuration for `.agent-context.json`, `project_config.json`, and needs to align the `pnpm` version to `10.28.2` as required by the latest Boomtick standards.

# Goal
1. Update all Boomtick composite action references within `.github/workflows/` to target `@main`.
2. Configure or ensure `project_config.json` correctly defines necessary repository parameters (e.g., `"github_repo": "arii/portfolio"`).
3. Ensure `.agent-context.json` can be generated correctly on bootstrap.
4. Pin the workspace `pnpm` version to `10.28.2`.

# Non-Goals
* Altering the deployment or build logic of the portfolio application.
* Updating external actions (like `actions/checkout`) not owned by the Boomtick project.
* Introducing a Boomtick git submodule.

# Proposed Approach
1. **Update Workflows:** Identify all instances of `uses: arii/boomtick/.github/actions/` in the workflow files and replace the hardcoded commit hash with `@main`.
2. **Setup Runtime & Environment:**
   - Update `pnpm-workspace.yaml` or `package.json` to ensure `pnpm` version `10.28.2` is configured.
   - Run `pnpm run agent:prime` to verify the `.agent-context.json` can be built successfully.
   - Update `project_config.json` at the root with required baseline schema data.

# Alternatives Considered
* **Periodic manual bumps of the commit hash:** Rejected as it creates unnecessary maintenance burden.

# Architectural Impact
Enforces the recommended Zero-Submodule Integration pattern while explicitly satisfying the CLI and agent tooling requirements for context indexing.

# Scope
* Affected files:
  * All `.github/workflows/*.yml` (updating commit hash to `@main`).
  * `project_config.json`
  * `package.json` / `pnpm-workspace.yaml`

# Validation Steps
* All Boomtick action references specify `@main`.
* The commit hash `605eebb56880a5ab47330f1e1eb2f9b9bbb4fd92` is entirely removed from workflow files.
* `project_config.json` contains valid configuration.
* `pnpm` is explicitly pinned to `10.28.2`.
* Validate that GitHub Actions pass in the repository.
