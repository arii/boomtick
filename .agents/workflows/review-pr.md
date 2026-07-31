# Comprehensive PR Review Agent

## 1. Setup & Discovery
1. Activate the environment: `source .venv/bin/activate`
2. Verify runtime: `td-cli doctor`
3. Track progress systematically in `review-status.md`.

## 2. Multi-Tiered Model Configuration & Fallbacks
The review system leverages a dynamic, resilient provider strategy configured in `project_config.json`:
- **triage_chain**: Configured for initial triage.
  - *Primary*: `gpt-4o-mini` (or env override `AI_TRIAGE_CHAIN_PRIMARY`).
  - *Fallbacks*: `llama-3.3-70b-instruct` (or env override `AI_TRIAGE_CHAIN_FALLBACKS`).
- **code_review_chain**: Configured for deep, specialized review.
  - *Primary*: `gpt-4o` (or env override `AI_SPECIALIST_CHAIN_PRIMARY`).
  - *Fallbacks*: `deepseek-r1`, `llama-3.3-70b-instruct` (or env override `AI_SPECIALIST_CHAIN_FALLBACKS`).

**Fallback Registry Mechanism:**
In case of recoverable errors (429 rate limits, 50x server errors), the client automatically retries with exponential backoff and cascades through the defined fallback models. This ensures zero-disruption execution even during API degradation.

## 3. Triage vs. Specialist Review Decision
Review execution must utilize the multi-tiered model pipeline based on diff complexity to optimize cost and quality:
- **Triage Phase (Triage Agent)**:
  - Validates the diff context initially.
  - **Triage Decision**:
    - *Simple Changes*: Small style cleanups, documentation, small utility functions, configuration tweaks, or minor text modifications are handled directly in the triage phase using fast/cheap models.
    - *Complex Changes*: Architectural adjustments, core layout/UI additions, data flow changes, performance-sensitive algorithms, or potential security implications are flagged to trigger the specialist phase.
- **Specialist Phase (Specialist Agent)**:
  - Triggered automatically when triage detects complexity. Executes deep, isolated analysis with a high-capacity model (e.g., `gpt-4o` / `deepseek-r1`) to find edge cases and vulnerabilities.

## 4. Fast Context Extraction (Avoid Truncation)
For each target PR:
1. Initialize the audit skeleton: `td-cli agent plan-review --pr <PR_NUMBER>`
2. **CRITICAL:** Do not rely on massive raw diff logs. Instead, fetch the file list and then fetch individual source file patches, filtering out lockfiles:
   ```bash
   gh pr diff <PR_NUMBER> --name-only | grep -v "pnpm-lock.yaml" > changed_files.txt
   for file in $(cat changed_files.txt); do gh pr diff <PR_NUMBER> -- $file; done > source_diffs.txt
   ```
3. Analyze `source_diffs.txt` to form the review plan.

## 5. Standard Inline Feedback Formatting
To ensure clarity, usefulness, and easy parsing, all inline comments provided in the review metadata JSON must adhere strictly to the following markdown structure inside the comment body:

```markdown
### `[Category]` **[Brief Summary]**
- **Issue**: Clear and objective explanation of the problem, referencing specific lines/variables. Avoid speculative language.
- **Actionable Fix**: Concrete code correction or exact step to resolve the issue. Provide inline code snippets where possible.
```

*Allowed Categories*: `Logic`, `Security`, `Performance`, `Consistency`, `Quality`.

## 6. Authoring and Submitting Reviews
1. Edit the review skeleton at `.boomtick/logs/reviews/pr-review-<PR_NUMBER>.md`.
2. **CRITICAL:** Ensure the JSON block at the bottom of the document is valid, correctly formatted JSON. Do not alter the surrounding backticks or formatting, as the `td-cli gh audit-pr --submit` parser is strictly dependent on it. Ensure the inline comments inside `comments` array follow the standard format defined in Section 5.
3. Submit the review: `td-cli gh audit-pr <PR_NUMBER> --submit --execute`

## 7. Finalization
1. Update `review-status.md`.
2. Commit `audit-log.md` with the overlap analysis and merge strategy.
