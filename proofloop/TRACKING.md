# ProofLoop — Tracking Document

Live status for the Personal Agents Hackathon build (Fri Nov 20, 2026). Kiro updates this file as work progresses. Ari's CLI agents (agy, Copilot, Muse CLI) read this file to pick up work interactively. Do not delete this file. Keep it current.

Last updated: 2026-11-20 12:02 PM PT (by Kiro). Focus is Senso + OpenRouter only (Jev and TypeSafe are out of the challenge). Local gate in place. Neither key has reached the Kiro sandbox yet.

## Repo and branch
- Repo: arii/boomtick (no new repo).
- Directory: proofloop/
- Branch: feat/proofloop — https://github.com/arii/boomtick/tree/feat/proofloop
- No PR open yet. Decision pending: open a PR now or wait until live runs are done.

## What is done
- [x] proofloop/ scaffold (extension/, harness/, skills-local/).
- [x] Three JSON schemas: replay tasks, proof ledger, sessions. All validate.
- [x] REAL sessions.jsonl (8 excerpts) in data/sessions.jsonl, validated against the sessions schema (timestamps checked as ISO 8601). Phone numbers were still present in the file, so the committed copy masks them as [PHONE-PRO] and [PHONE-FAMILY] (repo is public). The unmasked original is in data/private/sessions.raw.jsonl (git-ignored, local to Kiro sandbox).
- [x] Stubs for Senso/Cognee, plus live clients written to public API docs (harness/clients.py). Jev client and stub are kept in clients.py but disabled (see Jev removed below).
- [x] harness/mock_sponsors.py for offline live-path testing.
- [x] replay_loop.py runs all 8 steps in stub mode on the REAL sessions: v0 2/6; cycle 1 v1.1 5/6 (gate promote, Senso node complete); cycle 2 v1.2 6/6 promoted; injected v1.3-bad 4/6 (gate reject_and_refine, rolled back, active stays v1.2). Pass rates come from running the task checks, not hardcoded values. Caveat: the executor in harness/agent.py is a deterministic MODEL of agent behavior (slot baselines come from the recorded session outcomes), not an LLM run.
- [x] harness/server.py serving /augment, /config, /status and dashboard /.
- [x] harness/health.py: per-service GREEN / STUB / RED check (Senso GET /org/me, OpenRouter 1-token completion, Cognee round trip). Run `python3 harness/health.py` after keys are set. Tested against the mock only.
- [x] harness/validate.py, harness/make_tasks.py (derives replay_tasks.json: 6 tasks = vouch, waas, sfpromises, feels_mockup, adsense, hrm; left out: luma, feels_honest).
- [x] MV3 extension skeleton in proofloop/extension/ (manifest, background worker with chrome.tabs.query, content script, options Keys & Status page, Gemini Nano guard with backend fallback). Chip/proof-table/tab detection tested in jsdom against the local backend, not real Chrome.
- [x] skills-local/ with 3 skills copied from arii/hello (lane-coder, independent-tests, caffeinated-guardrails). Git-ignored because arii/hello is private and boomtick is public.
- [x] Live API shapes corrected from public docs: Senso base https://apiv2.senso.ai/api/v1 with X-API-Key, kb_node_id polling / content_id search, 409 handling; Cognee multipart add, cognify {datasets:[...]}, search query+search_type, X-Api-Key+X-Tenant-Id for Cloud / Bearer self-hosted (COGNEE_TENANT_ID); OpenRouter default arcee-ai/trinity-large-thinking:free (OPENROUTER_MODEL override), unconfirmed without key.
- [x] **Jev removed (no sponsor, no credits).** Replaced by a local deterministic threshold gate (clients.local_gate, no API call): promote if candidate pass rate > baseline AND constraint violations did not increase; reject_and_refine if candidate pass rate < baseline OR violations increased; hold otherwise. Same decision labels (promote / reject_and_refine / hold). Ledger fields unchanged in name: choice = decision, confidence = candidate minus baseline pass rate, constraints_prob = violation count after the candidate, utility_score = candidate pass rate; the ledger key is still named jev_gate for compatibility (rename is a small follow-up). The Jev client code and TYPESAFE_API_KEY / TYPESAFE_MODEL env vars are kept but unused; set PROOFLOOP_GATE=jev to re-enable. Edge cases of the rule are unit-checked; the Jev flag path was re-run against harness/mock_sponsors.py.
- [x] Live code paths exercised end to end against harness/mock_sponsors.py (same 2/6 -> 5/6 -> 6/6 -> rollback flow). Not yet run against the real sponsor APIs.
- [x] TRACKING.md committed on feat/proofloop.

## What is still missing
- [ ] Run against real sponsor APIs: Senso, Cognee, OpenRouter (blocked on keys, see below). Live code paths only exercised against harness/mock_sponsors.py.
- [ ] Luma session (consent/judge-applicant checkboxes) is not in the replay suite: slots model values, not checkbox state. Add a checkbox slot kind if Ari wants it in.
- [ ] Optional: an LLM-backed executor (needs OPENROUTER_API_KEY) so pass rates reflect a real model, not the deterministic model.
- [ ] Load the extension in real Chrome and verify chip/proof-table/tab detection (sandbox cannot start Chrome; must be done on Ari's machine).
- [ ] Backup video (90-second script) and two timed dry runs of the 3-minute demo.
- [ ] PR decision (open now or wait until live runs are done).

## Next steps (in order) and blockers
1. BLOCKER: Senso + OpenRouter keys must reach the Kiro sandbox (see Needs from Ari 2). Then: `python3 harness/health.py` (expect senso GREEN, openrouter GREEN, cognee STUB).
2. Run `replay_loop.py --reset --bad-demo` with Senso live and OpenRouter live (LLM proposes the mutation; rule-based mutator is the fallback). Record the pass rates here. They may differ from 2/6 -> 5/6 -> 6/6 if the LLM picks different steps.
3. If Senso live fails, check the first error: field names for POST /org/kb/raw and search are from docs, not yet run live.
4. Ari: load the extension in real Chrome (Needs item 6), then backup video and two timed dry runs.
5. PR decision.

## Needs from Ari
1. **Confirm the phone-number masking** — the real file contained both full phone numbers; Kiro committed a masked copy ([PHONE-PRO], [PHONE-FAMILY]) because boomtick is public. Say so if you want it handled differently. Also confirm you are fine with these staying public in data/sessions.jsonl: onasafari.ddns.net, the AdSense publisher ID (public in ads.txt), and the dhyuti-n Hugging Face dataset URL.
2. **Get SENSO_API_KEY and OPENROUTER_API_KEY into the Kiro sandbox.** Your secrets store is not visible here (both vars are unset, no .env). Either paste the two values in the Kiro chat as text (use rotatable hackathon keys; they stay in a git-ignored proofloop/.env), or run it on your machine: copy proofloop/.env.example to proofloop/.env, fill both, then `python3 harness/health.py && python3 harness/replay_loop.py --reset --bad-demo`. Cognee is optional: with no COGNEE_API_URL the local Cognee stub is used (labeled on screen). TypeSafe key is NOT needed.
3. ~~typesafe/jev-1.14.0 confirmation~~ — moot: Jev removed.
4. **arii/hello skills decision** — Whether to commit the 3 git-ignored skills (lane-coder, independent-tests, caffeinated-guardrails) or keep them git-ignored. They are in skills-local/ but ignored because arii/hello is private and boomtick is public.
5. **PR decision** — Open a PR now on feat/proofloop, or wait until live runs are done.
6. **Real Chrome check (Ari's machine)** — chrome://extensions -> Developer mode -> Load unpacked -> proofloop/extension; run `python3 proofloop/harness/server.py`; open extension/test/demo.html with related-1.html and related-2.html in one window.

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
