# Problem Statement
The repository currently has multiple workflows dedicated to CI repair and self-healing (`jules-fix-trigger.yml`, `main-ci-failure-repair.yml`, `self-healing.yml`), separated from the main `ci.yml` pipeline. This creates unnecessary top-level entries in the Actions sidebar and scatters CI logic across multiple files.

# Goal
Merge the "Self-Healing" and "Fix" tool workflows into jobs within the main `.github/workflows/ci.yml` file, triggering them via `workflow_run` when the primary CI build fails, or explicitly when summoned.

# Non-Goals
- We will not change the underlying Jules repair logic or CLI commands used for self-healing.
- We will not address release pipelines or issue chatops in this issue.

# Proposed Approach
1. Open `.github/workflows/ci.yml`.
2. Add a new job `self-healing` that triggers conditionally on failure.
3. Migrate the logic from `self-healing.yml` into this new job.
4. Migrate the logic from `main-ci-failure-repair.yml` into a dedicated job in `ci.yml`.
5. Integrate the `jules-fix-trigger.yml` manual dispatch logic appropriately.
6. Delete `jules-fix-trigger.yml`, `main-ci-failure-repair.yml`, and `self-healing.yml`.

# Alternatives Considered
- Leaving self-healing separate: Rejected because it clutters the UI and separates related concerns (CI execution and CI repair).

# Architectural Impact
Consolidating CI and repair pipelines into a single file reduces the Actions sidebar clutter and creates a unified view of build health and automated remediation.

# Scope
Limited to the `.github/workflows/` directory, specifically merging `jules-fix-trigger.yml`, `main-ci-failure-repair.yml`, and `self-healing.yml` into `ci.yml`.

# SPECIFY SCOPE
Limited to the `.github/workflows/` directory, specifically merging `jules-fix-trigger.yml`, `main-ci-failure-repair.yml`, and `self-healing.yml` into `ci.yml`.

# DEFINITION OF DONE
- `ci.yml` contains the new jobs for self-healing and main-ci-failure-repair.
- The 3 legacy workflow files are deleted.
- CI correctly triggers the repair jobs when jobs fail.

# UNDERSTAND THE ISSUE
- Review the `ci.yml` file and the target healing workflows to understand their current triggers, environments, and secrets requirements.

# DETERMINE APPROACH
- Use conditional logic (e.g., `if: github.event.workflow_run.conclusion == 'failure'`) to ensure repair jobs only execute when the main CI jobs fail.
- Ensure all necessary secrets (e.g., `JULES_API_KEY`) are available to the new jobs in `ci.yml`.