# Final GitHub Issue Audit - 2026-07-22

## 1. Summary of all open issues reviewed
A total of 23 open issues were reviewed. Most of them pertain to automated CI failure reports and some specification/epic tracking tasks for the `boomtick-pkg` transition.

## 2. Recommended action for each issue
- **#336 fix(ci): CI failure for PR #334**: Keep open
- **#327 Draft: Migrate tech-dancer to unified agent-orchestrator workflow**: Keep open
- **#321 fix(ci): CI failure for PR #320**: Keep open
- **#319 fix(ci): CI failure for PR #318**: Keep open
- **#306 agentic: implement execution lock / concurrency gating for ci-repair.yml**: Keep open
- **#304 ci: introduce stale branch pruning workflow for boomtick-pkg**: Keep open
- **#303 ci: align checkout action versions in publish-runner.yml to v7**: Keep open
- **#301 ci: standardize github app token auth for workflow dispatches in boomtick-pkg**: Keep open
- **#167 feat: Agentic Workflow Orchestration - Implement Context Builder Module**: Keep open
- **#166 feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph**: Keep open
- **#163 Implement GitHub Models Provider Strategy**: Keep open
- **#162 Create UX Auditor Agent**: Keep open
- **#143 epic: Transition boomtick-pkg from source-level submodule to published dependency**: Keep open
- **#142 infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository**: Keep open
- **#141 infra: Post-Migration Submodule Cleanup & Verification Tasks**: Keep open
- **#138 spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling**: Keep open
- **#135 Implement multi-agent coordination and branch locking protocol**: Keep open
- **#126 Set Up Manual Collection and Bulk Auditing of AI Code Review Logs**: Keep open
- **#73 Feature Request: RAG & Vector Store integration for contextual knowledge**: Keep open, needs clarification
- **#28 spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption**: Keep open
- **#20 ci(models): capture context window limits from GitHub models catalog and filter on them**: Keep open
- **#15 Improve AI Review Context Management and Truncation Handling**: Keep open
- **#14 Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs**: Keep open, needs clarification

## 3. Issues that should remain open
- **#336**: fix(ci): CI failure for PR #334
- **#327**: Draft: Migrate tech-dancer to unified agent-orchestrator workflow
- **#321**: fix(ci): CI failure for PR #320
- **#319**: fix(ci): CI failure for PR #318
- **#306**: agentic: implement execution lock / concurrency gating for ci-repair.yml
- **#304**: ci: introduce stale branch pruning workflow for boomtick-pkg
- **#303**: ci: align checkout action versions in publish-runner.yml to v7
- **#301**: ci: standardize github app token auth for workflow dispatches in boomtick-pkg
- **#167**: feat: Agentic Workflow Orchestration - Implement Context Builder Module
- **#166**: feat: Agentic Workflow Orchestration - Define Architecture and Execution Graph
- **#163**: Implement GitHub Models Provider Strategy
- **#162**: Create UX Auditor Agent
- **#143**: epic: Transition boomtick-pkg from source-level submodule to published dependency
- **#142**: infra: Migrate boomtick-pkg to external submodule referencing the standalone boomtick repository
- **#141**: infra: Post-Migration Submodule Cleanup & Verification Tasks
- **#138**: spec: Phase 4 — Remove boomtick-pkg submodule after full decoupling
- **#135**: Implement multi-agent coordination and branch locking protocol
- **#126**: Set Up Manual Collection and Bulk Auditing of AI Code Review Logs
- **#28**: spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption
- **#20**: ci(models): capture context window limits from GitHub models catalog and filter on them
- **#15**: Improve AI Review Context Management and Truncation Handling

## 4. Issues that need clarification or scope updates
- **#73**: Feature Request: RAG & Vector Store integration for contextual knowledge
- **#14**: Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs

## 5. Issues that should be merged into other issues
None.

## 6. Issues that should be closed as duplicates
None.

## 7. Issues that should be closed as completed

## 8. Issues that should be closed as outdated or no longer aligned

## 9. Label, milestone, or priority cleanup recommendations
- **Cleanup Stale Labels**: Many automated `fix(ci)` issues might need `wontfix` or `stale` labels applied if the PR is abandoned without merging.
- **Prioritization Needed**: Epic #143 should be prioritized as it involves a significant transition to a published dependency.
- **Needs Clarification Enforcement**: Any issue labelled with `needs-clarification` (e.g., #73) that is inactive for >30 days should be closed.

## 10. Suggested follow-up issues to create, if any
- Create an issue to automatically close `fix(ci)` issues once the linked PR is merged or closed to avoid future bloat.
- Create a tracking issue for standardizing issue templates across `mcp/` and `cli/` directories since many are missing required `spec-driven` fields.

## 11. Recommended order for addressing remaining issues
1. **Close all non-actionable issues**: Run the script to close `test` issues and duplicate issues (e.g. #324, #332, #335).
2. **Close resolved CI failures**: Close all `fix(ci)` issues tied to already merged PRs.
3. **Provide clarification updates**: Request clarification on #73 and #28 so they can move forward.
4. **Tackle critical infrastructure tasks**: Continue work on Epic #143 and its sub-tasks (#142, #141, #138).
5. **Resume Feature Development**: Address Agentic Workflow Orchestration (#166, #167) and UX Auditor (#162).
