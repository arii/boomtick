# Repository Onboarding, Workflows, and Integration Guide

Welcome to the `arii/boomtick` repository! This document serves as the single source of truth for onboarding developers and integrating `boomtick` as a core dependency/submodule inside a new repository.

---

## Problem Statement

To enable rapid deployment of autonomous agent tooling, low-latency AI-driven PR reviews, and automated verification suites across multiple projects, developers need a streamlined way to integrate `boomtick` as a submodule or dependency.
Without clear onboarding and integration guidelines, new repositories risk API/schema drift, incorrect setup configurations, and misconfigured CI/CD workflows.

## Goal

- Provide a step-by-step blueprint for incorporating `boomtick` into a new parent repository.
- Document setup procedures, local run commands, and workspace contract synchronization patterns.
- Outline automated workflow setup using the `td-cli` tool to avoid manual configuration errors.
- Define branching, PR, and collaboration rules to maintain repository hygiene and coordinate submodule changes.

## Non-Goals

- Detailing the business logic of specific parent applications.
- Documenting remote server hosting provisioning.

## Proposed Approach

This guide details the integration lifecycle of `boomtick` in four operational stages: **Dependency & Submodule Integration**, **Automated Workflow Installation**, **Local Run/Verification Workflows**, and **Collaboration & Branching Strategy**.

---

### 1. Dependency & Submodule Integration

To include `boomtick` in a new repository (acting as the superproject), follow these initial integration steps:

#### Step 1: Add Boomtick as a Submodule
In your new repository's root, add `boomtick` as a Git submodule. We recommend placing it in a folder like `mcp/` or `boomtick/`:
```bash
git submodule add https://github.com/arii/boomtick.git mcp
git submodule update --init --recursive
```

#### Step 2: Configure `project_config.json`
Every repository consuming `boomtick` needs a `project_config.json` at its root. This file declares base parameters to satisfy the CLI parser and workspace dependencies:
```json
{
  "github_repo": "your-org/your-new-repo",
  "vite_base_path": "/your-base-path/",
  "code-review-chain": {
    "primary": "gpt-4o",
    "fallbacks": ["deepseek-r1", "llama-3.3-70b-instruct"],
    "max_retries": 3
  }
}
```

#### Step 3: Runtime Expectations
Any host repository running `boomtick` must align with the following runtime standards:
- **Node.js**: `v24.16.0` (or `24.x`)
- **pnpm**: `v10.28.2` (configured via `pnpm-workspace.yaml` or workspace `package.json`)
- **Python**: `python3` (typically managed inside a local virtual environment like `.venv`)

---

### 2. Automated Workflow Setup

`boomtick` includes an automated setup script to synchronize and copy the required AI/automation workflows from the submodule directly into your superproject's GitHub action workspace.

#### Step 1: Run local bootstrap
Navigate into your submodule and execute the setup script:
```bash
cd mcp # (or the directory where you added the submodule)
./setup-agent.sh
```

#### Step 2: Automatically Install Workflows
Run the `td-cli` workflow installation command. This command automatically copies the correct GitHub Actions workflows to your parent repository's `.github/workflows/` directory, while dynamically adjusting composite action paths to target the submodule folder name:
```bash
# Run with --execute to perform the installation (without it, it defaults to a dry-run)
td-cli agent install-workflows --execute
```

This command installs the following three essential workflows:
1. **`chatops-trigger.yml`**: Triggers autonomous agent reviews, feedback collection, and macro-agent operations on PR comments or events.
2. **`ci-repair.yml`**: Coordinates automated test verification and triggers Jules-led self-repair branches on CI failures.
3. **`issue-operations.yml`**: Executes issue specification parsing and manages downstream issue lifecycle hooks.

#### Step 3: Superproject secrets and Environment Configuration
To authorize the automation workflows, you must configure the following repository Secrets in your parent GitHub repository:
- `GITHUB_TOKEN` / `GH_PAT_SUBMODULE_UPDATE`: A personal access token or installation token with repository-scoped read/write permissions.
- `JULES_API_KEY`: Required to communicate with the Jules session orchestrator.
- `GEMINI_API_KEY`: Required to enable deep vision-based review pipelines.

---

### 3. Local Run & Verification Workflows

When working within a repository containing `boomtick`, follow these local workflows to verify code changes, synchronize contract models, and boot the local MCP server.

#### Schema & Contract Synchronization
To keep TypeScript tool schemas and Python CLI models in perfect parity without manual copy-pasting, `boomtick` features an automated validation pipeline. Run this command in the submodule directory:
```bash
pnpm run verify:schemas
```
This command triggers `scripts/verify-schemas.mjs`, which coordinates:
1. Identifying the correct local Python interpreter (preferring `.venv/bin/python3`).
2. Generating the CLI schema (`cli/dev_tools/cli-schema.json`) from the Python models via `cli/dev_tools/schema_gen.py`.
3. Synchronizing TypeScript contracts inside the MCP package (`pnpm --filter @arii/boomtick-mcp sync-contracts`).
4. Rebuilding and synchronizing the final MCP schemas (`pnpm --filter @arii/boomtick-mcp sync:mcp-schemas`).

#### Running Tests Locally
To verify the TypeScript MCP codebase, run the test suite:
```bash
pnpm --filter @arii/boomtick-mcp run test
```
To run Python CLI unit tests, run:
```bash
PYTHONPATH=cli pytest cli/tests
```

#### Activating the MCP Server Locally
You can activate and connect to the MCP server locally via standard I/O:
```bash
# Direct execution
node mcp/dist/index.js

# Or via the start script
./mcp/start_browsermcp.sh
```

To configure Claude Desktop or another MCP client to run the server on demand, insert this snippet in your client configuration:
```json
{
  "mcpServers": {
    "boomtick": {
      "command": "node",
      "args": ["/absolute/path/to/your-repo/mcp/dist/index.js"],
      "env": {
        "GITHUB_TOKEN": "your_github_token",
        "GITHUB_OWNER": "your_org",
        "GITHUB_REPO": "your-repo",
        "BOOMTICK_REPO_PATH": "/absolute/path/to/your-repo"
      }
    }
  }
}
```

---

### 4. Collaboration & Branching Strategy

To maintain a clean history and prevent breaking changes between host repositories and `boomtick`, adhere to the following collaboration standards.

#### Pull Request & Branching Rules
- **No Direct Push to Main**: All development must occur on separate branch names. Directly committing to the `main` branch is blocked.
- **Squash & Rebase Merges**: To preserve a linear history, Pull Requests must be merged using either Squash or Rebase merge strategies.
- **Approvals & Reviews**: Merging a Pull Request requires at least one review approval.
- **Conventional Commits**: Every commit message must adhere to the Conventional Commits specification (e.g., `feat:`, `fix:`, `docs:`, `chore:`).

#### Coordinating Submodule Changes
When a feature requires changes across both the `boomtick` submodule and its consuming parent (superproject) repository, follow this workflow to prevent broken dependencies and build failures:
1. **Develop First in Submodule**: Open a branch inside the `boomtick` subdirectory. Complete your CLI, MCP, or contract updates.
2. **Submit Submodule PR**: Open a Pull Request on the `arii/boomtick` repository. Complete reviews, ensure all tests pass, and merge the changes into `boomtick`'s `main` branch.
3. **Update Superproject Submodule Pointer**: Navigate to the parent repository root, fetch the latest submodule reference, and commit the pointer update:
   ```bash
   # Pull latest submodule main
   git submodule update --remote --recursive

   # Add the updated pointer change to git
   git add mcp # (or the submodule folder name)
   git commit -m "chore: bump boomtick submodule pointer to main"
   ```
4. **Submit Superproject PR**: Open a corresponding Pull Request in the superproject repository. Verify downstream integration tests (such as end-to-end or visual regression tests) before merging.

---

## Alternatives Considered

- **Manual Workflow Copy-Pasting**: Requiring host repos to manually copy YAML workflows and change all paths by hand. *Rejected* because it is extremely error-prone and leads to configuration drift during updates.
- **Publishing as a Private npm/pip Dependency Only**: Distributing components solely via package managers. *Rejected* because local repository actions require tight access to worktrees, local filesystems, and custom git hook integration which is best done via submodules.

## Architectural Impact

- **Zero-Drift Contracts**: Ensures unified Python-to-TypeScript contract validation across any repository consuming `boomtick`.
- **Streamlined Workflow Maintenance**: Superprojects can update workflow files instantly by fetching submodule updates and re-running `td-cli agent install-workflows --execute`.
- **Low-overhead Integration**: Host projects need minimal setup, remaining focused on their own domain logic.

## Scope

This onboarding and integration guide is applicable to any human developer, repository owner, or autonomous system integrating `boomtick` as a dependency.

## DEFINITION OF DONE

1. **Integration Guide Created**: `docs/onboarding.md` is updated with generic, reusable instructions for host repository dependency integration and automated workflow installations.
2. **References Synced**: `README.md` correctly points to the updated onboarding guide.
3. **Validation Passes**: Schema synchronization pipeline and unit tests run successfully.
