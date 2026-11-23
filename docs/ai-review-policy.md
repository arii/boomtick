# AI review policy (operator guide)

Applies to the boomtick Gemini code review (`action.yml`, `lib/codeReviewOrchestrator.ts`, `lib/verdictGate.ts`). Decision record: [arii/boomtick#1403](https://github.com/arii/boomtick/issues/1403). Tests that pin it: `tests/unit/reviewPolicyMatrix.test.ts`.

## What fails the check and what only warns

The check goes red only when the review verdict is `fail` (an open HIGH finding) and the consuming workflow sets `fail-on-verdict: 'true'`. Everything else exits 0.

| Situation | Reason string in the verdict file, step summary and `blocking-findings` output | Verdict | Exit |
| --- | --- | --- | --- |
| Review completed, no blocking finding | none | `pass` | 0 |
| Review completed, open HIGH finding | none (findings listed as `- [HIGH] file:line - issue`) | `fail` | 1 with `fail-on-verdict: 'true'`, else 0 |
| `GEMINI_API_KEY` missing or model discovery finds no verified model | `UNHANDLED_ERROR` | `warn` | 0 |
| API key rejected (401, `API_KEY_INVALID`) | `MISSING_API_KEY` | `warn` | 0 |
| Gemini outage or other unhandled error in a review task | `UNHANDLED_ERROR` | `warn` | 0 |
| Rate limit (429) | `RATE_LIMIT` | `warn` | 0 |
| Model output truncated | `TRUNCATED` | `warn` | 0 |
| Model findings block malformed | `PARSE_ERROR` | `warn` | 0 |
| Diff larger than `max_diff_chars` (default 250000) | `isTruncated` in the verdict file, no reason string | `warn` | 0 |

Infra problems never block a merge. A hard error in the runner itself (for example the verdict step crashing) is not a review result and still fails the step.

## Review cap and red-at-cap

`MAX_AI_REVIEWS` (default 10, read from the environment in `lib/codeReviewOrchestrator.ts`; `action.yml` does not set it) limits reviews per PR. At the cap the reviewer skips the model call and keeps the previous verdict: if the last recorded state has an open HIGH finding the verdict stays `fail`, otherwise `pass`.

A red verdict at the cap is resolved in only two ways, never automatically:

1. Resolve the findings. Push a change that addresses them; a later review marks them `resolved` in the review state (also when the finding's code snippet no longer appears in the diff). This only helps while reviews remain under the cap.
2. A repository admin bypasses branch protection to merge.

There is no auto-retry and no override input. Re-running at the cap stays red.

## Known gaps against this policy

Tests marked `MISMATCH` in `reviewPolicyMatrix.test.ts` (`it.fails`) show runs that turn a prior FAIL into a green or warn result today. These need a decision from Ari before any code change:

- No code change detected (including a lockfile-only diff): `pass`, exit 0.
- Diff truncated on a later run: `warn`, exit 0.
- Every review task rate limited or model output truncated on a later run: `warn`, exit 0.

## Where to read the verdict

- Step outputs `verdict` (`pass`, `warn`, `fail`, `unknown`) and `blocking-findings`.
- The job summary (`### AI review verdict: ...`).
- The review comment posted by `boomtick[bot]`, which also carries the review state.

## Real consumer artifact

From [arii/remote-server PR #1566](https://github.com/arii/remote-server/pull/1566#pullrequestreview-6015464620), a `boomtick[bot]` review (redacted: the hidden base64 review-state comment was removed; the body below is a header excerpt only and contains no tokens, keys, app ids, URLs with signatures or emails). No FAIL review was found on the consumer PRs checked (#1566, #1590, #1592 are all approvals):

```
## 👁 Gemini Code Review Agent
### 🟢 Verdict: APPROVED
**Review Iteration:** #3 of 10
**Findings:** 0 blocking · 0 warning(s) · 0 clean.
**Model:** gemini-3.1-flash-lite
```

Dry-run output for a FAIL (`pnpm exec tsx scripts/review-dry-run.ts tests/fixtures/review-dry-run/fail.json`, canned review, not a real PR):

```
verdict=fail
AI review verdict: FAIL. 1 blocking finding(s):
- [HIGH] src/app.ts:3 - User input is concatenated into a SQL query, allowing injection.
This check fails because fail-on-verdict is enabled.
dry-run exit code: 1
```

## `fail-on-verdict`

Optional input on the root `action.yml`, default off. Set `fail-on-verdict: 'true'` to fail the step on a `fail` verdict. Without it the verdict is reported but the step never fails on it.
