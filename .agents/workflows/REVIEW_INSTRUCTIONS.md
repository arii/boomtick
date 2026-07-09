# Code Review Standards & Instructions

Read `pr-context-<PR_NUMBER>.md` and evaluate the code against these standards. Record findings in `pr-review-<PR_NUMBER>.md`.

## 1. Output Protocol

- **Target File**: Modify the existing `pr-review-{PR}.md`.
- **No New Files**: Do not create temporary or JSON files.
- **Checklist**: Mark every Audit Checklist item to indicate verification.
- **JSON Block**: Fill the JSON block at the bottom of the file with findings.

## 2. Audit Checklist

Mark items as `[x]` (passed) or `[ ]` (failed). Provide detailed feedback for failed items.

### Anti-AI-Slop
- **Dead abstractions**: No new classes/hooks where simpler primitives suffice.
- **Unnecessary indirection**: No wrapping where a direct function call suffices.
- **Responsibility creep**: Components should not manage logic belonging in parents/hooks.
- **Import bloat**: No `import React from 'react'` in React 17+.
- **Token compliance**: No raw Tailwind values or inline styles; use established design tokens.

## 3. Severity Standards

- **High/Blocking**: Concerns must feature concrete code contradictions (e.g., type mismatch, nonexistent call, wrong arity, failing test). Cite exact lines.
- **No Speculation**: If it uses "could" or "might", it is non-blocking. Downgrade to "Approved with Minor Changes".
- **Verification**: Do not raise concerns you cannot verify. State what is needed to verify rather than assuming the worst case.

## 4. CI Failure Handling

If the PR context indicates failing CI checks:
- **Block Approvals**: You MUST NOT recommend "Approved" if there are failing CI checks that are related to the PR changes.
- **Log Triage**: You must complete the "CI Log Triage" section in the review file. Use the "Detected Errors" and "Failure Logs Snippet" from the context file to perform a Root Cause Analysis and provide Remediation Steps.
- **Prioritize Fixes**: Mention the CI failures prominently in your review body and prioritize their resolution.

## 5. Review Status Mapping

### Review Status Mapping:
- **Approved**: Zero violations AND all critical CI checks passing.
- **Approved with Minor Changes**: Minor non-breaking violations (e.g., import bloat, trivial token leakage), or speculative concerns that lack concrete evidence of failure.
- **Not Approved**: Architectural regressions, evidenced breaking changes (see Section 3), major token violations, OR failing CI checks.

## 6. Formatting the Output (Markdown + JSON)

The review file uses a separated format to prevent JSON escaping issues. You must write standard Markdown at the top and a structured JSON block at the very bottom for metadata.

### The Metadata JSON Block:

```json
{
  "body": "## ANTI-AI-SLOP\\n<findings>\\n\\n## FINDINGS\\n<summary>\\n\\n## FINAL RECOMMENDATION\\n<Approved | Approved with Minor Changes | Not Approved>\\n\\n<!-- td-review-manager-comment -->",
  "recommendation": "<Approved | Approved with Minor Changes | Not Approved>",
  "labels": [],
  "comments": []
}
```

### Output Rules:

- **Standard Markdown Body**: Write your findings, checklist, and triage as standard Markdown at the top of the file.
- **Flattened Schema**: The JSON block must ONLY contain metadata (`recommendation`, `labels`, `comments`). Do NOT nest the review body inside JSON.
- **Comments**: Provide inline comments in the `comments` array. If no inline issues are found, use an empty array `[]`.
- **Line Numbers**: Every inline comment MUST have a `line` number that exists within the **Valid Comment Ranges** for that file in the diff context.
- **JSON Validity**: Ensure the final submission block remains 100% valid JSON.

## 7. Tiered Review Standards (Application vs. Infrastructure)

Distinguish between "Application" and "Infrastructure/Tooling" code to provide relevant feedback.

### Infrastructure & Tooling (`scripts/`, `boomtick-pkg/cli/`, `.github/`, `setup-agent.sh`)
- **Portability**: Avoid shell-specific extensions (bashisms) unless necessary. Prefer standard POSIX shell or robust Bash 4+.
- **Idempotency**: Scripts should be safe to run multiple times.
- **Error Handling**: Use `set -e`, `set -u`, `set -o pipefail`. Provide clear error messages.
- **Security**: Never hardcode secrets. Use environment variables or masked inputs.
- **Verification**: Allow verification via dry-runs, log analysis, or `bash -n` static checks when live execution is risky.

### Application & UI (`src/`)
- **Layout primitives**: `src/layouts/` (Box, Stack, Grid, Text, Button)
- **UI components**: `src/components/ui/`
- **Custom hooks**: `src/hooks/` (useSearchParam, useGlobalSearch, useHotkeys)
- **Utilities**: `src/lib/utils.ts` (cn, safeSearch)
- **Design tokens**: `src/styles/design-tokens.ts` and `tokens.css`

## 8. Component Awareness (Application Only)

Before suggesting an implementation, verify if it already exists:

- **Layout primitives**: `src/layouts/` (Box, Stack, Grid, Text, Button)
- **UI components**: `src/components/ui/`
- **Custom hooks**: `src/hooks/` (useSearchParam, useGlobalSearch, useHotkeys)
- **Utilities**: `src/lib/utils.ts` (cn, safeSearch)
- **Design tokens**: `src/styles/design-tokens.ts` and `tokens.css`

**Do NOT request:**
- Building layout with `div` + flex when `<Stack>` or `<Box>` exists.
- Adding `import React` in React 17+ files.

## 9. Failure Modes (Avoid These)

- **hallucinating PR Numbers**: Always use the PR number provided in the prompt.
- **Out-of-range comments**: Comments on lines not in the diff cause 422 errors.
- **Empty payloads**: Never submit a review with empty findings or placeholders.

## 10. Git Merge & Conflict Resolution

In scenarios involving branch orchestration or PR consolidation, agents may encounter complex merge states:
- **Unrelated Histories**: If `git merge` fails with `fatal: refusing to merge unrelated histories`, agents should retry the merge using the `--allow-unrelated-histories` flag.
- **Heavy Conflicts (Patch Fallback)**: For disjoint histories or heavy merge conflicts where standard git merging is fragile, utilize a patch-based approach:
  1. Generate a clean patch from the source branch: `git diff base_branch...head_branch > changes.patch`
  2. Apply the patch to the target branch: `git apply changes.patch`
  3. Manually resolve any `.rej` (rejected) chunks.

## 11. Tooling Guidelines

Agents must not directly use git or gh commands but reuse existing tooling (`td-cli`).
