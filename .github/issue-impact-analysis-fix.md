# Problem Statement
The `impact-analysis` composite action `.github/actions/impact-analysis/action.yml` fails to send analysis results back to Jules on downstream integration repositories (like `tech-dancer`) when triggered by `push` events instead of `pull_request` events. This occurs because steps `parse_jules` (`Parse Jules session ID from PR description`) and the notification step (`Send impact analysis to Jules session`) hardcode lookups to `github.event.pull_request.body` and `github.event.pull_request.number`. On a `push` event, these fields evaluate to empty strings, causing the Jules task ID extraction to silently exit (returning `exit 0` because `$TASK_ID` is empty) and skipping the Python dispatch step entirely.

# Goal
Refactor the parsing and notification steps in `.github/actions/impact-analysis/action.yml` to support non-`pull_request` trigger contexts by leveraging GitHub API (e.g. `gh pr view`) to dynamically fetch the PR body and number when standard event context variables are missing.

# Non-Goals
* Refactoring the internal mechanics of `send-jules-impact.py`.
* Altering the core visual diffing or code review logic of the action.

# Proposed Approach
Update `.github/actions/impact-analysis/action.yml`:
1. Use the pre-existing dynamically resolved `PR_NUMBER` (from `steps.resolve-pr.outputs.pr_number`) for the `Send impact analysis` step instead of `github.event.pull_request.number`.
2. In the `Parse Jules session ID` step, if `github.event.pull_request.body` is empty but `steps.resolve-pr.outputs.pr_number` is populated, use the `gh pr view` command to retrieve the PR body payload dynamically.

# Alternatives Considered
* Forcing downstream repositories to only use `pull_request` triggers for CI, but this breaks our standard "run on all branches" configuration (`branches: ["**"]`).
* Modifying `td-cli` to handle context parsing internally. Rejected because the shell script is responsible for extracting configuration variables before launching Docker/Python scripts.

# Architectural Impact
This improves portability of the composite action across different GitHub action event triggers, aligning with our Zero-Submodule Strategy for downstream CI orchestration.

# Scope
* Affected File: `.github/actions/impact-analysis/action.yml`.
* Update step `Parse Jules session ID from PR description` (lines ~101-114).
* Update step `Send impact analysis to Jules session` (lines ~116-124).

# UNDERSTAND THE ISSUE
Downstream repositories like `tech-dancer` trigger CI on `push` to provide real-time impact analysis, but the reporting step expects PR webhook context. We already have a `Resolve PR Number` step (`id: resolve-pr`) that safely determines PR context, but the final steps don't utilize its `pr_number` output.

# DETERMINE APPROACH
The solution is to substitute hardcoded event payloads with the dynamic variables already resolved by the action itself, adding a small `gh` CLI fallback for the PR body text.

# SPECIFY SCOPE
* Modify `.github/actions/impact-analysis/action.yml`.
* Motivation: Fix lack of AI impact analysis messages on push events.
* Affected components: `impact-analysis` composite action.
* Dependencies and sequencing: Must execute after `Resolve PR Number`. Requires `GITHUB_TOKEN` to use `gh pr view`.
* Risks and edge cases: PR body extraction using `gh` might fail if token lacks permissions, but the action already requires a valid token.
* Accessibility implications: None.
* Responsive behavior: None.
* Design system implications: None.
* Testing strategy: CI testing on a draft PR mimicking a `push` trigger.
* Documentation updates: None required.
* Acceptance criteria: The `TASK_ID` is parsed successfully and the message is sent even on `push` triggers.
* Validation steps: Validate the action runs correctly by looking for the "Found Jules task ID" stdout during a simulated test run.

# DEFINITION OF DONE
* The `action.yml` file is updated to use dynamic variable resolution for PR properties.
* Both `pull_request` and `push` triggers correctly extract the `TASK_ID` from the PR body (if one exists).
