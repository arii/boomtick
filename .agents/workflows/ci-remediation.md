# CI Pipeline Remediation Agent Workflow

# Problem Statement

Developers and automated agents currently spend significant manual effort investigating and resolving CI pipeline failures. While localized repair tools like the `td-cli agent repair` command exist for local developer usage, there is no standardized, comprehensive agentic workflow documented in `.agents/workflows/` that formally defines how an autonomous agent should handle CI failure triage, root-cause analysis, and automated remediation within the Boomtick architecture. Without a clear workflow, agents lack a structured protocol to autonomously setup their environment, fetch logs, isolate root causes, execute targeted remediation, validate their changes, and push resolutions.

# Goal

Define and specify a fully standardized agentic workflow document at `.agents/workflows/ci-remediation.md`. This document will serve as the core prompt and instruction set for an autonomous agent (like Jules or other LLM-driven agents) to independently and reliably handle CI failure remediation. The agent must fetch failing CI logs, analyze the root cause against recent commits, apply targeted minimal fixes, run the project's verification suite, and push the resolution to the repository.

# Non-Goals

- Modifying existing `td-cli` Python source code or adding new `td-cli` agent commands.
- Implementing or modifying the core agent execution engine itself.
- Covering generic bug fixes or feature requests unrelated to CI failures.

# Proposed Approach

The autonomous agent must follow a highly structured, multi-phase execution loop when dispatched to remediate a CI pipeline failure. The workflow is split into the following phases:

1. **Required Setup**: Ensure the environment is clean, activate the Python virtual environment, and run system checks to verify dependency alignment.
2. **Log Retrieval**: Fetch failing workflow logs from GitHub using standard tools or `gh` CLI commands to understand what failed.
3. **Root Cause Analysis (RCA)**: Map log failures back to files modified in recent commits to locate the source of regression.
4. **Remediation & Local Validation**: Execute targeted, minimal code modifications. Run local verification suites (`pnpm run test`, `pnpm run lint`, `pnpm run type-check`, `pytest cli/tests`) to ensure correctness.
5. **Safe Loop & Attempt Limit**: Enforce a strict maximum of 3 remediation attempts to prevent infinite execution loops.
6. **Submission**: Commit the changes using conventional commits and push them to the branch.

# Alternatives Considered

- **Expanding `review-pr.md`**: Considered expanding the existing PR review workflow to cover CI remediation. This was rejected because CI remediation is a distinct, highly complex operation that requires dedicated isolation, specific local testing environments, and retry-loop tracking. Combining them would bloat the context window of the review agent.
- **Using raw bash commands only**: Considered relying solely on raw bash commands instead of `td-cli` tools. This was rejected because the `td-cli` toolset (e.g. `td-cli doctor`) enforces critical environment, version, and dependency invariants that protect repository integrity.

# Architectural Impact

This workflow introduces a new standardized agent capability within `.agents/workflows/ci-remediation.md`, expanding the repository's suite of autonomous operations. It adheres to the existing pattern of markdown-based agent instructions and requires no changes to the core MCP server or CLI tooling. It increases agent autonomy and prevents pipeline failures from stalling developer progress.

# Scope

- **Creation of `.agents/workflows/ci-remediation.md`**: Fully document the remediation workflow and loop.
- **Environment and Log Context**: Detail exact steps for setup using `.venv` and retrieving logs.
- **Validation Guidelines**: Enforce standard workspace validation tools (`pnpm` tasks and `pytest`) to avoid broken PR states.
- **Edge Case Management**: Incorporate explicit rules for failure back-off, maximum retry limits, and human hand-off.

# UNDERSTAND THE ISSUE

When a CI run fails, the agent must treat the failing logs as its primary source of truth. It must not guess the cause or perform sweeping refactors. The agent must check:
- What exactly failed: Is it a linter error, a type-checking failure, a unit test, or an integration/E2E test?
- Where it failed: Which files, packages, or scripts are mentioned in the traceback?
- Why it failed: Did a recent commit introduce a typo, a missing import, a breaking API change, or an incompatible package version?

# DETERMINE APPROACH

The agent will execute the following concrete steps:

## Step 1: Environment Activation & Doctor Verification
The agent must initialize its sandbox environment exactly as follows:
- Activate the virtual environment:
  ```bash
  source .venv/bin/activate
  ```
- Run the doctor tool to verify that the CLI, Node, and pnpm versions are properly pinned and healthy:
  ```bash
  td-cli doctor
  ```

## Step 2: Log Retrieval
- The agent must retrieve the failing CI logs. If a Run ID is provided or can be resolved, it should use the GitHub CLI to view the failure:
  ```bash
  gh run view <RUN_ID> --log
  ```
- Alternatively, if running under a PR or commit context, fetch the latest check run logs using `td-cli` or `gh`:
  ```bash
  td-cli gh audit-pr <PR_NUMBER> --fetch
  ```
- Extract the failing lines or test traces. If the log is too large, the agent should search for keywords like `ERROR`, `FAIL`, `Vitest`, or `pytest`.

## Step 3: Analysis and Targeted Fixes
- Analyze the diff between the current branch and the base branch (e.g., `origin/main`) to locate the source of regression:
  ```bash
  git diff origin/main...HEAD
  ```
- Identify the exact files causing the failure.
- Formulate a minimal, highly targeted fix. Do not refactor unrelated code.
- Apply the fix directly to the source files. Do not modify build artifacts or auto-generated files.

## Step 4: Iterative Local Validation
- The agent must validate the fix locally before committing or pushing. Run the following checks:
  ```bash
  # Run linting and type-checking
  pnpm run lint
  pnpm run type-check

  # Run python test suite
  pytest cli/tests

  # Run typescript unit tests
  pnpm run test
  ```
- If any of these checks fail, the agent must treat the new errors as feedback, adjust its fix, and repeat Step 4.

## Step 5: Retry Limit and Back-off
- To prevent infinite loops, the agent must maintain an execution counter.
- **Limit**: The agent is allowed a maximum of **3 remediation attempts**.
- If after 3 attempts the local validation or CI still fails, the agent must stop, document its attempts, explain the remaining blocker, and hand off to a human developer.

## Step 6: Commit and Push (Submission)
- Once local validation passes, stage and commit the targeted changes using standard Conventional Commit messages:
  ```bash
  git add <modified_files>
  git commit -m "fix(ci): resolve CI pipeline failure in <component_or_test>"
  ```
- Push the commit back to the head branch:
  ```bash
  git push origin HEAD
  ```

# SPECIFY SCOPE

The remediation agent's scope is strictly bound to:
- Fixing the specific failures highlighted in the CI logs.
- Running standard project verification scripts.
- Pushing the minimal fix back to the head branch.
The agent must never introduce new dependencies, perform unrelated code cleanups, or modify architectural boundaries unless explicitly instructed by a developer.

# DEFINITION OF DONE

The CI Remediation Agent Workflow is considered complete and successful when all of the following acceptance criteria are fully met:

### Acceptance Criteria
- [ ] **Verification**: The file `.agents/workflows/ci-remediation.md` exists and contains all required spec-driven sections.
- [ ] **Setup Instructions**: The workflow explicitly mandates environment setup with `source .venv/bin/activate` and `td-cli doctor`.
- [ ] **Log Triage**: Detailed instructions are provided to retrieve CI logs using `gh` or `td-cli`.
- [ ] **Validation Protocol**: The workflow requires local validation using `pnpm run lint`, `pnpm run type-check`, `pnpm run test`, and `pytest cli/tests`.
- [ ] **Attempt Limit**: An explicit maximum limit of 3 tries is defined to prevent infinite agent loops.
- [ ] **No Regressions**: All existing CLI and workspace tests continue to pass perfectly.
- [ ] **Zero Findings**: Running `td-cli gh validate-issue --file .agents/workflows/ci-remediation.md` returns zero findings and zero warnings.

### Validation Steps
1. Verify that the `.agents/workflows/ci-remediation.md` file is present in the repository.
2. Run the validation tool to ensure the markdown structure conforms to the specifications:
   ```bash
   source .venv/bin/activate
   td-cli gh validate-issue --file .agents/workflows/ci-remediation.md
   ```
3. Run the complete workspace linting, type-checking, and testing suites to verify system integrity:
   ```bash
   pnpm run lint
   pnpm run type-check
   pnpm run test
   pytest cli/tests
   ```
