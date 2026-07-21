1. Review feedback mentions `lib/codeReviewOrchestrator.ts:592`: "Potential data exposure due to lack of validation/sanitization of input data. Implement input validation and sanitization for client.reportFileName."
2. Review feedback mentions `lib/geminiUtils.ts:50`: "message: any" is untrusted input path.
3. Review feedback mentions `lib/geminiUtils.ts:1`: "Potential data exposure due to lack of validation/sanitization of input data." for `message`.

Wait, the feedback is:
- `lib/geminiUtils.ts`: Implement input validation and sanitization for the `message` parameter.
- `scripts/clients/geminiCodeReviewClient.ts`: Implement input validation and sanitization for all parameters passed to invokeGeminiWithBudgetRetry.
- `scripts/clients/geminiVisualReviewClient.ts`: Implement input validation and sanitization for all parameters passed to invokeGeminiWithBudgetRetry.
- `lib/codeReviewOrchestrator.ts`: Implement input validation and sanitization for client.reportFileName.

Plan:
1. Update `lib/geminiUtils.ts` to add validation to `invokeGeminiWithBudgetRetry`: Check that `modelName` is a string, `maxOutputTokens` is a number, `thinkingBudget` is a number, and `message` is a defined object/array.
2. Update `lib/codeReviewOrchestrator.ts` and `lib/visualReviewOrchestrator.ts` to sanitize `client.reportFileName` using `path.basename(client.reportFileName)` before passing it to `path.join(ARTIFACTS_DIR, ...)` and `writeVerdictJson`.
3. Pre-commit and commit.
