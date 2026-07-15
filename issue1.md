# Problem Statement
The `.github/workflows/` directory contains numerous fragmented workflows related to issue and comment handling (`ai-chatops.yml`, `issue-comment-dispatcher.yml`, `issue_to_pr.yml`, `validate_issue.yml`). This fragmentation clutters the GitHub Actions sidebar and makes maintaining the issue-operations architecture difficult. GitHub treats pull request comments as issue comments, allowing these to be consolidated.

# Goal
Combine all issue- and PR-comment-triggered automations into a single, cohesive workflow (`issue-operations.yml`) to reduce UI clutter and simplify maintenance.

# Non-Goals
- We will not modify the underlying logic of the individual scripts (`ai-chatops`, `issue_to_pr`, etc.), only how they are triggered.
- We will not consolidate CI or release workflows in this specific issue.

# Proposed Approach
1. Create `.github/workflows/issue-operations.yml`.
2. Configure it to trigger `on: issues` (types: opened, edited) and `on: issue_comment` (types: created).
3. Migrate the `validate-quality` job from `validate_issue.yml`, configuring it to run `if: github.event_name == 'issues'`.
4. Migrate the chatops parsing logic from `issue-comment-dispatcher.yml` and `ai-chatops.yml` into a unified `chatops-dispatcher` job that runs `if: github.event_name == 'issue_comment'`.
5. Migrate the `create-pr` job from `issue_to_pr.yml`.
6. Delete the old workflows (`ai-chatops.yml`, `issue-comment-dispatcher.yml`, `issue_to_pr.yml`, `validate_issue.yml`).

# Alternatives Considered
- Keep them separate: Rejected because it leaves the GitHub Actions sidebar cluttered with 14+ top-level entries.
- Grouping by tool instead of event: Rejected because GitHub Actions triggers are event-based; grouping by event reduces redundant checkout and setup steps.

# Architectural Impact
This significantly cleans up the GitHub Actions UI sidebar, leaving only a few core entry points (CI, Issue Operations, Release Orchestrator). It simplifies the permissions and environment setup for issue-related tasks by centralizing them.

# Scope
This issue is limited to consolidating the following files into `.github/workflows/issue-operations.yml`:

# SPECIFY SCOPE
This issue is limited to consolidating the following files into `.github/workflows/issue-operations.yml`:
- `ai-chatops.yml`
- `issue-comment-dispatcher.yml`
- `issue_to_pr.yml`
- `validate_issue.yml`

# DEFINITION OF DONE
- `issue-operations.yml` is created and correctly triggers on issues and issue comments.
- The 4 legacy workflow files are deleted.
- ChatOps functionality is verified in a PR comment.

# UNDERSTAND THE ISSUE
- Verify the current `.github/workflows/` directory to locate the files targeted for consolidation.
- Analyze the `on:` triggers and permissions in each file to ensure the unified workflow inherits all necessary scopes.

# DETERMINE APPROACH
- Map out the conditional `if:` statements required to ensure jobs only run on their specific event types (e.g., `github.event_name == 'issues'` vs `github.event_name == 'issue_comment'`).
- Draft the unified YAML structure and test it locally or on a branch before merging.