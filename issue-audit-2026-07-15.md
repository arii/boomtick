# Final GitHub Issue Audit

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
