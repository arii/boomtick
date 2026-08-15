---
title: "Update Boomtick Composite Actions and Environment Configs"
---

# Problem Statement
The CI/CD workflows in this repository are currently pinning Boomtick composite actions to a specific, outdated commit hash (`605eebb56880a5ab47330f1e1eb2f9b9bbb4fd92`). Additionally, proper initialization and runtime configuration for `.agent-context.json` generation and project base parameters (such as `project_config.json`) require alignment with the newest Boomtick architecture (using `pnpm` 10.28.2). Without these updates, the repository cannot fully utilize the upstream features provided by Boomtick.

# Goal
1. Update all references to Boomtick composite actions in `.github/workflows/` to point to the `@main` branch.
2. Initialize and configure `.agent-context.json` properly in the repository root.
3. Ensure `project_config.json` declares base parameters to satisfy the CLI parser.
4. Update `pnpm` version requirements to `10.28.2`.

# Non-Goals
* Upgrading other third-party GitHub Actions (e.g., `actions/checkout`).
* Modifying the internal logic of the workflow files beyond action references.

# Proposed Approach
1. **Update Workflows:** Perform a search-and-replace across all YAML files in `.github/workflows/` to replace `uses: arii/boomtick/.github/actions/...@605eebb56880a5ab47330f1e1eb2f9b9bbb4fd92` with `@main`.
2. **Setup Runtime & Environment:**
   - Update `pnpm-workspace.yaml` or `package.json` to ensure `pnpm` version `10.28.2` is configured.
   - Run `pnpm run agent:prime` (or invoke `td-cli context-warm`) to generate an initial `.agent-context.json`.
   - Ensure a `project_config.json` exists containing valid properties like `"github_repo": "arii/tech-dancer"`.

# Alternatives Considered
* **Keeping the pinned commit hashes:** Rejected because it causes configuration drift and requires manual updates every time Boomtick releases a critical fix.

# Architectural Impact
Aligns the repository with the "Zero-Submodule Integration" pattern while ensuring the required CLI configurations and contract tools have the correct versions.

# Scope
* Affected files:
  * All `.github/workflows/*.yml` (updating commit hash to `@main`).
  * `project_config.json` (creating/updating).
  * `package.json` / `pnpm-workspace.yaml` (updating pnpm version).
  * `.agent-context.json` (running initialization).

# Validation Steps
* All Boomtick action references use `@main`.
* `project_config.json` contains required fields.
* `pnpm` is explicitly pinned to `10.28.2`.
* `.agent-context.json` exists or can be properly generated using `pnpm run agent:prime`.
* Validate that GitHub Actions pass in the repository.

---
**Files modified in this issue:**
.github/workflows/agent-orchestrator.yml
.github/workflows/chatops-trigger.yml
.github/workflows/ci.yml
.github/workflows/release.yml
.github/workflows/smoke-test-impact-analysis.yml
