# Developer Onboarding, Workflows, and Codebase Context Guide

Welcome to the `arii/boomtick` repository! This document serves as the comprehensive developer onboarding guide, clarifying the codebase context, setup workflows, and collaboration strategies for both human developers and autonomous agents.

## Problem Statement

As `arii/boomtick` decouples into a standalone repository, new developers need clear context, structural expectations, and step-by-step setup guides.
Unlike the parent repository `arii/tech-dancer` (which is a Vite-based single-page React application), `arii/boomtick` operates as a decoupled Python CLI (`td-cli`) + Node/TypeScript Model Context Protocol (MCP) Server.
Developers need explicit instructions on workspace-level tool syncing, contract verification, and runtime expectations to ensure parity and prevent divergence between CLI and MCP models.

## Goal

- Establish a single source of truth for onboarding new developers to the decoupled repository.
- Clarify runtime expectations, repository parity, local execution workflows, contract syncing, and collaboration/branching policies.

## Non-Goals

- Documenting Vite React application components or UI styling details (which reside strictly in `arii/tech-dancer`).
- Detailing remote production deployment hosting or cloud infrastructure provisioning.

## Proposed Approach

This onboarding guide is structured into three primary sections: **Codebase Context & Parity**, **Setup & Run Workflows**, and **Collaboration & Branching Strategy**.

---

### 1. Codebase Context & Parity

#### Architectural Differences from the Parent Repository
`arii/boomtick` is a decoupled Python CLI (`td-cli` under `cli/`) and Node/TypeScript MCP Server (`mcp/`). This is highly distinct from the parent repository, `arii/tech-dancer`, which is a Vite-based single-page React application. While `tech-dancer` focuses on interactive visual UI, `boomtick` provides backend services, RAG-backed PR reviews, autonomous agent tooling, and validation workflows.

#### The Role of `project_config.json`
`project_config.json` is located at the root of the repository and declares base parameters (such as `github_repo`, `vite_base_path`, and model configuration overrides). This file satisfies parser and CLI configuration dependencies, allowing CLI subcommands to execute with deterministic defaults without needing manual parameters passed.

#### Runtime & Version Expectations
The repository enforces strict environment constraints to maintain environment parity:
- **Node.js**: `v24.16.0` (or `24.x`, matching `.node-version` or `engines` in `package.json`).
- **pnpm**: `v10.28.2` (enforced via `packageManager` in `package.json`).
- **Python**: `python3` (typically configured via `.venv/bin/python3` or the system Python interpreter).

---

### 2. Setup & Run Workflows

Follow these step-by-step instructions to get the environment fully running locally.

#### Step 1: Checkout the Standalone Repository
Clone the repository to your local workspace:
```bash
git clone https://github.com/arii/boomtick.git
cd boomtick
```

#### Step 2: Bootstrap/Initialize the Environment
Run the root setup script to bootstrap the system dependencies, node modules, and virtual environments:
```bash
./setup-agent.sh
```
This script handles the installation of system tools, Node.js packages, Python virtual environments, Playwright, remote origin configuration, and git hooks.

#### Step 3: Rebuilding TypeScript Schemas & Contract Syncing
To prevent type drift between the Python models and TypeScript MCP schemas, `boomtick` uses an automated validation pipeline. Run the following command at the repository root:
```bash
pnpm run verify:schemas
```
This executes `scripts/verify-schemas.mjs`, which orchestrates:
1. Identifying the correct Python interpreter (preferring `.venv/bin/python3`).
2. Generating the CLI schema (`cli/dev_tools/cli-schema.json`) from the Python models via `cli/dev_tools/schema_gen.py`.
3. Synchronizing TypeScript contracts inside the MCP package (`pnpm --filter @arii/boomtick-mcp sync-contracts`).
4. Rebuilding and synchronizing MCP schemas (`pnpm --filter @arii/boomtick-mcp sync:mcp-schemas`).

To build the MCP server manually:
```bash
pnpm --filter @arii/boomtick-mcp run build
```

#### Step 4: Running Tests Locally
To verify the TypeScript codebase and check for regressions, run the MCP package unit tests:
```bash
pnpm --filter @arii/boomtick-mcp run test
```
To run Python CLI unit tests, use:
```bash
PYTHONPATH=cli pytest cli/tests
```

#### Step 5: Activating the MCP Server Locally
You can start the MCP server using standard I/O:
```bash
# Directly with Node
node mcp/dist/index.js

# Or via the helper script
./mcp/start_browsermcp.sh
```

To configure Claude Desktop or another MCP client to use the server locally, add the following to its configuration file:
```json
{
  "mcpServers": {
    "boomtick": {
      "command": "node",
      "args": ["/absolute/path/to/boomtick/mcp/dist/index.js"],
      "env": {
        "GITHUB_TOKEN": "your_pat",
        "GITHUB_OWNER": "your_org",
        "GITHUB_REPO": "your_repo",
        "BOOMTICK_REPO_PATH": "/absolute/path/to/boomtick"
      }
    }
  }
}
```

---

### 3. Collaboration & Branching Strategy

#### Branch Protection & PR Rules
- **No Direct Pushing**: Direct pushing to `main` is strictly forbidden. All updates must be made via feature/bugfix branches.
- **Pull Request Reviews**: All code modifications must undergo standard Pull Request reviews and obtain necessary approvals before merging.
- **Squash & Rebase Merges**: Commits should be consolidated into a single clean squash or rebase commit upon merging to keep the history readable.
- **Conventional Commits**: Commit messages and PR titles must follow the Conventional Commits specification (e.g., `feat: ...`, `fix: ...`, `docs: ...`).

#### Coordinating Multi-Repository / Submodule Changes
`arii/boomtick` is embedded as a git submodule in the parent repository `arii/tech-dancer` (at path `mcp/` or `boomtick-pkg/`). When a task spans both repositories, coordinate changes as follows:
1. **Develop First in Boomtick**: Make all CLI, MCP tool, or RAG pipeline changes directly in `arii/boomtick`. Open a PR, verify it against the test suite, obtain review, and merge to `main`.
2. **Commit Submodule Update in Parent**: Once the submodule changes are merged into `boomtick`'s `main` branch, navigate to your local `arii/tech-dancer` workspace.
3. **Update Reference**: Pull the latest commit from `boomtick` and update the submodule reference:
   ```bash
   git submodule update --remote <submodule-path>
   ```
4. **Test and PR in Parent**: Run any downstream tests in `tech-dancer` (such as integration/e2e/visual tests) to ensure compatibility with the updated submodule. Open a PR in `tech-dancer` representing the submodule bump.
5. **Merge Parent PR**: Once verified, merge the parent PR.

---

## Alternatives Considered

- **Monolithic Repository**: Keeping all CLI and MCP code inside the `tech-dancer` parent codebase. *Rejected* to enable independent release cycles, package publication (npm / future PyPI), and reuse in separate agent environments.
- **Manual Schema Synchronization**: Manually copying types and schemas across Python and TypeScript codebases. *Rejected* because it introduces a significant risk of contract and API schema drift. The automated validation pipeline is much safer and more reliable.

## Architectural Impact

- Ensures developer parity and streamlined local setups across both human and agent contributors.
- Enforces an automated model-to-schema-to-contract pipeline, guaranteeing zero schema drift between Python CLI and TypeScript MCP server components.
- Standardizes cross-repository coordination, keeping parent-submodule dependencies highly organized and predictable.

## Scope

This document applies to all developers, contributors, and autonomous agent systems operating within the `arii/boomtick` repository.

## DEFINITION OF DONE

1. **Onboarding Guide Created**: `docs/onboarding.md` is written and correctly structured without internal AI planning headers.
2. **Documentation Index Registered**: `README.md` successfully links to `docs/onboarding.md`.
3. **No Drift / Regressions**: Schema/contract validation runs perfectly and workspace tests pass cleanly.
