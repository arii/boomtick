# Code Review Standards & Instructions

When evaluating a Pull Request, you must read the generated diff context (pr-context-<PR_NUMBER>.md) and evaluate the code against the following rigorous standards.

You will record your findings in the writeable `pr-review-<PR_NUMBER>.md` file.

## 1. Output Protocol (CRITICAL)

- **Target File**: You MUST modify the existing `pr-review-{PR}.md` file.
- **NO New Files**: DO NOT create temporary files or new JSON files. The submission scripts ONLY read from the specified `pr-review-{PR}.md` file.
- **Checklist Completion**: Every item in the Audit Checklist MUST be marked to indicate it was verified.
- **JSON Block**: You MUST fill the JSON block at the bottom of the file with your findings.

## 2. Audit Checklist Verification

You MUST systematically verify each item against the diff context.

### Marking Convention:
- **`[x]`**: Verified and **passed** (no issues found).
- **`[ ]`**: Verified and **failed** (issue found). You MUST provide detailed feedback for these items in the `FINDINGS` section and/or as inline comments in the JSON block.

The **Anti-AI-Slop checklist** is mandatory for all reviews.

- **Dead abstractions**: Did they introduce a new class, context, or hook that a simpler primitive could handle?
- **Unnecessary indirection**: Does this add a layer of wrapping where a direct function call would suffice?
- **Responsibility creep**: Is a component taking on state or logic that belongs in a parent container or a custom hook?
- **Import bloat**: Is `import React from 'react'` included unnecessarily (not needed in React 17+)?
- **Token compliance**: Are they using raw Tailwind values (e.g., `text-[13px]`, `bg-[#f4f4f4]`) or inline styles instead of the established design tokens?
- **Audit ratio**: If the PR adds > 100 lines of code, you must find at least 10 lines of code to recommend removing or refactoring.

## 3. CI Failure Handling

If the PR context indicates failing CI checks:
- **Block Approvals**: You MUST NOT recommend "Approved" if there are failing CI checks that are related to the PR changes.
- **Log Triage**: You must complete the "CI Log Triage" section in the review file. Use the "Detected Errors" and "Failure Logs Snippet" from the context file to perform a Root Cause Analysis and provide Remediation Steps.
- **Prioritize Fixes**: Mention the CI failures prominently in your review body and prioritize their resolution.

## 4. Review Status Mapping

- **Approved**: Zero violations AND all critical CI checks passing.
- **Approved with Minor Changes**: Minor non-breaking violations (e.g., import bloat, trivial token leakage).
- **Not Approved**: Architectural regressions, breaking changes, major token violations, OR failing CI checks.

## 5. Formatting the JSON Output

At the bottom of `pr-review-<PR_NUMBER>.md`, there is a JSON block. You must write your feedback strictly into this JSON structure.

### The JSON Schema:

```json
{
  "body": "## ANTI-AI-SLOP\n- [x] No dead abstractions\n- [x] No unnecessary indirection\n- [x] No responsibility creep\n- [x] No import bloat\n- [x] Token compliance verified\n- [x] Audit ratio satisfied\n\n## FINDINGS\n<summary of key findings and observations>\n\n## FINAL RECOMMENDATION\n<Approved | Approved with Minor Changes | Not Approved>",
  "comments": [
    {
      "path": "src/example.tsx",
      "line": 42,
      "body": "This abstraction is unnecessary. Consider passing this as a direct prop."
    }
  ]
}
```

### Output Rules:

- **Replace Placeholders**: Replace all `<findings>`, `<summary>`, and `<Approved | ...>` placeholders with actual analysis.
- **Always provide at least one comment** in the `comments` array.
- **Line Numbers**: Every inline comment MUST have a `line` number that exists within the **Valid Comment Ranges** for that file in the diff context.
- **JSON Validity**: Ensure the final submission block remains 100% valid JSON.

## 6. Infrastructure & Component Awareness

Before suggesting an implementation, verify if it already exists:

- **Layout primitives**: `src/layouts/` (Box, Stack, Grid, Text, Button)
- **UI components**: `src/components/ui/`
- **Custom hooks**: `src/hooks/` (useSearchParam, useGlobalSearch, useHotkeys)
- **Utilities**: `src/lib/utils.ts` (cn, composeStyles, safeSearch)
- **Design tokens**: `src/styles/design-tokens.ts` and `tokens.css`

**Do NOT request:**
- Building layout with `div` + flex when `<Stack>` or `<Box>` exists.
- Adding `import React` in React 17+ files.

## 7. Failure Modes (Avoid These)

- **hallucinating PR Numbers**: Always use the PR number provided in the prompt.
- **Out-of-range comments**: Comments on lines not in the diff cause 422 errors.
- **Empty payloads**: Never submit a review with empty findings or placeholders.

## 8. Tooling Guidelines

Agents must not directly use git or gh commands but reuse existing tooling (`td-cli`).
