# ProofLoop: an observer that warns before a page contradicts your own past sessions

**One line:** ProofLoop is a Chrome extension that watches the sites you turn on and quietly warns when a field, a checkbox or another open tab conflicts with a rule learned from your own past sessions. It never types, fills or submits anything for you.

## Short description (for the form)

Most of the mistakes in Ari's recorded sessions were made by AI agents filling forms for her: San Jose instead of San Francisco on a Vouch signup, sponsor-consent and judge boxes checked on a Luma registration, the friends-and-family phone sent with three job applications. ProofLoop turns those sessions into rules and checks every watched page against them. A loop replays the past sessions with a real LLM, proposes rule changes from the failures and from Cognee recall, keeps only changes that beat measured noise on train and holdout tasks, and stores promoted rule sets in Senso. On the page, a small pill shows how many rules apply to the current task. A warning appears beside the field that conflicts, citing the rule, its version, where it came from and the session it was learned from. The extension can hold one submit while a conflict is open so you can review it.

## What it does

1. **Tasks from sessions.** `harness/tasks.py` asks the LLM to turn each redacted session into a replay task with checks. Every value a check names must appear in that session, so a check cannot reward a value nobody recorded. The suite is reviewed by hand before use (`data/replay_tasks.json`, 3 tasks, reviewed).
2. **Replay with a real agent.** The LLM answers every task under the current rule set, 3 samples per task. String checks score what it would enter; a separate judge call scores "asked instead of guessing" and "no untraceable claims".
3. **Propose.** The mutator sees only train-split failures, the past sessions Cognee recalls for them, and feedback from the page ("Rule is wrong"). It rewrites the whole rule set. A proposal is refused unless it validates against the schema, cites only recalled sessions, and every value it names appears in those sessions.
4. **Gate.** A proposal is promoted only if its train score beats the baseline by more than the measured sampling noise, its holdout score does not drop, and no task that always passed collapses. Otherwise it is held or rejected and the active set stays.
5. **Repeat.** The loop stops when three proposals in a row fail to promote, when every train task passes, or at a 12-proposal cap. Nothing is injected: a rollback in the ledger is a real proposal that lost.
6. **Store.** A promoted rule set goes to Senso and becomes active only after a readback finds it. The backend re-reads the Senso node when Senso is enabled and labels the source on the page.
7. **Watch the page.** The extension runs only on sites turned on from its toolbar button (or all tabs, with one optional grant). It works out the page's task locally (event registration, job application, insurance or service quote, profile edit and others), asks the local backend for the rules for that task, and compares field values locally. It re-reads fields regularly, so values set by an agent, by autofill or by picking a suggestion are caught too.

## What was checked

| Check | Where | Result |
|---|---|---|
| Offline suite (`pnpm run test:proofloop`) | sandbox | 36 Python tests (loop, gate, grounding, server, security) + background contracts + extension contracts + assist eval, green |
| Assist eval | 36 hand-labeled form states (captured Luma and Vouch forms, synthetic job, checkout, profile, blog pages) | precision 1.0, recall 1.0 on the eval rule set |
| Browser e2e | real Chromium, unpacked extension, real backend, fixtures re-captured from the live sites | 13/13 steps |
| Live sites | real luma.com registration dialog and apply.vouch.us, temporary test rule set | city and sponsor-consent warnings shown beside the fields, submit held with no registration request sent, Vouch's picked address ("S Main St San Jose, US-CA 95035") and the family phone flagged, no field or button covered |

A live loop run with promoted rule sets is not recorded in this repository yet. The numbers above are about the page assistant and the loop's code paths, not about how much the loop improves an agent.

## Tools used

- **Cognee (Cognee Cloud)**: recall over the session log. It decides which past sessions the mutator may cite, and can add "from past sessions" context on the page (off by default).
- **Senso**: storage and readback of promoted rule sets; the page cites the Senso node.
- **LLM via Tokens with Taste (local gateway) or OpenRouter**: task generation, the replay agent, the judge and the mutator.
- **Chrome extension (Manifest V3)**: observer content scripts registered per site, a background worker, popup and settings.
- **Python backend and loop**: loopback server with a per-run token, replay loop, gate, ledger.

## Privacy and safety

- The extension runs only where you turn it on. Its permissions are `storage`, `scripting` and `activeTab`, plus optional host grants.
- Field values never leave the browser. Forbidden values arrive as salted hashes and the field value is hashed locally. Real phone numbers live only in a git-ignored file on your machine.
- The backend receives the page origin, the task id and a short list of other open tabs (origin and short title); never paths, query strings, page text or field values.
- Sessions in the repository are redacted (`[PHONE-PRO]`, `[PHONE-FAMILY]`). The loop never reads the private values file.
- The backend binds 127.0.0.1, checks Host and Origin, and needs the token on every API route. UI text is rendered as text in a closed shadow root.

## Honest limits

- The rules are only as good as the recorded sessions: 8 committed sessions, mostly about form filling and verifying claims. On most pages there is nothing to say yet.
- The gate measures replay of past tasks with a small suite. It is a measured result, not a guarantee, and there is no formal verifier.
- An agent driving the browser can click "Submit anyway" just as it clicked Submit. The hold stops silent mistakes, not determined ones.
- Senso readback field names are not confirmed against a live response; if the page reports "could not be confirmed", that read is the likely cause.

## Links

- Code: https://github.com/arii/boomtick/tree/feat/proofloop/proofloop
- Setup, activation and test commands: `proofloop/README.md`
- Plan and milestones: `proofloop/PLAN.md` (section 0)
