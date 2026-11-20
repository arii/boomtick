# ProofLoop — Tracking Document

Live status for the Personal Agents Hackathon build (Fri Nov 20, 2026). Kiro updates this file as work progresses. Ari's CLI agents (agy, Copilot, Muse CLI) read this file to pick up work interactively. Do not delete this file. Keep it current.

Last updated: 2026-11-20 11:36 AM PT (by Kiro). TRACKING.md arrived as pasted text and is committed. The real sessions.jsonl has NOT arrived (third attempt); see "Needs from Ari".

## Repo and branch
- Repo: arii/boomtick (no new repo).
- Directory: proofloop/
- Branch: feat/proofloop — https://github.com/arii/boomtick/tree/feat/proofloop
- No PR open yet. Decision pending: open a PR now or wait until live runs are done.

## What is done
- [x] proofloop/ scaffold (extension/, harness/, skills-local/).
- [x] Three JSON schemas: replay tasks, proof ledger, sessions. All validate.
- [x] Placeholder sessions.jsonl (8 lines) and replay_tasks.json (6 tasks). Both validate. NOTE: placeholders are synthetic. The real sessions.jsonl still needs to reach Kiro (see "Needs from Ari").
- [x] Stubs for Senso/Jev/Cognee, plus live clients written to public API docs (harness/clients.py).
- [x] harness/mock_sponsors.py for offline live-path testing.
- [x] replay_loop.py runs all 8 steps in stub mode on the placeholder data: v0 2/6, Cycle 1 v1.1 5/6 (Jev promote, Senso node complete), Cycle 2 v1.2 6/6 promoted, injected bad v1.3-bad 4/6 (Jev reject_and_refine, rolled back, active stays v1.2). Pass rates come from task checks, not hardcoded values. These numbers are for the placeholders, not the real sessions.
- [x] harness/server.py serving /augment, /config, /status and dashboard /.
- [x] harness/validate.py.
- [x] MV3 extension skeleton in proofloop/extension/ (manifest, background worker with chrome.tabs.query, content script, options Keys & Status page, Gemini Nano guard with backend fallback). Chip/proof-table/tab detection tested in jsdom against the local backend, not real Chrome.
- [x] skills-local/ with 3 skills copied from arii/hello (lane-coder, independent-tests, caffeinated-guardrails). Git-ignored because arii/hello is private and boomtick is public.
- [x] Live API shapes corrected from public docs: Senso base https://apiv2.senso.ai/api/v1 with X-API-Key, kb_node_id polling / content_id search, 409 handling; Jev questions map (choice/score/noul) to answers, tries typesafe/jev-1.14.0 first (TYPESAFE_MODEL override) then jev-latest on 400/404/422, code guard requiring strictly better candidate; Cognee multipart add, cognify {datasets:[...]}, search query+search_type, X-Api-Key+X-Tenant-Id for Cloud / Bearer self-hosted (COGNEE_TENANT_ID); OpenRouter default arcee-ai/trinity-large-thinking:free (OPENROUTER_MODEL override), unconfirmed without key.
- [x] Live code paths exercised end to end against harness/mock_sponsors.py (same 2/6 -> 5/6 -> 6/6 -> rollback flow). Not yet run against the real sponsor APIs.
- [x] TRACKING.md committed on feat/proofloop.

## What is still missing
- [ ] Real sessions.jsonl (8 real excerpts) to replace placeholders. File attachments have not reached Kiro in three attempts (only pasted text arrives). Paste the 8 lines into the chat.
- [ ] After it arrives: validate it against schemas/sessions.schema.json. The schema requires role in {user, assistant, tool}, ISO 8601 timestamp, related_tabs array. Adjust the schema or the file if the real lines differ.
- [ ] Re-derive replay_tasks.json (6 tasks) from 6 of the 8 real excerpts. Needs new checks in harness/agent.py (cross-tab facts like location/role/phone, unsupported-claim detection); the current executor only handles dates. Pick: 2 cross-tab misses, 2 hallucinations, 2 successes unless Ari says otherwise.
- [ ] Re-run replay_loop.py in stub mode on the real sessions and record the new pass rates here. They may not be 2/6 -> 5/6 -> 6/6.
- [ ] Run against real sponsor APIs (blocked on keys, see below).
- [ ] Load the extension in real Chrome and verify chip/proof-table/tab detection (sandbox cannot start Chrome; must be done on Ari's machine).
- [ ] Backup video (90-second script) and two timed dry runs of the 3-minute demo.
- [ ] PR decision (open now or wait until live runs are done).

## Needs from Ari
1. **Real sessions.jsonl** — paste the 8 lines directly into the Kiro chat as text (attachments do not reach Kiro). Muse curated them (3 cross-tab misses: Vouch San Jose/Full-time, Luma San Jose/judge/sponsor-sharing, WaaS phone 8803; 2 hallucinations: SF Promises fabrication, Feels mockup confusion matrix; 3 successes: AdSense live, HRM live, Feels no-fabrication rule). Source: ~/workspace/goals/personal-agents-hackathon-nov-20/files/sessions.jsonl. A repo path or gist Kiro can fetch over HTTPS also works. Keep PII redacted as [REDACTED].
2. **API keys, or go-ahead to proceed on stubs** — SENSO_API_KEY, TYPESAFE_API_KEY, Cognee URL (+key/tenant if Cloud), OPENROUTER_API_KEY. Keys are used only as env vars, never committed. Get them from the ProofLoop doc (Section 3) or Discord #senso, #typesafe_ai, #cognee.
3. **typesafe/jev-1.14.0 confirmation** — Is jev-1.14.0 hackathon-specific? Public docs list jev-1.13.0 / jev-latest. Kiro tries 1.14.0 first then falls back to jev-latest on 400/404/422.
4. **arii/hello skills decision** — Whether to commit the 3 git-ignored skills (lane-coder, independent-tests, caffeinated-guardrails) or keep them git-ignored. They are in skills-local/ but ignored because arii/hello is private and boomtick is public.
5. **PR decision** — Open a PR now on feat/proofloop, or wait until live runs are done.
6. **Real Chrome check (Ari's machine)** — chrome://extensions -> Developer mode -> Load unpacked -> proofloop/extension; run `python3 proofloop/harness/server.py`; open extension/test/demo.html with related-1.html and related-2.html in one window.

## Task checklist (from the ProofLoop doc)
- [ ] Task 1 — Curate JSONL + replay_tasks.json (11:00–11:20 AM). Status: placeholders done; real sessions.jsonl not received yet; re-derive replay_tasks.json after that.
- [ ] Task 2 — Browser-first key entry + health checks (11:20–11:40 AM). Status: not started (needs keys from Ari or stub go-ahead).
- [ ] Task 3 — Cognee ingestion smoke test (11:40 AM–12:10 PM). Status: stub path works; live path needs Cognee URL.
- [ ] Task 4 — Core recursive loop, replay_loop.py (12:10–1:10 PM). Status: stub mode complete on placeholders (2/6 -> 5/6 -> 6/6, rollback works). Live mode needs keys. Re-run on real sessions pending.
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
- Sync 3 — after Task 4 (~1:10 PM): end-to-end run shows v0 2/6 → v1.1 5/6 → Jev promote → Senso complete → ledger entry. If it does not run end to end here, cut scope rather than debugging on stage.
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
