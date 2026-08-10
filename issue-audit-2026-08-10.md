# Final Issue Audit Report - 2026-08-10

## 1. Summary of all open issues reviewed

- Total open issues reviewed: 79
- Issues recommended to keep open: 66
- Issues recommended for clarification: 0
- Issues recommended to merge: 0
- Issues recommended to close: 10
- Issues blocked by PRs or other work: 3

## 2. Recommended action for each issue
(See categorized sections below for details on each recommendation type.)

## 3. Issues that should remain open
- Issue #577 — Introduce Sticky Table of Contents for Long Guides
- Issue #576 — Standardize Product Display Modules and Sizing
- Issue #575 — Optimize Next/Previous Article Footer Navigation
- Issue #574 — Design Issue: Markdown Mermaid Graphs Unreadable and Small in Dark Mode
- Issue #562 — Deployment Impact Analysis Effectiveness Audit
- Issue #561 — model aware token usage
- Issue #555 — Resolve Import Paths and Module Resolution in send-jules-impact.py
- Issue #554 — Fix ERR_MODULE_NOT_FOUND when running check-visual-changes.ts
- Issue #553 — [Workflow Audit] Recurrent OutOfMemory / SIGABRT (Exit Code 134) in Deployment Impact Analysis
- Issue #552 — [Workflow Audit] Missing Caching Path Directory
- Issue #551 — [Workflow Audit] Widespread Node.js 20 Deprecation Warnings
- Issue #550 — ci: align checkout action versions in publish-runner.yml to v7
- Issue #548 — [Workflow Audit] Invalid Parent-Relative Path in Composite Action
- Issue #547 — [Workflow Audit] Runner Stack Overflow from Infinite Composite Action Loop
- Issue #546 — [Workflow Audit] Consolidated Health Report
- Issue #544 — refactor(scripts): extract impact-analysis helpers into scripts/impact/ submodules with Zod schemas
- Issue #542 — [Workflow Audit] Submodule Update Automation Failure
- Issue #541 — chore: route all submodule action references through local wrappers for decoupling
- Issue #539 — ci: implement run concurrency and auto-cancellation in boomtick-pkg ci.yml
- Issue #538 — ci: introduce stale branch pruning workflow for boomtick-pkg
- Issue #536 — Local Python linting (pnpm run ci:local -> lint:python) fails due to missing dependencies
- Issue #506 — Migrate GitHub Models code review to OpenAI API (GitHub Models retired July 30, 2026)
- Issue #505 — Design/Spec: Fix GitHub Models API 404 Not Found Error in AI Code Review
- Issue #504 — fix(ci): CI failure for PR #500
- Issue #501 — fix(ci): CI failure for PR #497
- Issue #496 — Design: Migrate Boomtick to Standalone Distribution (Remove Submodule)
- Issue #495 — fix(ci): CI failure for PR #486
- Issue #494 — fix(ci): CI failure for PR #460
- Issue #493 — fix(ci): CI failure for PR #476
- Issue #492 — Document Zero-Submodule Strategy for Impact Analysis Integration
- Issue #480 — design: Support GraphQL Pagination for Pull Request Files Retrieval
- Issue #471 — [Spec/Design] Standardizing Python Development Dependencies in Root Workspace
- Issue #470 — [Spec/Design] Submodule Workspace Node.js Dependency Hydration Strategy
- Issue #469 — spec: Submodule Path Detection and Mock Isolation in CLI Orchestrator
- Issue #521 — Design Gap: Missing Python ETL Linting Dependencies in Parent Repository
- Issue #455 — Spec / Design: Graceful Validation and Execution of Optional Pull Request Inputs in Composite Actions
- Issue #448 — Python unit tests fail locally due to lack of environment bootstrapping
- Issue #523 — Improve local Playwright test orchestration to automatically bootstrap prerequisites
- Issue #444 — Design Spec: Capability-Based Feature Detection and Thinking Gating for Gemini Models
- Issue #524 — Design Gap: Missing Shared CORS Middleware for Vercel API Endpoints
- Issue #525 — Design/Spec: Standardize GitHub Action Deprecation Handling Strategy
- Issue #432 — spec/design: Establish Unified CLI Parameter Overloading Conventions for Resource-Targeting Subcommands
- Issue #431 — Consolidate redundant Scope and SPECIFY SCOPE sections in issue template and validator
- Issue #526 — Design/Spec: Decouple Hidden Python Dependencies from Generic Workspace Setup
- Issue #515 — Design/Spec: Standardize pnpm Caching Dependency Resolution in GitHub Actions
- Issue #527 — Design/Spec: Standardize Version Parsing for GitHub Action Tags (CodeQL and Beyond)
- Issue #528 — Spec: Refactor GitHub Action path resolutions to support containerized runs
- Issue #428 — Deterministic Testing for DiskCache Time-To-Live (TTL) Expiration
- Issue #519 — pnpm run lint fails due to missing pylint in default environment
- Issue #517 — Missing PyYAML dependency for audit-ai-slop.py
- Issue #416 — Refactor boomtick-pkg references across workflows, scripts, and tests
- Issue #394 — spec: Identify final dependencies blocking boomtick-pkg submodule removal
- Issue #375 — Semgrep static analysis fails locally due to OpenTelemetry version conflicts
- Issue #511 — Transition boomtick-pkg submodule to zero-submodule published dependency
- Issue #301 — ci: standardize github app token auth for workflow dispatches in boomtick-pkg
- Issue #167 — feat: Agentic Workflow Orchestration - Implement Context Builder Module
- Issue #166 — feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph
- Issue #143 — epic: Transition boomtick-pkg from source-level submodule to published dependency
- Issue #142 — infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository
- Issue #141 — infra: Post-Migration Submodule Cleanup & Verification Tasks
- Issue #138 — spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling
- Issue #73 — Feature Request: RAG & Vector Store integration for contextual knowledge
- Issue #28 — spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption
- Issue #14 — Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs
- Issue #15 — Improve AI Review Context Management and Truncation Handling
- Issue #20 — ci(models): capture context window limits from GitHub models catalog and filter on them

## 4. Issues that need clarification or scope updates
None

## 5. Issues that should be merged into other issues
None

## 6. Issues that should be closed as duplicates
- Issue #502 — spec/design: Halt AI Code Reviews When PR Is Approved or Merged
- Issue #529 — spec/design: Suppress Empty / Pass-Only AI Review Messages Sent to Jules
- Issue #454 — Spec / Design: Standardize CLI Path Resolution Across Monorepo GitHub Actions
- Issue #439 — Spec: Refactor and Simplify Redundant try/catch Handlers Across CLI Scripts
- Issue #430 — Spec: Enforce Click CLI Docstring/Help Coverage via Static Unit Testing
- Issue #516 — Design: Prevent redundant dependency installations in container CI jobs
- Issue #429 — Design Gap: impact-analysis composite action lacks dependency isolation and setup
- Issue #162 — Create UX Auditor Agent
- Issue #135 — Implement multi-agent coordination and branch locking protocol
- Issue #126 — Set Up Manual Collection and Bulk Auditing of AI Code Review Logs

## 7. Issues that should be closed as completed
None - covered above.

## 8. Issues that should be closed as outdated or no longer aligned
None - covered above.

## 9. Label, milestone, or priority cleanup recommendations
- Need to apply 'blocked' label to all issues waiting on active PRs.
- 'Needs Clarification' label for issues lacking actionable scope.

## 10. Suggested follow-up issues to create, if any
- Central epic to track Zero-Submodule migration completion, given the scattered issues.

## 11. Recommended order for addressing remaining issues
1. Address and merge the active draft PRs to unblock related issues.
2. Complete the boomtick-pkg architecture migration.
3. Request clarification on poorly scoped issues.
4. Resolve environment and local tooling failures.
