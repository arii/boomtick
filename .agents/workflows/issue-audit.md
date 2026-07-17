# Agent: Issue Audit

Audit every currently open GitHub issue in this repository and create a persistent `issue-audit-status.md` document that tracks the full process with checkboxes.

You must continue working until every open issue has been reviewed. Do not stop to ask questions, request verification, or wait for confirmation. Make reasonable decisions based on the repository, agent docs, current codebase, roadmap docs, existing conventions, closed issues, linked PRs, and the available `td-cli` commands.

---

## Required Setup

1. Read the repository agent docs first (`.agents/workflows/`).
2. **CRITICAL:** Activate the Python virtual environment before running any `td-cli` commands:
   ```bash
   source .venv/bin/activate
   ```
3. Verify environment and remote setup:
   ```bash
   td-cli doctor
   td-cli gh detect-conflicts --all
   ```
4. Create or update an `issue-audit-status.md` file before beginning detailed audit work.
5. Keep `issue-audit-status.md` updated as you complete each issue review.

Use the dev-tools CLI wherever it helps inspect issues, labels, linked PRs, branches, commits, project status, or related files:

```bash
# Search for all open issues
td-cli gh search-issues

# Validate a single issue or all open issues
td-cli gh validate-issue --issue-number <N>
td-cli gh validate-issue --all-open

# View PR status board to cross-reference active work
td-cli gh status-board

# Check for overlapping / duplicate PR work
td-cli gh overlaps

# Post a comment to an issue (dry-run by default, requires --execute to actually post)
td-cli gh validate-issue --all-open --post-comments --execute
```

---

## Audit Scope

For each open issue, evaluate:
- Whether the issue is still relevant to the current repository structure (`mcp/` and `cli/` split).
- Whether the issue has already been completed or superseded.
- Whether the issue duplicates another issue.
- Whether the issue is clear enough to act on.
- Whether the requested work matches the current product direction (MCP Gateway and CLI).
- Whether the issue describes a real user, UX, content, design, CI, or technical problem.
- Whether the issue has enough implementation detail.
- Whether labels, priority, milestone, or assignee need updates.
- Whether the issue should remain open, be revised, be merged into another issue, or be closed.

---

## Review & Feedback Criteria

For every issue, evaluate against the current codebase (`mcp/src/` or `cli/`), documentation (`.agents/`), recent merges, open PRs, and duplicates. Assess user value, implementation risk, scope, and actionability. Provide a clear audit note that includes:
- A short summary of what the issue is asking for
- Whether the issue is still relevant and actionable
- Any related PRs, files, or issues
- Specific edits if the issue should be clarified or narrowed
- A recommended next action, including a closing reason if applicable

Use one of these recommended outcomes for each issue:
- `Keep open`
- `Keep open, needs clarification`
- `Keep open, update scope`
- `Merge into another issue`
- `Duplicate, close`
- `Completed, close`
- `Outdated, close`
- `Not aligned with current direction, close`
- `Blocked by another issue or PR`
- `Convert into smaller issues`

Be critical but helpful. Do not close issues silently without explaining why. Do not recommend closing an issue just because another issue is more polished; only recommend closing when it is truly duplicate, completed, outdated, no longer relevant, or not aligned with the repository direction.

Do not close an issue just because there's a related PR. Only close an issue if the related PR was merged and the fix is actively present in the main branch.

---

## `issue-audit-status.md` Requirements

Maintain a markdown checklist that includes:
- List of every open issue reviewed
- Audit status for each issue
- Relevance checked
- Duplicate check completed
- Related PRs checked
- Current codebase checked
- Labels / milestone / priority reviewed
- Recommended action recorded
- Final audit note written
- Close / keep / revise recommendation recorded

### Example Structure

```markdown
# GitHub Issue Audit Status

## Summary

- Total open issues reviewed:
- Issues recommended to keep open:
- Issues recommended for clarification:
- Issues recommended to merge:
- Issues recommended to close:
- Issues blocked by PRs or other work:

## Issue Checklist

### Issue #123 — Issue title

- [ ] Relevance checked
- [ ] Duplicate check completed
- [ ] Related PRs checked
- [ ] Current implementation checked
- [ ] Labels / milestone reviewed
- [ ] Audit note written
- [ ] Recommendation recorded

**Recommendation:** Keep open / Close / Merge / Revise
**Reason:** ...
```

---

## Final Audit Document

When all issue reviews are complete, create and commit a markdown audit file (`issue-audit-<date>.md`).

The final audit must include:
1. Summary of all open issues reviewed
2. Recommended action for each issue
3. Issues that should remain open
4. Issues that need clarification or scope updates
5. Issues that should be merged into other issues
6. Issues that should be closed as duplicates
7. Issues that should be closed as completed
8. Issues that should be closed as outdated or no longer aligned
9. Label, milestone, or priority cleanup recommendations
10. Suggested follow-up issues to create, if any
11. Recommended order for addressing remaining issues

---

## Optional Issue Updates

If repository permissions and tooling allow it, update issues directly after writing the audit:
- Add audit comments to issues. Ensure your review document passed to the CLI follows standard Markdown layout with checkboxes, rather than just a raw JSON block, to avoid parsing errors.
- Apply or update labels.
- Link duplicate issues.
- Reference related PRs.
- Close issues only when the audit clearly supports closure.
- Do not close ambiguous issues without leaving a clear explanation.

```bash
# Post audit comments and apply label updates
td-cli gh validate-issue --all-open --post-comments --execute
```

---

## Completion Rule

Do not stop until:
- Every open issue has been reviewed
- `issue-audit-status.md` has been fully updated
- A recommendation has been recorded for every issue
- The final issue audit markdown file has been created
- The audit files have been committed
- Any safe issue updates have been applied, if tooling allows

Do not ask questions. Do not wait for verification. Complete the full issue audit using the available repository context and tooling.

---

## Related Workflows

- [AI Slop Audit](ai-slop-audit.md)
- [Design Issue Authoring](issue-authoring.md)
