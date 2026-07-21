1. **Refactor `writeVerdictJson` to `async` and use `fs.promises.writeFile`.**
   - Update `lib/sharedUtils.ts`.
   - Update usages in `lib/codeReviewOrchestrator.ts`.
   - Update usages in `lib/visualReviewOrchestrator.ts`.
   - Update usages in `lib/sharedUtils.ts` (`checkReviewQuota` must `await writeVerdictJson`).
   - Update usages in `scripts/utils/verdict.ts` (`writeMissingApiKeyVerdict` must become `async`).

2. **Refactor `writeMissingApiKeyVerdict` to `async` and use `fs.promises.mkdir` / `fs.promises.writeFile`.**
   - Update `scripts/utils/verdict.ts`.
   - Update usages in `scripts/impact-ai-code-review.ts` and `scripts/impact-ai-review.ts` to `await`.

3. **Input Validation for `writeVerdictJson` / `writeMissingApiKeyVerdict` (Data sanitization/validation).**
   - In `lib/sharedUtils.ts`, add a simple check to ensure `data` is a valid object and `verdictPath` is safe.
   - For `verdictPath`, ensure it stays within the `artifactsDir` or similar using `path.resolve`.

4. **Verify tests and pre-commit.**
