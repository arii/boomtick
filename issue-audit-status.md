# GitHub Issue Audit Status

## Summary

- Total open issues reviewed: 28
- Issues recommended to keep open: 23
- Issues recommended for clarification: 0
- Issues recommended to merge: 0
- Issues recommended to close: 3
- Issues blocked by PRs or other work: 2

## Issue Checklist

### Issue #386 — Pin Playwright version in Dockerfile

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to pin the Playwright version in the Dockerfile.
**Recommendation:** Blocked by another issue or PR
**Reason:** This is currently being addressed in PR #386.

### Issue #385 — ci: align checkout action version in publish-runner.yml to v7

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to align checkout action versions.
**Recommendation:** Blocked by another issue or PR
**Reason:** This is currently being addressed in PR #385.

### Issue #384 — Refactor `impact-analysis.ts` to remove nonsensical generic try/catch wrappers

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to refactor impact-analysis.ts by removing generic try/catch wrappers.
**Recommendation:** Keep open
**Reason:** Actionable refactor of impact-analysis.ts to improve error handling clarity.

### Issue #383 — Refactor `geminiUtils.ts` and clients to remove over-architected Langchain dependencies

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to remove Langchain dependencies from geminiUtils.ts.
**Recommendation:** Keep open
**Reason:** Actionable refactor that aligns with agent instructions to avoid over-architected dependencies.

### Issue #382 — fix(ci): CI failure for branch reimplement-pr-356-3347043156945218044

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A CI failure report for a specific branch.
**Recommendation:** Keep open
**Reason:** CI failure requires investigation and fix.

### Issue #381 — fix(ci): CI failure for PR #377

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A CI failure report for PR #377.
**Recommendation:** Keep open
**Reason:** CI failure requires investigation and fix.

### Issue #380 — Fix npx install warning in Dockerfile: pin playwright version instead of using @latest

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to pin Playwright version in Dockerfile, duplicate.
**Recommendation:** Duplicate, close
**Reason:** This is a duplicate of issue #386 which already has an active PR.

### Issue #375 — Semgrep static analysis fails locally due to OpenTelemetry version conflicts

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Local environment bug regarding OpenTelemetry.
**Recommendation:** Keep open
**Reason:** Actionable bug report regarding local static analysis.

### Issue #362 — Lazy load langchain inside geminiUtils

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to lazy load Langchain, but the new direction is to remove it.
**Recommendation:** Outdated, close
**Reason:** Superseded by issue #383 which aims to entirely remove Langchain dependencies rather than just lazy loading them.

### Issue #360 — ⚡ Performance: Reduce redundant file I/O checks in codeReviewOrchestrator.ts

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Performance optimization for file I/O checks.
**Recommendation:** Keep open
**Reason:** Actionable performance improvement in codeReviewOrchestrator.

### Issue #304 — ci: introduce stale branch pruning workflow for boomtick-pkg

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to introduce branch pruning in CI.
**Recommendation:** Keep open
**Reason:** Actionable feature request for a stale branch pruning workflow.

### Issue #303 — ci: align checkout action versions in publish-runner.yml to v7

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to align checkout action versions, duplicate.
**Recommendation:** Duplicate, close
**Reason:** This is a duplicate of issue #385 which already has an active PR.

### Issue #301 — ci: standardize github app token auth for workflow dispatches in boomtick-pkg

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** A request to standardize token auth for workflow dispatches.
**Recommendation:** Keep open
**Reason:** Actionable CI improvement to use GitHub App tokens.

### Issue #167 — feat: Agentic Workflow Orchestration - Implement Context Builder Module

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request for a context builder module.
**Recommendation:** Keep open
**Reason:** Actionable feature request for the agentic workflow orchestration.

### Issue #166 — feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request to define architecture and execution graph.
**Recommendation:** Keep open
**Reason:** Actionable architectural feature request.

### Issue #163 — Implement GitHub Models Provider Strategy

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request to implement GitHub Models Provider Strategy.
**Recommendation:** Keep open
**Reason:** Actionable architectural feature request to decouple single-model dependencies.

### Issue #162 — Create UX Auditor Agent

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request for a UX Auditor Agent.
**Recommendation:** Keep open
**Reason:** Actionable feature request to create a UX auditor agent.

### Issue #143 — epic: Transition boomtick-pkg from source-level submodule to published dependency

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Epic tracking issue for submodule transition.
**Recommendation:** Keep open
**Reason:** Ongoing epic tracking issue.

### Issue #142 — infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Infrastructure task for submodule migration.
**Recommendation:** Keep open
**Reason:** Ongoing infrastructure task.

### Issue #141 — infra: Post-Migration Submodule Cleanup & Verification Tasks

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Infrastructure task for submodule cleanup.
**Recommendation:** Keep open
**Reason:** Ongoing infrastructure task.

### Issue #138 — spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Spec task for submodule removal.
**Recommendation:** Keep open
**Reason:** Ongoing spec/epic task.

### Issue #135 — Implement multi-agent coordination and branch locking protocol

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request for multi-agent coordination.
**Recommendation:** Keep open
**Reason:** Actionable feature request.

### Issue #126 — Set Up Manual Collection and Bulk Auditing of AI Code Review Logs

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Task to set up manual collection of AI code review logs.
**Recommendation:** Keep open
**Reason:** Actionable task for setting up audit logs.

### Issue #73 — Feature Request: RAG & Vector Store integration for contextual knowledge

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Feature request for RAG and Vector Store integration.
**Recommendation:** Keep open
**Reason:** Actionable feature request for RAG integration.

### Issue #28 — spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Spec task for refactoring GitHub Actions.
**Recommendation:** Keep open
**Reason:** Ongoing spec task.

### Issue #14 — Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Bug report for CI comment invocation trigger.
**Recommendation:** Keep open
**Reason:** Actionable bug report regarding CI comment invocation.

### Issue #15 — Improve AI Review Context Management and Truncation Handling

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** Improvement request for AI review context management.
**Recommendation:** Keep open
**Reason:** Actionable improvement for AI review context management.

### Issue #20 — ci(models): capture context window limits from GitHub models catalog and filter on them

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** CI improvement request to capture context window limits.
**Recommendation:** Keep open
**Reason:** Actionable CI improvement to filter models by context limits.


### Issue #394 — spec: Identify final dependencies blocking boomtick-pkg submodule removal

- [x] Relevance checked
- [x] Duplicate check completed
- [x] Related PRs checked
- [x] Current codebase checked
- [x] Labels / milestone / priority reviewed
- [x] Audit note written
- [x] Recommendation recorded

**Audit Note:** New issue created to identify remaining dependencies blocking submodule removal.
**Recommendation:** Keep open
**Reason:** Needed to complete the decoupling of the boomtick-pkg submodule.
