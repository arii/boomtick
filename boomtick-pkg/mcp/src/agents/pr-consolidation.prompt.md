# PR Consolidation Guidelines

## Objective
Identify and propose consolidation of Pull Requests (PRs) that demonstrate high levels of functional or structural overlap to minimize code conflicts and streamline review cycles.

## Analysis Criteria
When reviewing the output of the `pr_overlap.py` analysis, evaluate candidates based on the following:

### 1. File Overlap Density
* **High Overlap:** PRs sharing identical files or logical components (e.g., core styles, shared UI components). These are primary candidates for consolidation.
* **Context:** Check if the overlapping files are `design-tokens.ts` or `ci.yml`. Broad overlaps in infrastructure files might indicate a need for coordination rather than full consolidation.

### 2. Functional Alignment (PR Titles & Descriptions)
* Review the PR titles to determine if they share a common feature set (e.g., "Mobile UI" or "Home Page Performance").
* Look for duplicate effort; if two PRs address the same UI improvement, they should be merged into a single branch.

### 3. Linked Issue Dependency
* Cross-reference the `(Fixes: #...)` metadata.
* If multiple PRs resolve related issues (e.g., #101 and #102 are both part of the same UX audit), suggest consolidating these to ensure the full feature set is verified as one unit.

## Actionable Recommendations
For every identified cluster:
1.  **Draft a Proposal:** Write a summary identifying the involved PRs and the common files shared.
2.  **Assign Ownership:** Determine if one author should take lead on the consolidated PR, or if a pair-programming session is required.
3.  **Conflict Resolution:** Explicitly state the plan for handling conflicting logic in shared files identified in the report.

## Submission
Present the findings in the following format:
- **Cluster ID:** [List of PR Numbers]
- **Primary Overlap:** [List of critical shared files]
- **Recommendation:** [Merge/Coordinate/Separate]
- **Rationale:** [Brief explanation referencing issues fixed]
