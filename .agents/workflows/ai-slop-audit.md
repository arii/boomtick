# Agent: AI Slop Audit

Your objective is to audit the repository codebase/diffs to identify and systematically eliminate "AI slop"—specifically targeting over-engineered patterns, bizarre architectural complexities, unnecessary abstractions, duplicate logic, and artificial backward-compatibility layers introduced by AI code generation drift or hallucinated requirements.

This audit is split into two distinct parts to balance deep, systematic codebase hygiene with rapid checks of recent changes.

---

## 🔍 AI Slop Categories to Target

Scan the code and flag/fix instances matching these four core categories:

1. **Hallucinated Backward-Compatibility & Ghost Requirements**: Defensive logic, polyfills, or fallback conditions handling deprecated/imaginary features that are never used in this project.
2. **Over-Engineered Abstraction Cascades (AI Over-Architecting)**: Excessive factory patterns, single-use interfaces, triple-nested wrapper classes, or micro-modular functions that add zero operational value. **Always prefer established design system primitives (e.g., `<Stack>`, `<Grid>`, `<Box>`) over raw Tailwind or inline styles.**
3. **"AI Drift", Copy-Paste & Cargo-Culting**: Boilerplate patterns copied blindly across modules. Leverage our centralized duplicate code detection configured in `.jscpd.json`.
4. **Overly Defensive / Nonsensical Error Handling**: Blocks of generic `try/catch` re-throwing exceptions with no context, or validation checks on type-guaranteed values.

---

## Part 1: Comprehensive, Exhaustive, Massive Audit

Use this part for a full, ground-up codebase sanity check.

### Step 1 — Full Codebase Drift Review
```bash
find . -type f \
  -not -path '*/.*' \
  -not -path '*/node_modules/*' \
  -not -path '*/dist/*' \
  -not -path '*/tests/*' \
  -not -path '*/.venv/*' \
  -not -path '*/logs/*' \
  -not -path '*/__pycache__/*' \
  -not -name 'pnpm-lock.yaml' \
  -not -name 'package-lock.json' \
  -not -name 'cli-schema.json' \
  -not -name 'contract.ts' \
  -not -name '*.png' \
  -not -name '*.jpg' \
  -not -name '*.webp' \
  -not -name '*.ico' \
  -not -name '*.svg' \
  | sort
```

```bash
pnpm exec jscpd .
```

Refactor files to remove over-engineered wrappers (e.g., wrappers that only pass through arguments without adding business logic), unused imports, or redundant generic error handlers. Defer importing heavy AI dependencies inside `cli/` until needed.

Create and maintain `drift-audit-status.md` in the root of the repository to track files to review. Every single file must have an explicit line in the checklist.
Update the state as files are cleaned: `- [x] path/to/file — Verified Clean`.

---

## Part 2: Targeted Audit of Changes from the Past 24 Hours

Use this part to audit recent commits, branches, and workspace modifications before submitting code.

### Step 1 — Scope Discovery (24-Hour Diff Window)
Generate the list of files modified or introduced in the past 24 hours (excluding lockfiles and generated artifacts):
```bash
# Get all files modified in commits in the past 24 hours + currently staged/unstaged changes
(git log --since="24 hours ago" --name-only --pretty="" ; git diff --name-only; git diff --cached --name-only) | sort -u | grep -vE "^(tests/|node_modules/|dist/|\.venv/|logs/|pnpm-lock\.yaml|package-lock\.json|cli/dev_tools/cli-schema\.json|mcp/src/tools/contract\.ts)" > recent_files.txt
cat recent_files.txt
```
Calculate the count of files returned. This is your **Recent Changes Audit Count**.

### Step 2 — Targeted Refactoring (Avoiding Truncation)
Examine the exact diff of these files. **CRITICAL:** To prevent diff truncation issues in the terminal, read patches file-by-file instead of querying massive bulk diffs:
```bash
for file in $(cat recent_files.txt); do
  echo "Diff for $file:"
  git diff HEAD@{24.hours.ago} -- "$file" || git diff -- "$file"
done > recent_diffs.txt
```
Analyze `recent_diffs.txt` and focus specifically on checking if the recent additions or edits introduced any new AI slop patterns.

### Step 3 — Targeted Verification Checklist
Create a separate section in `drift-audit-status.md` named `## 24-Hour Review Checklist`.
List each recently modified file. Every file must be verified and checked off:
```markdown
## 24-Hour Review Checklist (Count: [Recent Count])
- [x] cli/dev_tools/cli.py — Verified Clean (No new slop introduced)
- [ ] lib/codeReviewOrchestrator.ts
```

---

## 🧪 Validation & Regression Checks

After refactoring any file (under either Part 1 or Part 2), you must run the verification suite to ensure correctness. **CRITICAL:** You must run tests from the project root using the established binaries.

```bash
# 1. Ensure environment is loaded
source .venv/bin/activate

# 2. Verify pinned runtime dependencies and configuration via td-cli
td-cli doctor

# 3. Verify validation schemas pipeline
pnpm run verify:schemas

# 4. Run Python unit tests inside isolated venv
.venv/bin/pytest cli/tests

# 5. Run TypeScript static analysis and unit tests
pnpm run lint-typecheck
pnpm recursive exec vitest run  # or ./mcp/node_modules/.bin/vitest run tests/ if recursive fails
```

---

## Related Workflows

- [Issue Audit](issue-audit.md)
- [Design Issue Authoring](issue-authoring.md)
