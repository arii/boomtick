# Historical planning record, not current activation instructions

Patch prepared November 20 (PR #1350): README.md describes the local Replay Gate, explicit activation and schema-v2 state. Earlier key transfer, automatic credential loading and live-mode directions below are historical and superseded by that patch. Do not send secrets through chat. No live run or publication is established. Unique planning material is retained below, not treated as authorization.

# ProofLoop — Tracking Document

Live status for the Personal Agents Hackathon build (Fri Nov 20, 2026). Kiro updates this file as work progresses. Ari's CLI agents (agy, Copilot, Muse CLI) read this file to pick up work interactively. Do not delete this file. Keep it current.

Last updated: 2026-11-20 12:58 PM PT (by Kiro). PR #1350 merged-forward with main and feat/proofloop (scope check and stale exports fixed). Added Tokens with Taste as the mutation LLM backend (OpenRouter free quota is gone). Extension ID recorded.

## Repo and branch
- Repo: arii/boomtick (no new repo).
- Directory: proofloop/
- Branch: feat/proofloop — https://github.com/arii/boomtick/tree/feat/proofloop
- No PR open yet. Decision pending: open a PR now or wait until live runs are done.

## What is done
- [x] proofloop/ scaffold (extension/, harness/, skills-local/).
- [x] Three JSON schemas: replay tasks, proof ledger, sessions. All validate.
- [x] REAL sessions.jsonl (8 excerpts) in data/sessions.jsonl, validated against the sessions schema (timestamps checked as ISO 8601). Phone numbers were still present in the file, so the committed copy masks them as [PHONE-PRO] and [PHONE-FAMILY] (repo is public). The unmasked original is in data/private/sessions.raw.jsonl (git-ignored, local to Kiro sandbox).
- [x] Stubs for Senso/Cognee, plus live clients written to public API docs (harness/clients.py).
- [x] harness/mock_sponsors.py for offline live-path testing.
- [x] replay_loop.py runs all 8 steps in stub mode on the REAL sessions: v0 2/6; cycle 1 v1.1 5/6 (gate promote, Senso node complete); cycle 2 v1.2 6/6 promoted; injected v1.3-bad 4/6 (gate reject_and_refine, rolled back, active stays v1.2). Pass rates come from running the task checks, not hardcoded values. Caveat: the executor in harness/agent.py is a deterministic MODEL of agent behavior (slot baselines come from the recorded session outcomes), not an LLM run.
- [x] harness/server.py serving /augment, /config, /status and dashboard /.
- [x] harness/health.py: per-service GREEN / STUB / RED check (Senso GET /org/me, mutation-LLM 1-token completion, Cognee round trip; config-only by default, `--probe-live` to call). Run `python3 harness/health.py` after keys are set. Tested against the mock only.
- [x] demo.sh: one command (health check, validate, full run with rollback, then serves backend + dashboard on :8787). Verified from a fresh clone of the pushed branch (stub mode): 2/6 -> 5/6 -> 6/6, rollback at 4/6; no private data or skills in the clone. Needs `python3 -m venv .venv && .venv/bin/pip install jsonschema` first.
- [x] harness/validate.py, harness/make_tasks.py (derives replay_tasks.json: 6 tasks = vouch, waas, sfpromises, feels_mockup, adsense, hrm; left out: luma, feels_honest).
- [x] MV3 extension skeleton in proofloop/extension/ (manifest, background worker with chrome.tabs.query, content script, options page (read-only status, no key storage), Gemini Nano guard with backend fallback). Chip/proof-table/tab detection tested in jsdom against the local backend, not real Chrome.
- [x] skills-local/ with 3 skills copied from arii/hello (lane-coder, independent-tests, caffeinated-guardrails). Git-ignored because arii/hello is private and boomtick is public.
- [x] Live API shapes corrected from public docs: Senso base https://apiv2.senso.ai/api/v1 with X-API-Key, kb_node_id polling / content_id search, 409 handling; Cognee multipart add, cognify {datasets:[...]}, search query+search_type, X-Api-Key+X-Tenant-Id for Cloud / Bearer self-hosted (COGNEE_TENANT_ID); OpenRouter default openrouter/free alias (OPENROUTER_MODEL override); the Arcee free slug was retired (404).
- [x] **Promotion gate: local Replay Gate** (`harness/replay_gate.py`, no external gate service, no API call). Promote needs strictly more passed tasks, no previously passing check newly failing, and no increase in failed checks; equal results hold; any regression is reject_and_refine and rolls back. Ledger entries carry `replay_gate` (measured counts, regressed checks) and `retrieval` fields, schema v2.
- [x] Live code paths exercised end to end against harness/mock_sponsors.py (same 2/6 -> 5/6 -> 6/6 -> rollback flow). Not yet run against the real sponsor APIs.
- [x] TRACKING.md committed on feat/proofloop.

## What is still missing
- [ ] Run against the real Senso API (needs SENSO_API_KEY in Ari's shell). Cognee stays on the offline stub unless a URL is provided. Live code paths only exercised against harness/mock_sponsors.py.
- [ ] Luma session (consent/judge-applicant checkboxes) is not in the replay suite: slots model values, not checkbox state. Add a checkbox slot kind if Ari wants it in.
- [ ] Optional: an LLM-backed executor (needs OPENROUTER_API_KEY) so pass rates reflect a real model, not the deterministic model.
- [ ] Load the extension in real Chrome and verify chip/proof-table/tab detection (sandbox cannot start Chrome; must be done on Ari's machine).
- [ ] Backup video (90-second script) and two timed dry runs of the 3-minute demo.
- [ ] PR decision (open now or wait until live runs are done).

## Next steps (in order) and blockers
Current activation rules (PR #1350): `.env` is NOT read. Export real environment variables and opt in with `PROOFLOOP_LIVE_SERVICES`. Do not send secrets through chat.
1. Ari: merge PR #1350 (review the stacked Tokens with Taste PR into it first, or after).
2. Ari, optional live mutation LLM: start the Tokens with Taste gateway with one provider key (README "Mutation LLM via Tokens with Taste"), then `PROOFLOOP_LIVE_SERVICES=twt python3 proofloop/harness/health.py --probe-live`.
3. Ari, live Senso: `SENSO_API_KEY` exported in your shell, then `PROOFLOOP_LIVE_SERVICES=senso,twt python3 proofloop/harness/replay_loop.py --reset --bad-demo`. Senso field names are from docs and have not run against a real key yet; if it fails, paste the `[6]` line here (no key values).
4. Ari: extension in real Chrome. ID is `cbpokmfdbbcpgaookmhdgnbdcgkjkodl`. Start the backend with `PROOFLOOP_EXTENSION_ID=cbpokmfdbbcpgaookmhdgnbdcgkjkodl python3 proofloop/harness/server.py` (the ID stays the same only while the extension is loaded from the same folder). Related-tab display is off by default: enable the `local_related_tabs` option, or the chip shows 0 related tabs. Confirm the chip appears and the proof table expands.
5. Ari: two timed dry runs and a backup video.
6. PR decision for feat/proofloop into main (not requested yet).

## Live-run log
- First live run (Ari's machine, before PR #1350): Senso `403 error code: 1010` (Cloudflare blocks the default Python User-Agent; fixed with a custom User-Agent) and OpenRouter `404` retired model (default now `openrouter/free`). Cycle 1 matched the offline result (v1.1 5/6) before stopping at the Senso call.
- Tokens with Taste gateway checked in the build sandbox with no provider keys: `twt sync` OK, `twt serve` OK, chat returns 503 listing missing credentials, harness falls back to rule-based and the offline results are unchanged (2/6, 5/6, 6/6, 4/6 rejected). Successful provider completion not yet exercised.

## Needs from Ari
1. **A provider key for the gateway, or Ollama** (optional, only for an LLM-proposed mutation): Groq, Google, NVIDIA, Mistral or SambaNova free key exported in the shell that runs `twt serve`. Without it the rule-based mutator is used and every result is unchanged.
2. **SENSO_API_KEY exported in your shell** for live Senso (optional; offline stub otherwise, labeled on screen).
3. **Real Chrome check** (Next steps 4) and the demo rehearsals (5).
4. **Confirm phone masking** in data/sessions.jsonl ([PHONE-PRO], [PHONE-FAMILY]); the unmasked original is private and git-ignored.
5. **Merge decision** for PR #1350 and the stacked Tokens with Taste PR.

## Task checklist (from the ProofLoop doc)
- [x] Task 1 — Curate JSONL + replay_tasks.json (11:00–11:20 AM). Status: done. Real sessions validate; 6 tasks derived.
- [ ] Task 2 — Browser-first key entry + health checks (11:20–11:40 AM). Status: not started (needs keys from Ari or stub go-ahead).
- [ ] Task 3 — Cognee ingestion smoke test (11:40 AM–12:10 PM). Status: stub path works; live path needs Cognee URL.
- [ ] Task 4 — Core recursive loop, replay_loop.py (12:10–1:10 PM). Status: stub mode complete on real sessions (2/6 -> 5/6 -> 6/6, rollback works). Live mode needs keys.
- [ ] Task 5 — Minimal MV3 Chrome extension (1:10–1:55 PM). Status: skeleton done, tested in jsdom. Needs real Chrome load on Ari's machine.
- [ ] Task 6 — Proof table UI + demo dry run (2:30–3:00 PM). Status: dashboard done; dry runs and backup video not started. Needs Tasks 4 and 5 done.
- [ ] Task 7 — Buffer / polish / submission prep (3:00–3:55 PM). Status: not started. Submission ready by 3:55 PM, 35 min slack before 4:30 PM deadline.

## Parallel work
- Tasks 1 and 2 run in parallel (JSONL curation needs no key; key entry needs no JSONL).
- Task 5 (extension) runs in parallel with Task 4 (core loop). Sync at the end to wire the extension to the backend /augment endpoint.
- Everything else is sequential. Task 3 needs Tasks 1 and 2. Task 4 needs Task 3. Task 6 needs Tasks 4 and 5. Task 7 needs Task 6.

## Sync points
- Sync 1 — after Task 2 (~11:40 AM): all health checks green, or the missing key is named and its stub fallback is confirmed.
- Sync 2 — after Task 3 (~12:10 PM): Cognee search returns the correct session excerpt, or switch to the local Cognee stub now.
- Sync 3 — after Task 4 (~1:10 PM): end-to-end run shows v0 2/6 → v1.1 5/6 → gate promote → Senso complete → ledger entry. If it does not run end to end here, cut scope rather than debugging on stage.
- Sync 4 — after Task 5 (~1:55 PM): extension loads, chip appears, proof table expands, related tabs detected. Wire the extension to the backend /augment endpoint.
- Sync 5 — after Task 6 (~3:00 PM): two clean dry runs at 6/6, backup video recorded, demo page and tabs pre-opened. Last full rehearsal.

## How CLI agents use this file
- Read this file first before starting any ProofLoop work. It is the source of truth for what is done, what is blocked, and what is next.
- Update this file when you finish a task, hit a blocker, or learn something that changes the plan. Commit the update to feat/proofloop along with the code change.
- Do not delete the "Needs from Ari" section. Only Ari can resolve those items. If you are blocked on one, move to the next independent task and note the blocker here.
- Do not commit API keys. Keys are env vars only, never in the repo.
- Do not commit the arii/hello skills unless Ari says to (they are git-ignored because arii/hello is private and boomtick is public).

## Links
- ProofLoop doc (Google Doc): https://docs.google.com/document/d/1RnhXCpj4aOdx_8Cl9cOWu8DdCAGEcKgMJhBJE2GJ_pQ/edit
- Branch: https://github.com/arii/boomtick/tree/feat/proofloop
- Kiro session: https://app.kiro.dev/session/80013a4a-ee1c-4caf-85e3-7218e0e32149
- Real sessions.jsonl (Muse workspace): ~/workspace/goals/personal-agents-hackathon-nov-20/files/sessions.jsonl
- Kiro instructions (Muse workspace): ~/workspace/goals/personal-agents-hackathon-nov-20/files/kiro-proofloop-instructions.md
