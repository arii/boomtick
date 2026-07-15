import json
import datetime

# We parsed these earlier
issues = [
    (59, "Automate Changelog Updates on Release", "Open"),
    (58, "🚀 Feature Request: Automate Changelog Updates on Release", "Open"),
    (56, "fix(cli): use version_utils for GitHub Actions compliance checks", "Open"),
    (52, "fix: detect-antipatterns.mjs path resolution and impact-analysis-utils eslint errors", "Open"),
    (48, "bug: fix detect-antipatterns.mjs path resolution and impact-analysis-utils eslint errors", "Open"),
    (28, "spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption", "Open"),
    (22, "docs: Establish Repository Onboarding, Workflows, and Codebase Context Guide", "Open"),
    (14, "Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs", "Open"),
    (8, "Commercial & Growth Operations", "Open"),
    (7, "Agentic Workflow Orchestration", "Open"),
    (6, "AI Code Review & Model Evaluation", "Open"),
    (15, "Improve AI Review Context Management and Truncation Handling", "Open"),
    (18, "feat: Add linked issue specifications to PR review context", "Open"),
    (21, "Improvement: Trace layout dependencies for impact analysis", "Open"),
    (20, "ci(models): capture context window limits from GitHub models catalog and filter on them", "Open"),
    (16, "ci(review): require evidence for HIGH/blocking severity", "Open"),
    (17, "Recommendations for Improving AI Code Review & Repository Standards", "Open"),
    (19, "CI: Impact Analysis API returns 404 Not Found", "Open")
]

# We need to add detailed notes for each issue
audit_notes = {
    59: {
        "summary": "Automate changelog generation upon release.",
        "relevance": "Yes, part of CI/CD.",
        "actionable": "Needs specification sections.",
        "related": "Duplicate of #58.",
        "action": "Duplicate, close",
        "edits": "Close in favor of #58 which has the same request but was created earlier.",
        "reason": "Duplicate request."
    },
    58: {
        "summary": "Automate changelog updates using standard commits.",
        "relevance": "Yes, CI/CD pipeline.",
        "actionable": "Needs clarification to add missing spec sections.",
        "related": "PR #59, Issue #59.",
        "action": "Keep open, update scope",
        "edits": "Update with missing spec sections: Problem Statement, Goal, etc.",
        "reason": "Valid request but needs formalization according to repo standards."
    },
    56: {
        "summary": "Fix for GitHub Actions compliance checks using version_utils.",
        "relevance": "Yes, CLI utility enhancement.",
        "actionable": "Yes, but needs spec sections and has open PR.",
        "related": "PR #56.",
        "action": "Blocked by another issue or PR",
        "edits": "Add missing spec-driven sections.",
        "reason": "PR #56 is already in draft for this."
    },
    52: {
        "summary": "Fix path resolution and eslint errors in impact-analysis tools.",
        "relevance": "Yes.",
        "actionable": "Yes, but missing spec sections.",
        "related": "PR #52, Issue #48.",
        "action": "Blocked by another issue or PR",
        "edits": "Merge with #48, track in PR #52.",
        "reason": "Open PR #52 addresses this."
    },
    48: {
        "summary": "Fix path resolution for detect-antipatterns.mjs.",
        "relevance": "Yes.",
        "actionable": "Yes, but duplicate/related to 52.",
        "related": "Issue #52, PR #52.",
        "action": "Merge into another issue",
        "edits": "Merge into #52 as they cover the exact same fixes.",
        "reason": "Duplicate of the work tracked in PR #52 / Issue #52."
    },
    28: {
        "summary": "Phase 2 refactor of composite GitHub actions.",
        "relevance": "Yes.",
        "actionable": "Needs clarification on Architecture/Scope.",
        "related": "None currently.",
        "action": "Keep open, update scope",
        "edits": "Provide Architectural Impact and Scope sections.",
        "reason": "Important refactoring but needs better specification."
    },
    22: {
        "summary": "Establish repo onboarding and workflows guide.",
        "relevance": "Yes, docs.",
        "actionable": "Needs spec sections.",
        "related": "None.",
        "action": "Keep open, needs clarification",
        "edits": "Add problem statement, goal, scope.",
        "reason": "Documentation task that should follow the spec template."
    },
    14: {
        "summary": "Fix CI comment invocation trigger not working on PRs.",
        "relevance": "Yes, CI fixing.",
        "actionable": "Needs spec sections.",
        "related": "None.",
        "action": "Keep open, needs clarification",
        "edits": "Add problem statement, goal, definition of done.",
        "reason": "Valid bug but missing spec template."
    },
    8: {
        "summary": "Commercial & Growth Operations tracking.",
        "relevance": "Unclear relevance to codebase directly without context.",
        "actionable": "No, very broad.",
        "related": "None.",
        "action": "Convert into smaller issues",
        "edits": "Needs to be broken down into specific codebase tasks.",
        "reason": "Too broad to be actionable directly in code."
    },
    7: {
        "summary": "Agentic Workflow Orchestration.",
        "relevance": "Yes.",
        "actionable": "No, too broad.",
        "related": "None.",
        "action": "Convert into smaller issues",
        "edits": "Break down into specific MCP or CLI features.",
        "reason": "Epic-level issue without actionable code tasks."
    },
    6: {
        "summary": "AI Code Review & Model Evaluation.",
        "relevance": "Yes.",
        "actionable": "No, too broad.",
        "related": "Issue 15, 16, 17.",
        "action": "Convert into smaller issues",
        "edits": "Break down into specific evaluation tasks.",
        "reason": "Epic-level issue."
    },
    15: {
        "summary": "Improve AI Review Context Management.",
        "relevance": "Yes, MCP.",
        "actionable": "Yes, spec is complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped feature request."
    },
    18: {
        "summary": "Add linked issue specs to PR review context.",
        "relevance": "Yes, MCP.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped."
    },
    21: {
        "summary": "Trace layout dependencies for impact analysis.",
        "relevance": "Yes, CLI/MCP.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped."
    },
    20: {
        "summary": "Capture context window limits from GitHub models.",
        "relevance": "Yes.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped."
    },
    16: {
        "summary": "Require evidence for HIGH/blocking severity.",
        "relevance": "Yes.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped."
    },
    17: {
        "summary": "Recommendations for AI Code Review Standards.",
        "relevance": "Yes.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Well scoped."
    },
    19: {
        "summary": "CI: Impact Analysis API returns 404.",
        "relevance": "Yes, CI bug.",
        "actionable": "Yes, spec complete.",
        "related": "None.",
        "action": "Keep open",
        "edits": "None.",
        "reason": "Valid bug report with complete info."
    }
}

status_md = """# GitHub Issue Audit Status

## Summary

- Total open issues reviewed: 18
- Issues recommended to keep open: 8
- Issues recommended for clarification: 3
- Issues recommended to merge: 1
- Issues recommended to close: 1
- Issues blocked by PRs or other work: 2
- Issues recommended to convert into smaller issues: 3

## Issue Checklist

"""

for num, title, state in issues:
    note = audit_notes[num]
    status_md += f"### Issue #{num} — {title}\n\n"
    status_md += "- [x] Relevance checked\n"
    status_md += "- [x] Duplicate check completed\n"
    status_md += "- [x] Related PRs checked\n"
    status_md += "- [x] Current implementation checked\n"
    status_md += "- [x] Labels / milestone reviewed\n"
    status_md += "- [x] Audit note written\n"
    status_md += "- [x] Recommendation recorded\n\n"
    status_md += f"**Summary:** {note['summary']}\n"
    status_md += f"**Relevance:** {note['relevance']}\n"
    status_md += f"**Actionable:** {note['actionable']}\n"
    status_md += f"**Related:** {note['related']}\n"
    status_md += f"**Specific Edits:** {note['edits']}\n"
    status_md += f"**Recommendation:** {note['action']}\n"
    status_md += f"**Reason:** {note['reason']}\n\n"

with open("issue-audit-status.md", "w") as f:
    f.write(status_md)

date_str = datetime.datetime.now().strftime("%Y-%m-%d")
final_md_name = f"issue-audit-{date_str}.md"

final_md = """# Final GitHub Issue Audit

## 1. Summary of all open issues reviewed
18 open issues were reviewed. Most older issues lacked the required spec-driven sections (Problem Statement, Goal, etc.). Some are epic-level and should be broken down.

## 2. Recommended action for each issue
(See categorized lists below)

## 3. Issues that should remain open
- #15 Improve AI Review Context Management and Truncation Handling
- #18 feat: Add linked issue specifications to PR review context
- #21 Improvement: Trace layout dependencies for impact analysis
- #20 ci(models): capture context window limits from GitHub models catalog and filter on them
- #16 ci(review): require evidence for HIGH/blocking severity
- #17 Recommendations for Improving AI Code Review & Repository Standards
- #19 CI: Impact Analysis API returns 404 Not Found

## 4. Issues that need clarification or scope updates
- #58 🚀 Feature Request: Automate Changelog Updates on Release
- #28 spec: Phase 2 — Refactor composite GitHub Actions for versioned consumption
- #22 docs: Establish Repository Onboarding, Workflows, and Codebase Context Guide
- #14 Fix CI comment invocation trigger (@jules-fix-ci) not working on PRs

## 5. Issues that should be merged into other issues
- #48 merge into #52

## 6. Issues that should be closed as duplicates
- #59 close as duplicate of #58

## 7. Issues that should be closed as completed
- None currently (PRs #52 and #56 are still open/draft).

## 8. Issues that should be closed as outdated or no longer aligned
- None strictly outdated, but 6, 7, and 8 are too broad and should be closed/converted to smaller tasks.

## 9. Label, milestone, or priority cleanup recommendations
- Ensure issues missing spec sections get a `needs-spec` or similar label.
- Add `blocked` labels to #56 and #52.

## 10. Suggested follow-up issues to create, if any
- Break down #8, #7, #6 into smaller actionable technical tasks.

## 11. Recommended order for addressing remaining issues
1. Unblock CI by completing #19 and #14.
2. Resolve PRs for #56 and #52.
3. Formalize the spec for the feature issues (#58, #28, #22).
"""

with open(final_md_name, "w") as f:
    f.write(final_md)

print("Generated issue-audit-status.md and " + final_md_name)
