# LLM Provider Scorecard

Ledger of which providers did real merge-queue work, with evidence. Updated per task.

| Date (UTC) | Provider / model | Task | Result | Evidence |
|---|---|---|---|---|
| 2026-11-08 | native (Muse Spark) | boomtick #1212 RAG-dep fix, #1206 scope bypass, #1214 single-range probe, HIGH fallback fixes, remote-server #1186/#1187/#1188, viewer fail-closed | merged / in-flight | [boomtick main](https://github.com/arii/boomtick/commits/main), [#1214](https://github.com/arii/boomtick/pull/1214) |
| 2026-11-08 | Nebius `zai-org/GLM-5.1` via REST (`$NEBIUS_BASE_URL`) | Independent review of HIGH fallback diff (git.ts + merge_gate.py) | APPROVE, 2.3k tokens | session log cloud-baryon; usage `{completion_tokens:1317, prompt_tokens:1019}` |
| 2026-11-08 | Ollama local (6 models, `ollama ls`) | health-checked serving; no queued task fit local capacity tonight | healthy, unused | `ollama /api/tags` 200 |
| registry history | GLM (Nebius) | spec validation + plan-approve-resume flows | mixed; false-positive on truncated diff noted advisory-only | lane registry |

## Notes

- Gemini reviewer framework (existing AI-review CI + lane protocol) stays the review path; no parallel framework.
- Gap: `NEBIUS_MODEL` / `NEBIUS_SPEND_CAP_USD` unset in container env; model was picked from `GET /v1/models`. Recommend defaults so future sessions don't stall.
- Rule: test authorship stays independent of fix authorship (author != tester) with red-green evidence.
