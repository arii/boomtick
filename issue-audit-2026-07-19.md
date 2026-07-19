# Final Issue Audit - 2026-07-19

## 1. Summary of All Open Issues Reviewed
- Total issues reviewed: 20
- Keep open: 14
- Keep open, needs clarification: 2
- Merge into another issue: 3
- Completed, close: 1

## 2. Recommended action for each issue
(See categorizations below)

## 3. Issues that should remain open
- #235: Consolidate CI Failure Issues by PR Number Instead of Commit SHA
- #204: setup-agent.sh fails to install td-cli in submodule context due to incorrect path resolution
- #167: feat: Agentic Workflow Orchestration - Implement Context Builder Module
- #166: feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph
- #163: Implement GitHub Models Provider Strategy
- #162: Create UX Auditor Agent
- #143: epic: Transition boomtick-pkg from source-level submodule to published dependency
- #142: infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository
- #138: spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling
- #135: Implement multi-agent coordination and branch locking protocol
- #126: Set Up Manual Collection and Bulk Auditing of AI Code Review Logs
- #28: spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption
- #15: Improve AI Review Context Management and Truncation Handling
- #20: ci(models): capture context window limits from GitHub models catalog and filter on them

## 4. Issues that need clarification or scope updates
- #73: Feature Request: RAG & Vector Store integration for contextual knowledge (needs concrete problem statement/goals)
- #14: Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs (needs reproducible steps/problem definition)

## 5. Issues that should be merged into other issues
- #240: fix(ci): CI failure at a90d5a0a — Deployment Impact Analysis (Merge into #235)
- #239: fix(ci): CI failure at 525a94b1 — Deployment Impact Analysis (Merge into #235)
- #238: fix(ci): CI failure at 67d709bd — Deployment Impact Analysis (Merge into #235)

## 6. Issues that should be closed as duplicates
- None explicitly marked strictly 'Duplicate, close' (the CI issues were marked 'Merge into another issue').

## 7. Issues that should be closed as completed
- #83: Phase 2: Create Master Setup Action & Simplify Release Pipeline

## 8. Issues that should be closed as outdated or no longer aligned
- None.

## 9. Label, milestone, or priority cleanup recommendations
- Ensure issues #143 and #142 are tagged with relevant epic or infra labels.
- Issue #73 and #14 should be labeled with `needs-clarification`.

## 10. Suggested follow-up issues to create, if any
- No immediate new issues are needed. We should focus on defining the missing specs for #73 and #14 first.

## 11. Recommended order for addressing remaining issues
1. Triage the CI failures to ensure CI is stable, consolidating #240, #239, #238 into #235.
2. Establish the multi-agent/architecture groundwork (#166, #167, #135, #163).
3. Address the infra decoupling for `boomtick-pkg` (#143, #142, #138).
4. Follow up on context management (#15, #20, #126) and agents (#162).
