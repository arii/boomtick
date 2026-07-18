---
title: "Consolidate CI Failure Issues by PR Number Instead of Commit SHA"
---

# Problem Statement
Currently, the `CI Repair` workflow (`.github/workflows/ci-repair.yml`) generates a new GitHub issue for CI failures based on the commit SHA. When multiple commits are pushed to the same pull request, or when multiple CI runs fail for the same PR (e.g. from different jobs like `Deployment Impact Analysis`), this creates an excessive number of issues. This clutters the issue space, making it difficult to track and manage failures associated with a specific PR.

# Goal
Modify the `CI Repair` workflow and associated issue tracking logic to group CI failures by Pull Request number rather than commit SHA for non-main branch failures. We want one open issue per PR that accumulates CI failure information, rather than creating new issues for every failing commit or job.

# Non-Goals
*   Changing the issue creation logic for failures on the `main` branch. Since `main` commits don't naturally belong to an open PR in the same way, tracking by SHA (or a single rolling issue) is still acceptable.
*   Modifying the logic for dispatching Jules sessions on `main` branch failures.
*   Modifying the actual CI workflows themselves (only the failure tracking logic in `ci-repair.yml`).

# Proposed Approach
1.  **Extract PR Number:** In the `Collect Failure Context` step of `.github/workflows/ci-repair.yml`, we need to determine the PR number associated with the `HEAD_SHA` or `HEAD_BRANCH`. The GitHub Actions `workflow_run` event payload contains information about pull requests (`github.event.workflow_run.pull_requests`). We will extract the PR number from this array.
2.  **Modify Idempotency Check:**
    *   **For PR branches:** Change the search criteria in the `Idempotency Check` step. Instead of searching for an issue containing the `SHA`, search for an open issue with the label `ci-failure` that is linked to the extracted PR number (e.g., using a tag in the issue body like `<!-- PR_NUMBER: <number> -->` or searching for the PR number directly). Alternatively, if the PR number is appended to the issue title, search by title. Let's use a hidden HTML comment tag in the issue body for reliable matching: `<!-- ci-failure-pr:<pr_number> -->`.
    *   **For main branch:** Keep the existing logic (search by `SHA` and `main-ci-failure` label).
3.  **Modify Issue Creation/Update Logic:**
    *   **If an issue exists for the PR:** Instead of doing nothing, append the new failure information (new `RUN_ID`, `SHA`, and `failing_jobs`) as a comment to the existing issue.
    *   **If no issue exists:** Create a new issue. For PRs, include the PR number in the title (e.g., `fix(ci): CI failure for PR #<pr_number>`) and add the hidden tag `<!-- ci-failure-pr:<pr_number> -->` in the body.
4.  **Handle missing PRs:** If a workflow runs on a branch that doesn't have an open PR yet, fallback to the existing SHA-based tracking or track by branch name until a PR is opened. (Tracking by branch name `<!-- ci-failure-branch:<branch_name> -->` is a good fallback).

# Alternatives Considered
*   **Creating PR Comments instead of Issues:** Instead of creating issues, we could post the failures directly as comments on the failing PR. *Rejected:* The current architecture uses issues to dispatch Jules sessions via `td-cli jules fix-ci --issue-number <ISSUE_NUMBER>`. Changing this to work off PR comments would require significant changes to the `td-cli` agent dispatch logic. Keeping them as issues maintains compatibility with the existing `fix-ci` command while reducing clutter.
*   **Deleting old issues when new ones are created for the same PR:** *Rejected:* We lose the history of previous failures and runs. Consolidating into one issue is better for tracking.

# Architectural Impact
This change reduces the noise in the GitHub Issues tracker by consolidating CI failure reports. It makes the system more manageable for human developers and maintains the existing contract for the Jules `fix-ci` agent.

# Scope
*   Modification of `.github/workflows/ci-repair.yml`.
*   Specifically, updating the `Collect Failure Context`, `Idempotency Check`, and `Create Issue` steps to handle PR-based tracking and issue updating (commenting).

# Dependencies and Sequencing
*   No external dependencies.
*   This should be implemented prior to adding more automated CI analysis tools that could exacerbate the issue spam.

# Risks and Edge Cases
*   **Multiple jobs failing simultaneously:** If two failing jobs trigger the `workflow_run` event almost concurrently, there might be a race condition during issue creation, potentially resulting in two issues for the same PR. We may need to ensure the idempotency check is robust or tolerate occasional duplicates.
*   **Forks:** Ensure that PRs originating from forks still have their `PR_NUMBER` correctly extracted from the `workflow_run` event payload.
*   **Missing PR Number:** If the workflow is run on a detached head or a branch without a PR, the `pull_requests` array might be empty. The fallback to branch-name tracking must work seamlessly.

# Accessibility Implications
*   None. This is an internal CI workflow change.

# Responsive Behavior
*   None.

# Design System Implications
*   None.

# Testing Strategy
*   **Unit/Integration:** Mock the GitHub Actions `workflow_run` event payloads for different scenarios:
    *   PR branch with no existing issue.
    *   PR branch with an existing issue.
    *   `main` branch.
    *   Branch without an open PR.
*   Verify that the correct `gh` CLI commands (`issue create` vs `issue comment`) are generated in each scenario.

# Documentation Updates
*   Update any developer onboarding guides or workflow documentation that explains how CI failures are tracked and triaged.

# Acceptance Criteria
*   When a CI workflow fails for a pull request, a single issue is created with the label `ci-failure`.
*   The issue title includes the PR number (e.g., `fix(ci): CI failure for PR #123`).
*   The issue body contains a hidden identifier tag (e.g., `<!-- ci-failure-pr:123 -->`).
*   If a subsequent CI failure occurs for the same PR, a new comment is appended to the existing issue instead of creating a new issue.
*   The comment includes the new `RUN_ID`, `SHA`, and the names of the failing jobs.
*   Failures on the `main` branch continue to be tracked by `SHA` and create a single issue per failure.
*   Jules `fix-ci` dispatch continues to work for the consolidated PR issues.

# Validation Steps
1.  Create a test branch and open a PR.
2.  Push a commit that intentionally fails a CI job.
3.  Verify that a new issue is created for the PR failure.
4.  Push a second commit to the same PR that also fails a CI job.
5.  Verify that no new issue is created, and instead, a comment is added to the first issue.
6.  Push a commit to `main` that intentionally fails CI.
7.  Verify that a new issue is created tracking the `SHA` for the `main` branch failure.

# UNDERSTAND THE ISSUE
The core problem is issue spam caused by a one-to-one mapping between CI workflow failure runs (which happen per-commit or per-re-run) and GitHub Issues. We need a many-to-one mapping where multiple failures on a single PR map to a single tracking issue.

# DETERMINE APPROACH
1. Analyze the `github.event.workflow_run` payload structure to reliably extract the `pull_requests[].number`.
2. Implement a robust search strategy to find existing issues for that PR. A hidden HTML comment tag is the most resilient approach.
3. Use the `gh` CLI to either `issue create` or `issue comment` based on the search results.

# SPECIFY SCOPE
The required changes are entirely contained within the `.github/workflows/ci-repair.yml` file. No changes to application code, CLI tools, or MCP server are necessary.

# DEFINITION OF DONE
*   When multiple CI failures occur for the same pull request, only one GitHub Issue is created.
*   Subsequent failures for that PR append comments to the existing issue with the new `RUN_ID`, `SHA`, and failing jobs.
*   The title of the issue clearly identifies the associated PR.
*   The `main` branch failure tracking continues to work as before (or is tracked sensibly per commit).
*   The Jules `fix-ci` dispatch mechanism still functions correctly for these consolidated issues.
