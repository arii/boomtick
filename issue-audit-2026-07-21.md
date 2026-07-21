# Issue Audit - 2026-07-21

## Summary of all open issues reviewed
Reviewed 21 open issues in the BoomTick repository. The focus was on identifying stale, duplicate, completed, or misaligned issues to clean up the backlog, particularly addressing the architectural shift from boomtick-pkg to standalone cli/ and mcp/ directories.

## Recommended action for each issue
See specific categorization sections below.

## Issues that should remain open
- #295: fix(ci): CI failure for branch jules-5465854236761332509-1b394437
- #254: fix(ci): CI failure for PR #268
- #167: feat: Agentic Workflow Orchestration - Implement Context Builder Module
- #166: feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph
- #163: Implement GitHub Models Provider Strategy
- #162: Create UX Auditor Agent
- #135: Implement multi-agent coordination and branch locking protocol
- #126: Set Up Manual Collection and Bulk Auditing of AI Code Review Logs

## Issues that need clarification or scope updates
- #73: Feature Request: RAG & Vector Store integration for contextual knowledge
- #14: Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs

## Issues that should be merged into other issues
- None

## Issues that should be closed as duplicates
- None

## Issues that should be closed as completed
- #204: setup-agent.sh fails to install td-cli in submodule context due to incorrect path resolution
- #15: Improve AI Review Context Management and Truncation Handling

## Issues that should be closed as outdated or no longer aligned
- #292: test
- #291: test
- #143: epic: Transition boomtick-pkg from source-level submodule to published dependency
- #142: infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository
- #141: infra: Post-Migration Submodule Cleanup & Verification Tasks
- #139: spec: Phase 3 — Replace source-level script invocations with installed CLI/package calls
- #138: spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling
- #28: spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption

## Label, milestone, or priority cleanup recommendations
- Apply `wontfix` or `obsolete` labels to issues #143, #142, #141, #139, #138, #28 before closing them to document why they were closed.
- Close the test issues #291 and #292 as `invalid`.

## Suggested follow-up issues to create, if any
- None immediately required.

## Recommended order for addressing remaining issues
1. Clarify requirements on #73 and #14.
2. Resolve recent CI failures (#295, #254).
3. Continue feature development on agent coordination and context building (#135, #166, #167).
