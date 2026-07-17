---
title: "Implement DevSecOps Branch Protection and Quality Gates"
---

# Problem Statement
Our default branch (`main`) is currently vulnerable to accidental deletions and non-fast-forward force pushes. Furthermore, our automated versioning tools (like `release-please`) require clean semantic commit histories to run correctly, and we need to guarantee that critical CI checks pass before any code is merged. Standard branch protections are insufficient as they often block automated bot workflows from operating autonomously.

# Goal
Implement a single, unified GitHub Repository Ruleset that prevents destructive actions on the default branch, enforces Conventional Commits metadata, mandates strict CI status checks, and correctly utilizes `bypass_actors` to allow automation apps (like `release-please`) to operate without developer-level restrictions.

# Non-Goals
*   Migrating away from our current CI/CD tools (GitHub Actions).
*   Enforcing rules on branches other than the default branch (`main`).
*   Modifying the actual CI workflows themselves (this issue only covers the ruleset gating).

# Proposed Approach
We will import a unified JSON ruleset schema in "Evaluate" mode initially. This ruleset will combine the "Branch Protection Best Practices" and "Require Pull Requests and Conventional Commits" recipes from the official `github/ruleset-recipes`.
Key configurations:
1.  **Branch Protection:** `deletion` and `non_fast_forward` prevention.
2.  **Metadata Restrictions:** `commit_message_pattern` matching Conventional Commits Regex.
3.  **Status Checks:** `required_status_checks` for `lint-typecheck`, `audit`, and `Deployment Impact Analysis`.
4.  **Bypass Actors:** Configure the Release Automation Bot (App ID) with `bypass_mode: always`.

# Alternatives Considered
*   **Legacy Branch Protection Rules:** Rejected because they do not support advanced metadata matching (like commit message regex) natively without third-party actions, and their bypass mechanisms are less granular for integrations.
*   **Pre-commit Hooks:** Rejected for enforcement because they run client-side and can be bypassed. We need server-side enforcement.

# Architectural Impact
This introduces a new governance layer at the repository level. It shifts validation left (to the PR merge attempt) rather than failing downstream during release processes. It relies on GitHub Apps for automated bypasses instead of standard PATs or standard `GITHUB_TOKEN`s.

# Scope
*   Creation of the `default-branch-ruleset.json` configuration.
*   Application of the ruleset to the repository in "Evaluate" mode.
*   Monitoring Rule Insights.
*   Transitioning the ruleset to "Active" mode after verification.

# UNDERSTAND THE ISSUE
The core challenge is balancing strict security/quality gates for human developers with the necessary autonomy for CI/CD bot integrations.

# DETERMINE APPROACH
The approach relies on GitHub's newer Rulesets feature, specifically leveraging the JSON import functionality and the `bypass_actors` array to solve the human-vs-bot conflict.

# SPECIFY SCOPE
The scope is limited to repository configuration (Settings > Rulesets). No application code or workflow YAML files will be modified, though a JSON backup of the ruleset should be committed to a `.github/rulesets/` directory for version control.

# DEFINITION OF DONE
*   Ruleset is active on the `~DEFAULT_BRANCH`.
*   Direct pushes and deletions are blocked.
*   PRs cannot be merged without a Conventional Commit message.
*   PRs cannot be merged unless required CI checks pass.
*   Automated bots (e.g., `release-please`) can successfully create and merge their PRs or push tags without being blocked by these rules.
