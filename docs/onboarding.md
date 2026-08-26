# Repository Onboarding, Workflows, and Integration Guide

Welcome to the `arii/boomtick` repository! This document serves as the single source of truth for onboarding developers and integrating `boomtick` using the **Zero-Submodule Strategy** into downstream consumer repositories (such as `arii/portfolio` or `arii/tech-dancer`).

---

## Onboarding Checklist

Use this checklist to ensure all prerequisites and configuration steps are complete when setting up Boomtick in a new repository:

- [ ] **Initialize Context Index**: Create `.agent-context.json` in your repository root to establish the workspace index.
- [ ] **Create Repository Configuration**: Add `project_config.json` at your repository root with `github_repo` and AI review model chain configurations.
- [ ] **Configure GitHub Secrets**: Set up required repository secrets:
  - `JULES_API_KEY`: Required for automated self-repair sessions and orchestrator integration.
  - `GEMINI_API_KEY`: Required for multi-modal code review and vision pipelines.
  - `GITHUB_TOKEN` (or GitHub App Token `APP_ID` / `APP_PRIVATE_KEY`): For repository-scoped actions.
- [ ] **Install Integration Paradigm**: Select and set up PyPI package (`pip install boomtick`), Docker container (`ghcr.io/arii/boomtick`), or npm MCP package (`@arii/boomtick-mcp`).
- [ ] **Integrate GitHub Composite Actions**: Reference Boomtick composite actions (such as `setup-workspace`, `chatops`, `ai-review`, and `impact-analysis`) in your `.github/workflows/`.
- [ ] **Verify Local Setup & Schemas**: Test CLI commands or MCP tools locally and run schema contract synchronization (`pnpm run verify:schemas` if developing locally).

---

## Problem Statement

To enable rapid deployment of autonomous agent tooling, low-latency AI-driven PR reviews, and automated verification suites across multiple projects, developers need a streamlined way to integrate `boomtick`.
Coupling downstream repositories via Git submodules introduces deep filesystem dependencies, complex tree synchronizations, and fragile CI builds. A decoupled, zero-submodule approach using standalone packages, Docker containers, and composite GitHub Actions is required.

## Goal

- Provide a step-by-step blueprint for incorporating `boomtick` into downstream repositories via package managers, Docker containers, and composite actions.
- Document setup procedures, local run commands, and workspace contract synchronization patterns.
- Outline workflow integration and secret configuration to maintain consistent operational automation.
- Define branching, PR, and collaboration rules to maintain repository hygiene.

## Non-Goals

- Detailing the business logic of specific parent applications.
- Documenting remote server hosting provisioning.

## Proposed Approach

This guide details the integration lifecycle of `boomtick` in four operational stages: **Zero-Submodule Integration Paradigms**, **GitHub Actions Integration**, **Local Run & MCP Workflows**, and **Collaboration & Branching Strategy**.

---

### Zero-Submodule Strategy

Downstream consumer repositories integrate Boomtick's powerful automation capabilities **without** initializing it as a git submodule. Boomtick is consumed as a standalone PyPI package, a Docker container image, an npm MCP package, or via GitHub composite actions. This decouples your workflows from direct filesystem dependency trees, speeding up CI pipelines and eliminating submodule overhead.

#### 1. PyPI Package (`boomtick`)

The Python CLI developer tool (`td-cli`) and automation utilities are available directly via PyPI.

```bash
# Standard pip installation
pip install boomtick

# Fast installation with uv
uv pip install boomtick
```

Verify installation:
```bash
td-cli --help
```

#### 2. Docker Container (`ghcr.io/arii/boomtick`)

For containerized environments, CI runners, or isolated execution, Boomtick provides official OCI container images hosted on GitHub Container Registry.

```bash
# Pull the latest image
docker pull ghcr.io/arii/boomtick:latest

# Run interactive CLI command inside container
docker run --rm -it -v $(pwd):/app -e GITHUB_TOKEN=$GITHUB_TOKEN ghcr.io/arii/boomtick:latest td-cli --help
```

Commit-tagged images are also available for reproducible builds (e.g. `ghcr.io/arii/boomtick:sha-<commit_sha>`).

#### 3. MCP Server via npm (`@arii/boomtick-mcp`)

The Model Context Protocol (MCP) server enables AI agent environments (such as Claude Desktop or IDE extensions) to interact with Boomtick capabilities.

```bash
# Global installation using npm or pnpm
npm install -g @arii/boomtick-mcp
# or
pnpm add -g @arii/boomtick-mcp

# Execute directly via npx / pnpm dlx
npx @arii/boomtick-mcp
```

---

### 1. Repository Configuration & Setup

Every downstream repository consuming `boomtick` requires workspace configuration files at its root.

#### Step 1: Create `project_config.json`
Add `project_config.json` to declare base parameters for `td-cli` and AI review model routing:

```json
{
  "github_repo": "your-org/your-repo",
  "vite_base_path": "/",
  "triage_chain": {
    "primary": "gpt-4o-mini",
    "fallbacks": ["gemini-1.5-flash"],
    "max_retries": 2
  },
  "code_review_chain": {
    "primary": "gpt-4o",
    "fallbacks": ["deepseek-r1", "llama-3.3-70b-instruct"],
    "max_retries": 3
  }
}
```

#### Step 2: Initialize `.agent-context.json`
Create `.agent-context.json` to index repository metadata and scope definitions for agent operations.

#### Step 3: Runtime Expectations
Any host repository running `boomtick` tools locally or in CI should align with:
- **Node.js**: `v24.x` (or `v20+`)
- **pnpm**: `v10.x`
- **Python**: `python 3.10+` (preferably with `uv` or standard venv)

---

### 2. GitHub Actions Integration

Instead of local script paths or submodules, reference Boomtick's composite actions directly in your repository's `.github/workflows/`:

#### Available Reusable Actions
Boomtick exposes the following Composite Actions under `arii/boomtick/.github/actions/` (or `mcp/actions/`):

1. **`setup-workspace`**: Installs Node, Python, and the `td-cli` developer tool natively onto the runner.
   ```yaml
   uses: arii/boomtick/.github/actions/setup-workspace@main # nosemgrep: yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag
   with:
     setup-node: 'true'
     setup-python: 'true'
   ```

2. **`chatops`**: Handles comment parsing and automatically dispatches appropriate workflow operations.
   ```yaml
   uses: arii/boomtick/.github/actions/chatops@main # nosemgrep: yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag
   with:
     comment_body: ${{ github.event.comment.body }}
     author_association: ${{ github.event.comment.author_association }}
     issue_number: ${{ github.event.issue.number }}
     github_token: ${{ secrets.GITHUB_TOKEN }}
   ```

3. **`ci-repair`**: Coordinates automated CI failure tracking and self-repair fix sessions.
   ```yaml
   uses: arii/boomtick/.github/actions/ci-repair@main # nosemgrep: yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag
   with:
     run_id: ${{ github.event.workflow_run.id }}
     run_url: ${{ github.event.workflow_run.html_url }}
     head_sha: ${{ github.event.workflow_run.head_sha }}
     head_branch: ${{ github.event.workflow_run.head_branch }}
     github_token: ${{ secrets.GITHUB_TOKEN }}
     jules_api_key: ${{ secrets.JULES_API_KEY }}
   ```

4. **`ai-review`**: Runs AI review audits on pull requests.
   ```yaml
   uses: arii/boomtick/.github/actions/ai-review@main # nosemgrep: yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag
   with:
     pr_number: ${{ inputs.pr_number }}
   ```

5. **`impact-analysis`**: Performs blast-radius checks and posts review summaries.
   ```yaml
   uses: arii/boomtick/.github/actions/impact-analysis@main # nosemgrep: yaml.github-actions.security.github-actions-mutable-action-tag.github-actions-mutable-action-tag
   with:
     github_token: ${{ secrets.GITHUB_TOKEN }}
     gemini_api_key: ${{ secrets.GEMINI_API_KEY }}
   ```

#### GitHub Secrets Configuration
Configure the following Secrets in your repository settings:
- `JULES_API_KEY`: Communicates with the Jules session orchestrator.
- `GEMINI_API_KEY`: Enables multi-modal vision and code review pipelines.
- `GITHUB_TOKEN` or GitHub App Token (`APP_ID` & `APP_PRIVATE_KEY`): Passed as `github_token` input to composite actions.

---

### 3. Local Run & Verification Workflows

#### Schema & Contract Synchronization
To keep TypeScript MCP schemas and Python CLI models in sync during local development, run:
```bash
pnpm run verify:schemas
```
This triggers `scripts/verify-schemas.mjs`, which generates CLI schemas from Python models and updates TypeScript MCP contracts.

#### Running Tests Locally
- TypeScript / MCP unit tests:
  ```bash
  pnpm --filter @arii/boomtick-mcp run test
  ```
- Python CLI unit tests:
  ```bash
  pnpm run test:python
  # or
  PYTHONPATH=cli pytest cli/tests
  ```

#### Activating the MCP Server Locally
To connect Claude Desktop or another client to the local MCP server:
```json
{
  "mcpServers": {
    "boomtick": {
      "command": "npx",
      "args": ["-y", "@arii/boomtick-mcp"],
      "env": {
        "GITHUB_TOKEN": "your_github_token",
        "GITHUB_OWNER": "your_org",
        "GITHUB_REPO": "your-repo"
      }
    }
  }
}
```

---

### 4. Collaboration & Branching Strategy

To maintain a clean history and prevent breaking changes across repositories, adhere to standard collaboration rules:

- **No Direct Push to Main**: All changes must be delivered via Pull Requests from feature branches.
- **Squash & Rebase Merges**: Maintain a linear git history.
- **Conventional Commits**: Commit messages must adhere to [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat:`, `fix:`, `docs:`, `chore:`) to ensure release automation functions properly.
- **Independent Package Updates**: Downstream repositories bump Boomtick PyPI/Docker/npm package tags independently, eliminating tightly-coupled git submodule pointer updates.

---

## Alternatives Considered

- **Maintaining Submodule Integration**: Keeping git submodules as a legacy integration mode. *Rejected* because submodules create deep filesystem dependencies, fragile CI checkouts, and pointer sync friction across downstream repositories.
- **Separate Quickstart File**: Creating a `docs/quickstart.md` document. *Rejected* because centralizing documentation in `docs/onboarding.md` avoids duplication and documentation fragmentation.

## Architectural Impact

- **Zero-Submodule Integration**: Repositories consume Boomtick as standard PyPI packages, Docker containers, npm packages, or GitHub composite actions.
- **Zero-Drift Contracts**: Unified Python-to-TypeScript contract validation without filesystem coupling.
- **Low-Overhead Maintenance**: Downstream consumer repositories stay clean and focused on their own application logic.

## Scope

This onboarding and integration guide applies to all downstream consumer repositories, developers, and autonomous systems integrating `boomtick`.

## DEFINITION OF DONE

1. `docs/onboarding.md` is updated to remove submodule instructions.
2. `docs/onboarding.md` includes instructions for PyPI (`pip install boomtick`), Docker (`ghcr.io/arii/boomtick`), and MCP package usage (`@arii/boomtick-mcp`).
3. A clear "Onboarding Checklist" is present in the guide.
4. The issue successfully validates against `td-cli gh validate-issue`.
