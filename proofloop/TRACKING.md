# Historical planning record, not current activation instructions

Patch prepared November 20 (PR #1350): README.md describes the local Replay Gate, explicit activation and schema-v2 state. Earlier key transfer, automatic credential loading and live-mode directions below are historical and superseded by that patch. Do not send secrets through chat. No live run or publication is established. Unique planning material is retained below, not treated as authorization.

# ProofLoop — Tracking Document

Live status for the Personal Agents Hackathon build (Fri Nov 20, 2026). Kiro updates this file as work progresses. Ari's CLI agents (agy, Copilot, Muse CLI) read this file to pick up work interactively. Do not delete this file. Keep it current.

Last updated: 2026-11-20 02:55 PM PT (by Kiro). Started the assistant rebuild in PLAN.md: city-field warning slice built and tested on fixtures and on the live Luma dialog. PR not opened.

## Repo and branch
- Repo: arii/boomtick (no new repo).
- Directory: proofloop/
- Branch: feat/proofloop — https://github.com/arii/boomtick/tree/feat/proofloop
- PR #1350 and #1351 merged into feat/proofloop (not main). A PR from feat/proofloop to main is not open; decide after the live checks.

## Current status (latest)
- **Rebuild per PLAN section 0 (M1 to M6), 2026-11-20.** Code done and tested offline and on the live sites with a test rule set. Live loop not run: no Senso, Cognee or provider keys in the sandbox, and TWT (127.0.0.1:8000 on Ari's machine) is unreachable from it.
  - M1 auto-repeat loop: `replay_loop.py` runs real LLM answers (3 samples) on generated tasks, judge for clarification and claim checks, mutator from train failures + recall + feedback, gate with per-task sampling noise and a holdout split, stops on 3 non-promoting proposals or all-pass, cap 12. Deterministic executor, CHECK_FIX, slots, injected v1.3, stubs and hand-written cards removed.
  - M2 conflict warnings: forbid_value (hash-matched), keep_unchecked, confirm_choice (at submit), cross-tab value differences.
  - M3 observer: never writes to the page; polling catches values set by agents, autofill and suggestion picks; optional one-time submit hold.
  - M4 task determination: local classifier over `schemas/tasks.json` (no hostnames); rules scoped by task; runs only on sites turned on from the toolbar.
  - M5/M6: Cognee recall required unless `--no-recall`; Senso promotion with readback; the backend re-reads the Senso node when Senso is enabled and labels the source.
  - Live sites (`extension/test/live_sites.cjs --test-rules`, run from the sandbox): Luma city warning beside the field, consent box flagged, submit held, no registration request; Vouch suggestion pick ("S Main St San Jose, US-CA 95035") flagged, family phone flagged; pill and chips cover no control. Fixes found only on the live sites: address format after a suggestion pick, the pill covering Vouch's cookie-banner buttons, outlines drawn over a field hidden behind the banner.
- **Milestone 2 (field detector, PLAN 2.1 and 4.1): passes on the live site, awaiting check-in.** `extension/test/live_detect.cjs` runs the shipped `assist/detect.js` on live luma.com/personalagenthack (Request to Join dialog) and live apply.vouch.us. Luma: city question, judge checkbox, sponsor-consent checkbox, submit "Request to Join"; 7 other inputs correctly ignored. Vouch: address combobox (placeholder only), Phone Number, 2 checkboxes (no-website, terms), submit "Start Application" (type=button, found by text); 9 other inputs ignored. Fixtures re-captured from the live pages (`capture_fixtures.cjs`): 10 and 13 inputs, same as live. Not done yet: milestone 3 (cards for phone and checkboxes), milestone 4 (pre-submit panel).
- **Assistant slice (PLAN.md phases 0 to 2, plus a local /skill for phase 3).** Run the backend once, then paste `state/server_token` into the extension options page and reload the extension.
  - Built: constraint cards (`data/cards.json`, schema `schemas/cards.schema.json`, hand-reviewed, 2 cards), field detector (`extension/assist/detect.js`), deterministic matcher (`assist/match.js`), inline chip with Use San Francisco and Keep (`assist/assist.js`), `/skill`, `/assist` (origin and path only), `/feedback` (card id and action only).
  - Security from PLAN section 9: per-run bearer token on every API route (closes the missing-Origin hole, S2), JSON content type and 16 KB body limit, manifest narrowed from all sites to Luma and Work at a Startup (S1), closed shadow root and text-only rendering with a source lint (S1), atomic writes for state, ledger and task files (S6).
  - The old ledger chip is off by default (options page toggle).
  - Tests: 62 Python, 8 + 1 Node offline suites, and `extension/test/e2e_assist.cjs` (real Chromium, unpacked extension, real backend, 10 scenarios including the v1 to v2 rule change on refresh). `extension/test/live_luma.cjs` passed against the real luma.com/personalagenthack dialog (types into the city field, never submits).
  - Snapshots: `extension/test/fixtures/luma_registration.html` (city field identified only by its label, no autocomplete) and `vouch_apply.html` (apply.vouch.us has no city field, only a placeholder-only address combobox). The Vouch form from the Nov 16 session is not identified, so Vouch is out of scope in the cards.
  - Not built yet: Senso read path (cards come from the local file and the chip says so), Cognee recall in /assist (`recall.mode` is reported as `none`).
- **CLI agent session (from its transcript, commit 51887d1, pushed to feat/proofloop):**
  - **Cognee is now LIVE.** Cognee Cloud URL, key and tenant ID are in Ari's `.env`; `PROOFLOOP_LIVE_SERVICES=senso,twt,cognee` and `PROOFLOOP_ALLOW_SESSION_UPLOAD=1`. `--probe-live`: Senso GREEN, LLM GREEN (via the gateway), Cognee GREEN, gate LOCAL. The replay ingests the 8 sessions and recalls 6/6 tasks. This supersedes every earlier "Cognee STUB" line below.
  - **Latest live run (state dir `proofloop/state/live-twt`):** v0 2/6; v1.1 6/6 promoted (LLM mutation via the gateway, Senso readback live); injected v1.3-bad 4/6 rejected and rolled back; active v1.1. The chip shows the same table.
  - **Bugs found and fixed by the CLI agent** (all in 51887d1, 39 tests pass):
    1. Cognee Cloud answered 200 to `add` but stored nothing, because sessions were sent as plain form fields (`data_ids` was empty). They are now uploaded as files under `data`; the client fails if nothing is stored and waits for cognify before searching.
    2. Senso promotion failed at readback on every replay: the readback searched a title shared with earlier uploads. Titles now carry the cycle ID and a timestamp.
    3. The health probe asked for 1 token, which reasoning models return empty. It now asks for 64.
    4. Env typo: the files had `CLOUDFARE_*` instead of `CLOUDFLARE_*`, so the gateway saw no Cloudflare key. Names were fixed in `.env` and `proofloop/.env` (values untouched, backups deleted).
  - **Side effects to know about:** `pip install -e tokens-with-taste` upgraded `opentelemetry-api` in the repo's `.venv`; pip warns it conflicts with versions pinned by `semgrep` and `boomtick-cli`, which may misbehave there. The probes and replays left synthetic test data in Ari's Senso account and in the Cognee Cloud datasets `proofloop_healthcheck` and `proofloop_sessions`. An 8-character prefix of the Cognee key and tenant ID appeared in CLI agent output: rotate the key after the hackathon.
  - **Replay timing with Cognee live:** the whole run takes about 20 to 70 seconds (cognify wait plus the LLM call). Time the dry runs with live services, or use `bash proofloop/demo.sh` for the always-offline run.
  - **Session data from today:** four redacted excerpts from the CLI session are in `data/candidates/sessions.2026-11-20-build.jsonl` (extension ID length accepted wrongly, Cognee 200 with nothing stored, Senso readback title collision, env variable typo). They validate against the sessions schema but are NOT wired into the demo suite, which stays at the six tasks above so the demo numbers do not move. To use them, derive tasks with `harness/make_tasks.py` and re-run.
  - **The raw transcript is not in the repo on purpose:** it contains private tab contents (messaging and email), names and key fragments.
- **Chrome check result (reported by Ari, real Chrome, extension ID `cbpokmfdbbcpgaookmhdgnbdcgkjkodl`):**
  - **Chip:** green banner at the bottom: "ProofLoop v1.1: deterministic replay (6/6 replay pass) - 5 local tabs shown".
  - **Proof table (expanded):**

    | Version | Pass | Delta | Gate | Senso node | Status |
    |---|---|---|---|---|---|
    | v1.1 | 2/6 -> 6/6 | +0.67 | promote | 821c47a2-506e-4362-95b5-3af669263bc4 | promoted (green) |
    | v1.3-bad | 6/6 -> 4/6 | -0.33 | reject_and_refine | - | rolled_back (red) |

  - **Sequence:** v1.1 goes directly to 6/6 in this live run, because the LLM mutation (through the Tokens with Taste gateway) proposed all the missing steps in one cycle. This is the case the `SUBMISSION.md` sentence about the LLM reaching 6/6 in a single cycle describes. The deterministic rule-based sequence (2/6, 5/6, 6/6) is a separate run.
  - **Other tabs (local opt-in)** listed: 127.0.0.1:8787/status, the Gemini hackathon page (twice), (9) WhatsApp, Examine Attached Files, Kiro Web.
  - **Services shown:** Cognee enabled (unverified), Senso enabled (unverified), Mutation LLM via local Tokens with Taste gateway enabled (unverified). The "unverified" wording is the chip's standing label for any enabled service; the readback line is the live evidence for Senso.
  - **Footer lines:** "Measured deterministic replay only. No page data sent to backend or sponsors." and "Retrieval readback: live".
  - **Flags for the demo and video:**
    - **Personal tabs are visible in the chip.** The related-tabs list shows (9) WhatsApp and other tab titles. Close every non-demo tab, or turn the related-tabs option off, before the dry runs and before recording.
    - **Cognee is live now**: re-run `health.py --probe-live` before the demo or video to see it GREEN, and say "live Cognee Cloud" only if the probe and run on that day show it.
    - **Numbers for the submission:** if the live run is what gets shown in the demo and video, quote 2/6 -> 6/6 (v1.1 promoted) and 6/6 -> 4/6 (v1.3-bad rejected and rolled back), and say the LLM proposed the steps.
- **Services restarted (reported by the CLI agent; only the two services were restarted):**
  - **ProofLoop backend:** 127.0.0.1:8787, pid 36873, dashboard HTTP 200, `/status` OK, reading state dir `proofloop/state/live-twt`, started with `PROOFLOOP_EXTENSION_ID=cbpokmfdbbcpgaookmhdgnbdcgkjkodl`.
  - **Tokens with Taste gateway:** 127.0.0.1:8000, pid 36872, `/v1/models` HTTP 200.
  - **Status:** Senso live, LLM live (via gateway), gate local; Cognee has since gone live (see CLI agent session above).
  - **Chip in real Chrome: CONFIRMED working by Ari** (see "Chrome check result" above). The earlier "backend unreachable" and "No ledger entries" messages are gone; the backend fetch works with the extension ID.
  - **Note on the numbers:** the live run reaches 6/6 at v1.1, not the 5/6 then 6/6 of the rule-based mutator. That is expected when the LLM (gateway) proposes all the missing steps in one cycle. The Replay Gate rules are the same; only the mutation proposal differs. Narrate whatever sequence the ledger shows. `SUBMISSION.md` and the video must quote the numbers from the final run that is actually shown.
- **`health.py --probe-live` result (reported by the terminal agent on Ari's machine):**
  - **Senso: GREEN.** `GET /org/me` succeeded, so the key works. By design this does not prove ingest or search. Separately, the earlier live replay got a Senso readback that found content.
  - **LLM (mutation): GREEN, via the Tokens with Taste gateway.** The gateway is running now, so the mutation can be LLM-proposed. Pass rates are unchanged in principle (the rule-based mutator gives the same sequence); if the LLM proposes a different step set the sequence may differ, so re-check the printed pass rates on the next run.
  - **Cognee: STUB at that time** (since changed to GREEN, see CLI agent session). **Gate: LOCAL** deterministic Replay Gate.
  - **Live retrieval: CONFIRMED** by the chip panel ("Retrieval readback: live") and a real Senso node ID on the promoted entry (not `stub-node-*`). In this live run the active version is v1.1 (there is no v1.2 entry).
- **Replay loop, run locally by Ari with Senso live (reported; Kiro has no keys and did not reproduce it):** v0 2/6, v1.1 5/6 promote, v1.2 6/6 promote, injected v1.3-bad 4/6 reject_and_refine and rollback, active v1.2 6/6. Ledger at `proofloop/state/proof_ledger.json` (git-ignored, local to Ari's machine). To confirm Senso was really live, not the stub: the promoted entries' `senso_kb_node_id` should NOT start with `stub-node-` and `retrieval.mode` should be `live`.
- **Backend:** running on 127.0.0.1:8787 with `PROOFLOOP_EXTENSION_ID=cbpokmfdbbcpgaookmhdgnbdcgkjkodl` (32 characters, valid format).
- **Tokens with Taste gateway:** was not running at the earlier check; now running and probed GREEN (see above). `twt` installs from `tokens-with-taste/` into its own environment, not into `proofloop/.venv`, and ProofLoop calls it over HTTP at 127.0.0.1:8000, so a ModuleNotFoundError for `twt` in `.venv` is expected and harmless.
- **demo.sh:** ran in offline mode and completed.
- **Kiro checks this turn (no keys, no Chrome):**
  - Real server with the extension ID: `/augment` and `/status` return 200 for `chrome-extension://cbpokmfdbbcpgaookmhdgnbdcgkjkodl`; a different extension ID, a web-page origin and a bad Host header all return 403; `POST /config` returns 410. With no `PROOFLOOP_EXTENSION_ID` set, the extension origin gets 403 and the chip would say backend unreachable.
  - Real `background.js` plus real `content.js` run against the real server in a simulated browser: chip renders ("ProofLoop v1.2: deterministic replay (6/6 replay pass)"), the proof table expands with the three ledger rows, dismiss works, and related tabs show 0 with the opt-in off and 2 with it on (the chrome:// tab is excluded).
  - The extension ID does not appear in extension code and cannot: Chrome derives it. It is configured only through `PROOFLOOP_EXTENSION_ID` on the backend.
  - Branch is merge-ready against main: 0 commits behind, no conflicts, 36 files (2 outside `proofloop/`: `package.json`, `.fallowrc.json`), no secrets or phone numbers in tracked files. PR is drafted but NOT opened.

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
- [x] Live retrieval confirmed: the chip shows "Retrieval readback: live" and real Senso node IDs on the promoted entries.
- [ ] Luma session (consent/judge-applicant checkboxes) is not in the replay suite: slots model values, not checkbox state. Add a checkbox slot kind if Ari wants it in.
- [ ] Optional: an LLM-backed executor (needs OPENROUTER_API_KEY) so pass rates reflect a real model, not the deterministic model.
- [x] Extension loaded in real Chrome: chip, proof table, local tab list and live readback confirmed by Ari.
- [ ] Backup video (90-second script) and two timed dry runs of the 3-minute demo.
- [ ] PR decision (open now or wait until live runs are done).

## Submission
- **Submission text:** `proofloop/SUBMISSION.md` (short form description, what it does, demo results, tools, privacy, honest limits, links). Edit before submitting if any detail differs from what actually ran: it says Cognee has an API client plus a built-in local graph (update if a live Cognee endpoint was used), and that Senso stores and reads back promoted skills (true only if the Senso run was live, see Current status).
- **Still to add:** link to the backup video once recorded.
- **PR:** drafted, not opened. Title and body are in the Kiro chat history and `/projects/sandbox/.pr/` in the Kiro sandbox. Kiro opens it on Ari's go (squash merge).

## Chrome troubleshooting (chip not appearing)
- **Where it injects:** every top-level `http://` and `https://` page, at document idle. Not on `chrome://` pages (including the New Tab page), the Chrome Web Store, `file://` pages, PDFs, or inside iframes. Tabs that were already open when the extension was loaded or reloaded need a page reload; new tabs and navigations pick it up automatically.
- **What it looks like:** a dark green pill in the bottom-right corner, 16px from the edges, on top of the page (maximum z-index). It reads "ProofLoop v1.2: deterministic replay (6/6 replay pass) - N local tabs shown". Click it to open the proof table; the small x dismisses it for that page.
- **Related-tabs opt-in is NOT needed** for the chip. With it off the chip just says "0 local tabs shown".
- **Chip shows an error but the dashboard loads in a normal tab:** the extension uses `http://127.0.0.1:8787` (fixed in `background.js` and `options.js`, allowed in the manifest), so the address is right. The extension request carries `Origin: chrome-extension://<ID>`; the backend returns 403 unless started with `PROOFLOOP_EXTENSION_ID=<that exact ID>`. A normal tab sends no such origin, so it works. Fix: stop the backend and restart it as `PROOFLOOP_EXTENSION_ID=cbpokmfdbbcpgaookmhdgnbdcgkjkodl python3 proofloop/harness/server.py` (the chip text and the server's stderr now print the exact line), then reload the page. Also check the server is on port 8787; the extension cannot use another port.
- **Backend unreachable or 403:** the chip still appears and says "ProofLoop: no data (...)" with the error. A 403 means the backend was started without `PROOFLOOP_EXTENSION_ID` equal to the ID on the chrome://extensions card.
- **No chip at all** now means the script did not run: wrong page type, page not reloaded, extension disabled or errored on load. After the fix (content.js), a dead background worker also shows a chip instead of nothing.

Exact steps:
1. Start the backend with state present: `cd proofloop/harness && python3 replay_loop.py --reset --bad-demo` (same `PROOFLOOP_STATE` as the server), then `PROOFLOOP_EXTENSION_ID=cbpokmfdbbcpgaookmhdgnbdcgkjkodl python3 server.py`. Check `curl http://127.0.0.1:8787/status` prints JSON.
2. chrome://extensions: Developer mode on. Load unpacked and select the `proofloop/extension` folder (the one that contains `manifest.json`). The card must show ID `cbpokmfdbbcpgaookmhdgnbdcgkjkodl`, be enabled, and have no red "Errors" button. Click the reload arrow on the card after any code change.
3. Open a NEW tab at http://127.0.0.1:8787/ (or https://example.com). Look at the bottom-right corner. Click the chip to expand the proof table.
4. If nothing shows: on that page open DevTools, Console, and look for `[ProofLoop] content script running`. Or run `document.getElementById('proofloop-chip-host')` in the console: null means the script did not run (reload the page, check the page type and that the extension is enabled); an element means it ran. On the chrome://extensions card click "service worker" to see background errors.

## What the loop is and is not (assessed 2026-11-20, from the code)
- **Is:** a bounded propose, replay, gate, promote loop (`replay_loop.py`, default `--max-cycles 4`). A promoted candidate becomes the new baseline, and the next cycle proposes changes from that skill's remaining failures. It stops when all tasks pass, when no change is available, when the gate rejects or holds, or at the cycle cap. A second run on an already-passing skill does nothing.
- **Is not open-ended improvement.** The only thing a mutation can change is which of 4 fixed step names are in the skill (`agent.KNOWN_STEPS`). The rule-based mutator maps a failed check to its step through a fixed table (`CHECK_FIX`). The LLM path may only pick from the same 4 names (anything else is dropped). After at most three additions nothing is left to add, so the loop ends because the vocabulary is used up, not because it found no further improvement. There is no step or rule generation and no rewriting of prompt text.
- **Fixed inputs.** The six tasks come from a committed file and do not grow. Cognee recall is reported but does not change the suite. Senso is written to and read back to gate activation but never read as input to a later round.
- **The injected bad cycle is scripted** (`--bad-demo` drops the grounding step). It shows the gate rejecting a regression; it is not something the loop discovered.
- **The executor is a deterministic model, not an agent run.** `agent.run_task` builds an answer string from each task's slots: with `ground_in_related_tabs` it substitutes the slot's `source_hint`, with `ask_when_unstated` it emits "Clarify: ...", and so on. The `baseline` value is copied from what the real session got wrong. The checks are string tests on that output. No LLM or real agent produces the answers. The LLM is used only to choose among the 4 step names, and that choice is replayed through the same model.
- **Partly built in.** Kiro wrote each task's slots and hints and the check-to-step table, so the right steps fix the right tasks by construction. The pass counts are real computations, but they show the gate and ledger working, not that an agent improved.
- **What the demo honestly shows:** replay, per-check gate, promote and rollback on a fixed six-task set, with live Cognee, Senso and an LLM in the pipeline, plus a prompt block rendered from the promoted skill.
- **What changed today:** after each run the active skill is rendered into `state/.../active_prompt.md` (rules for the steps in the skill, plus the constraints of tasks that pass). `--sync-prompt PATH` (or `PROOFLOOP_PROMPT_TARGET`) writes that block into an agent instruction file between PROOFLOOP markers, only for `.md/.mdc/.txt` files, never `.env` or `.git`, and never from an unpromoted v0. A rollback leaves the previous block. The backend serves it at `/prompt`; the chip and dashboard have a copy button. The rules are fixed text per step, so this makes the output usable, not smarter.
- **A real loop (post-hackathon):** (1) replace `run_task` with a real LLM call that answers each task with the rendered prompt and keep the same checks; (2) let the LLM rewrite or extend the prompt text from failing outputs instead of picking step names; (3) repeat until no improvement for k rounds or a budget is hit, replaying each candidate more than once because LLM output varies; (4) keep a held-out task split to avoid overfitting; (5) feed new tasks from fresh session logs (see `data/candidates/`) each round. Roughly 250 to 400 lines plus tests, and several hours to make stable. It is not safe to do before the 4:30 PM deadline.

## Timeline (PT)
- Now to 2:30: Ari confirms the chip in Chrome. Kiro fixes anything it reports.
- 2:30 to 3:00: two timed dry runs of the 3-minute demo (fill in the log below).
- 3:00 to 3:55: record the 90-second backup video, add the link to `SUBMISSION.md`. Video done by 3:55.
- 3:55 to 4:10: final check of `SUBMISSION.md` numbers against the last run, submit. Hard deadline 4:30.

## Pre-flight (before each dry run, before recording)
1. Backend up with the ID: `curl -s http://127.0.0.1:8787/status` returns JSON. Gateway up: `curl -s http://127.0.0.1:8000/v1/models` returns 200.
2. Clean browser window with ONLY demo tabs: the dashboard `http://127.0.0.1:8787/` plus two related tabs (for example the repo page and `proofloop/SUBMISSION.md` on GitHub). With the related-tabs option on, the chip and panel list other tab titles, so close personal tabs first. Related-tabs option on in the extension settings.
3. Terminal shows no secrets: keys exported in the shell beforehand, never `echo`ed, no `.env` or `env` output on screen. Large font, one terminal for the run.
4. Pre-run once so a fallback ledger exists: `PROOFLOOP_LIVE_SERVICES=senso,twt PROOFLOOP_STATE=proofloop/state/live-twt python3 proofloop/harness/replay_loop.py --reset --bad-demo`. The backend reads `live-twt`, so the chip and dashboard always show that finished run.
5. Offline fallback if Senso or the gateway misbehaves on stage: `bash proofloop/demo.sh` (always offline, labeled stub, deterministic 2/6, 5/6, 6/6, 4/6 rejected). Say plainly that it is the offline stub.

## Demo script (3 minutes)
Live runs write new content to Senso each time (small credit use). Run the on-stage replay into its own state dir so the chip keeps showing the pre-run ledger: `PROOFLOOP_STATE=proofloop/state/demo-run`.

| Time | Show | Say / point at | Command |
|---|---|---|---|
| 0:00-0:35 | A normal web page with the quiet chip bottom-right. Click it: proof table. | "No chat box. ProofLoop lives on the page. The chip shows the active skill version and the replay record: each version, pass count, gate decision, Senso node, status. It also shows my other tabs, locally only." | none (open the dashboard tab) |
| 0:35-1:15 | Terminal: baseline replay. | "These six tasks come from my real past sessions: wrong city, wrong phone number, fabricated numbers. The baseline skill passes 2 of 6, and each failure names the check it broke." | `PROOFLOOP_LIVE_SERVICES=senso,twt PROOFLOOP_STATE=proofloop/state/demo-run python3 proofloop/harness/replay_loop.py --reset --bad-demo` (let it run; the baseline prints first) |
| 1:15-2:15 | Same terminal: mutation, gate, Senso. | "It proposes a new skill version (here the LLM through a local gateway). The local Replay Gate decides with plain rules: promote only if more tasks pass and no passing check breaks. No model decides promotion. Then Senso stores it and we read it back before it goes live." | same run, lines `[4]` to `[7]` |
| 2:15-3:00 | Terminal: the injected bad version; then the chip/proof table. | "A deliberately bad version drops to 4 of 6. The gate rejects it and rolls back; the active skill is unchanged. ProofLoop accepts a change only when replaying your past tasks shows more of them pass with no regression." Close on the proof table row marked `rolled_back`. | same run, line `[8]`; click the chip again |

Rules for the narration: quote only numbers on screen; say "deterministic replay on six tasks", not "improves the model"; if a service shows `stub`, say so.

## Dry run log (fill in)
| Run | Start | Duration | Sequence shown | Chip ok | Issues |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
Target: under 3:00, two clean runs in a row.

## Backup video checklist (90 seconds, done by 3:55 PM)
- [ ] Screen recorder ready (macOS Shift-Cmd-5, Loom, or OBS), 1080p, microphone check, notifications off, do-not-disturb on.
- [ ] Pre-flight above done; clean window; no secrets, no personal tabs, no password manager popups.
- [ ] Script (about 90 s): 0:00-0:12 "Personal agents live in a chat box and forget what went wrong." Show a page with the quiet chip. 0:12-0:30 click the chip: proof table, local tabs. 0:30-0:55 terminal: baseline 2/6 with the failing checks. 0:55-1:15 mutation, Replay Gate promote, Senso readback, result. 1:15-1:30 bad version rejected and rolled back; end card "ProofLoop: Cognee memory, Senso proof store, local Replay Gate. No chat. Just proof."
- [ ] One take is fine; if it fails, use the offline stub run and say "offline stub".
- [ ] Export, watch it once with sound, check for secrets or personal tab titles.
- [ ] Upload (YouTube unlisted or Drive link anyone can view), test the link in a private window.
- [ ] Add the link to `proofloop/SUBMISSION.md` and the submission form. Keep a local copy of the file as backup.

## Next steps (in order) and blockers
Activation rules: `.env` is NOT read. Export real environment variables and opt in with `PROOFLOOP_LIVE_SERVICES`. Do not send secrets through chat.
1. ~~Chrome check (Ari)~~ DONE and confirmed (see Current status). Before recording: close personal tabs or turn off the related-tabs option.
2. **Two timed dry runs** using the demo script and pre-flight above. Log them in the table.
3. **Backup video** by 3:55 PM using the checklist.
4. **PR decision (Ari):** not opened. Kiro opens it from feat/proofloop to main on Ari's go (squash merge).
5. **Submission** by 4:30 PM PT, with `SUBMISSION.md` numbers matching the final run and the video link added.

## Live-run log
- First live run (Ari's machine, before PR #1350): Senso `403 error code: 1010` (Cloudflare blocks the default Python User-Agent; fixed with a custom User-Agent) and OpenRouter `404` retired model (default now `openrouter/free`). Cycle 1 matched the offline result (v1.1 5/6) before stopping at the Senso call.
- Tokens with Taste gateway checked in the build sandbox with no provider keys: `twt sync` OK, `twt serve` OK, chat returns 503 listing missing credentials, harness falls back to rule-based and the offline results are unchanged (2/6, 5/6, 6/6, 4/6 rejected). Successful provider completion not yet exercised.
- Ari's machine, after PR #1350/#1351 merged: full replay loop with Senso live completed, 2/6 -> 5/6 -> 6/6, injected regression 4/6 rejected and rolled back, active v1.2. Gateway not running, rule-based mutator used. demo.sh offline run completed. (Reported by Ari.)
- `--probe-live` on Ari's machine: Senso GREEN (`GET /org/me`), LLM GREEN via the Tokens with Taste gateway, Cognee STUB, gate LOCAL. (Reported by the terminal agent.)
- Real Chrome (Ari): chip works. Proof table shows v1.1 2/6 -> 6/6 promoted (Senso node 821c47a2-506e-4362-95b5-3af669263bc4, readback live) and v1.3-bad 6/6 -> 4/6 rolled back. Live-run sequence is v1.1 straight to 6/6 (LLM mutation).

## Needs from Ari
1. **A provider key for the gateway, or Ollama** (optional, only for an LLM-proposed mutation): Groq, Google, NVIDIA, Mistral or SambaNova free key exported in the shell that runs `twt serve`. Without it the rule-based mutator is used and every result is unchanged.
2. **SENSO_API_KEY exported in your shell** for live Senso (optional; offline stub otherwise, labeled on screen).
3. **Real Chrome check** (Next steps 4) and the demo rehearsals (5).
4. **Confirm phone masking** in data/sessions.jsonl ([PHONE-PRO], [PHONE-FAMILY]); the unmasked original is private and git-ignored.
5. **Decision:** whether and when to open a PR from feat/proofloop to main.

## Task checklist (from the ProofLoop doc)
- [x] Task 1 — Curate JSONL + replay_tasks.json (11:00–11:20 AM). Status: done. Real sessions validate; 6 tasks derived.
- [ ] Task 2 — Browser-first key entry + health checks (11:20–11:40 AM). Status: not started (needs keys from Ari or stub go-ahead).
- [x] Task 3 — Cognee ingestion smoke test (11:40 AM–12:10 PM). Status: DONE on live Cognee Cloud (probe GREEN; 8 sessions ingested; 6/6 tasks recalled).
- [ ] Task 4 — Core propose/replay/gate loop, replay_loop.py (bounded, see "What the loop is and is not") (12:10–1:10 PM). Status: stub mode complete on real sessions (2/6 -> 5/6 -> 6/6, rollback works). Live mode needs keys.
- [x] Task 5 — Minimal MV3 Chrome extension (1:10–1:55 PM). Status: DONE. Loaded in real Chrome and confirmed by Ari: chip, proof table, local tab list, live readback.
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
