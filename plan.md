1. **Create and file issue for MCP Server & Tools (`mcp/`)**
   - Create `mcp_issue.md` containing the findings:
     - Dead Code: Remove unused class member `startHttp` in `mcp/src/mcp/server.ts`.
     - Complexity: Refactor targets in `mcp/src/tools/jules/shared.ts`, `mcp/src/config.ts`.
     - Duplication: DRY up clone groups in `mcp/src/tools/github.comment_triage_summary.ts`, `mcp/src/tools/github.get_pr_diff.ts`, `mcp/src/tools/jules/cancel-session.ts`, `mcp/src/tools/jules/get-messages.ts`, `mcp/src/tools/jules/list-sessions.ts`, `mcp/src/tools/jules/send-message.ts`, `mcp/src/tools/jules/trigger-feedback.ts`.
   - Use `read_file` to verify the contents of `mcp_issue.md`.
   - Run `td gh create-issue --title "[cleanup] MCP Server & Tools" --file mcp_issue.md`

2. **Create and file issue for Core Library (`lib/`)**
   - Create `lib_issue.md` containing the findings:
     - Dead Code: Remove unused export `DEFAULT_EXCLUDED_PATTERNS` in `lib/codeReviewUtils.ts`. Fix duplicate exports for `ARTIFACTS_DIR`, `DOM_REVIEW_DIR`, `VISUAL_SUMMARY_PATH` in `lib/visualReviewConstants.ts`.
     - Complexity: Extract functions in `lib/visualReviewOrchestrator.ts` (orchestrateVisualReview), `lib/codeReviewOrchestrator.ts` (getCodeDiffSummary, aggregateReviewResults), `lib/geminiUtils.ts`, `lib/codeReviewUtils.ts` (parseCodeReviewStateDetailed), `lib/julesReviewClient.ts` (sendJulesImpactReport).
   - Use `read_file` to verify the contents of `lib_issue.md`.
   - Run `td gh create-issue --title "[cleanup] Core Library" --file lib_issue.md`

3. **Create and file issue for Scripts & Build (`scripts/`, `package.json`)**
   - Create `scripts_issue.md` containing the findings:
     - Dead Code: Remove unused dependency `@types/react` in `package.json`. Fix duplicate exports in `scripts/impact-review-utils.ts`.
   - Use `read_file` to verify the contents of `scripts_issue.md`.
   - Run `td gh create-issue --title "[cleanup] Scripts & Build" --file scripts_issue.md`

4. **Create and file issue for Python Linter Findings**
   - Create `python_lint_issue.md` containing the findings from `pylint` (which were found in previous steps):
     - Unused imports in `cli/dev_tools/cli.py` (`Any`, `Dict`, `List`), `cli/dev_tools/services/vector_store.py` (`Tuple`), `cli/dev_tools/services/ast_audit.py` (`Optional`, `Tuple`).
     - Line too long errors in `cli/dev_tools/services/vector_store.py` and multiple files under `cli/dev_tools/models/__init__.py`.
     - Too many instance attributes (10/7) and too many local variables (26/15) in `cli/dev_tools/services/vector_store.py`.
     - Too many local variables (17/15) and too many branches (19/12) in `cli/dev_tools/services/ast_audit.py`.
     - Import outside toplevel (`sys`) in `cli/dev_tools/services/context_builder.py`.
   - Use `read_file` to verify the contents of `python_lint_issue.md`.
   - Run `td gh create-issue --title "[cleanup] Python Linter Findings" --file python_lint_issue.md`

5. **Run tests**
   - Execute the project's test suite (e.g., `pnpm run test`) to ensure no accidental codebase changes or regressions occurred.

6. **Complete pre-commit steps**
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.

7. **Submit changes**
   - Use the `submit` tool to push the branch.
