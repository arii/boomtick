# Comprehensive PR Review Agent

## 1. Setup & Discovery
1. Activate the environment: `source .venv/bin/activate`
2. Verify runtime: `td-cli doctor`
3. Track progress systematically in `review-status.md`.

## 2. Fast Context Extraction (Avoid Truncation)
For each target PR:
1. Initialize the audit skeleton: `td-cli agent plan-review --pr <PR_NUMBER>`
2. **CRITICAL:** Do not rely on massive raw diff logs. Instead, fetch the file list and then fetch individual source file patches, filtering out lockfiles:
   ```bash
   gh pr diff <PR_NUMBER> --name-only | grep -v "pnpm-lock.yaml" > changed_files.txt
   for file in $(cat changed_files.txt); do gh pr diff <PR_NUMBER> -- $file; done > source_diffs.txt
   ```
3. Analyze `source_diffs.txt` to form the review plan.

## 3. Authoring and Submitting Reviews
1. Edit the review skeleton at `.boomtick/logs/reviews/pr-review-<PR_NUMBER>.md`.
2. **CRITICAL:** Ensure the JSON block at the bottom of the document is valid, correctly formatted JSON. Do not alter the surrounding backticks or formatting, as the `td-cli gh audit-pr --submit` parser is strictly dependent on it.
3. Submit the review: `td-cli gh audit-pr <PR_NUMBER> --submit --execute`

## 4. Finalization
1. Update `review-status.md`.
2. Commit `audit-log.md` with the overlap analysis and merge strategy.
