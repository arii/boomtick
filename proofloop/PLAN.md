# ProofLoop: plan to build the assistant that was proposed

Status: plan only. Nothing in this document is built yet.
Deadline is not a constraint. Quality is.

## 1. What went wrong

The proposal was a personal assistant extension. It sits on live pages, shows quiet inline chips, pulls constraints from other tabs and from past sessions, and cites the rule it used. A self-improving loop was meant to make that assistant better over time.

What was built is the loop. The extension became a viewer for the loop's ledger. The assistant was never built.

| # | Proposed | Built | Gap |
|---|----------|-------|-----|
| 1 | Inline action chips on live pages, cross-tab context | One chip showing a proof table | No on-page assist at all |
| 2 | Demo climax: refresh the live tab, chip shows v2 badge, surfaces the conflicting constraint from tab 2, cites the Senso rule | Ledger display | Climax absent |
| 3 | Cognee `recall()` on failed tasks drives the mutator | Fixed `CHECK_FIX` map (failed check to step) picks the step | Cognee is reported, never used. Fixes work by construction |
| 4 | Extension reads the active skill from Senso | Senso is write-only (`senso_promote`) | No read path |
| 5 | Gate was TypeSafe Jev. Deterministic gate was risk fallback #2 | Fallback became the only gate | Downgrade |
| 6 | Executor is a real agent run | `agent.py` is a deterministic model of an agent. The LLM only picks one of 4 step names | No LLM answers any task |
| 7 | Open-ended loop | 4 fixed steps. Loop ends when steps run out. 6 tasks never grow. Bad v1.3 is injected | Convergence is not measured |

Root cause: the replay engine was the part that could be tested offline, so it got built, then dressed as the product. Everything below puts the assistant first. The replay engine becomes the quality gate behind it.

## 2. Product definition (what "good" means)

The assistant is a Chrome extension that, while Ari uses a page:

1. Notices what she is doing (editing a form field, reading a claim, a page that matches a past session).
2. Looks up the constraints she has learned before, from her own sessions.
3. Interrupts only when a constraint is about to be violated or is clearly relevant.
4. Says what, why, and where the rule came from (Senso rule id and version, source session).
5. Never acts silently. It proposes, she accepts or dismisses. Dismissals are recorded.

Quality bar:

- A warning is rare, correct, and explained. A false positive costs more trust than a missed warning is worth. Track precision first.
- Latency: the warning appears within 300 ms of a field change. Lookups against cloud services happen on page load and are cached, not per keystroke.
- Private by default: page text and tab content leave the machine only for services she has enabled, after redaction, and never from tabs she has not opted in.

## 3. Target architecture

```
 live page ─ content script ──► background SW ──► local backend (127.0.0.1:8787) ──► Senso (read + write)
   │  field detector            │  tab context      │  /skill     active rule set        Cognee (recall)
   │  chip UI (shadow DOM)      │  rule cache       │  /assist    rule cards for a page   LLM gateway
   │  local matcher             │  (ETag by version)│  /feedback  accept / dismiss
   ▼                            ▼                   ▼
 inline warning            offline-capable      replay engine + ledger  (quality gate, not product surface)
```

Keys stay in the backend. The extension talks only to the local backend. The existing origin allow-list and `PROOFLOOP_EXTENSION_ID` check stay.

### 3.1 The central data model: constraint cards

Today a constraint is a free-text sentence in `sessions.jsonl` (`"City is San Francisco, never San Jose."`). A sentence cannot drive an on-page check. Add a structured card derived from each session constraint:

```json
{
  "id": "rule.city.sf",
  "version": 3,
  "kind": "forbid_value",
  "field": {"semantic": "city", "hints": ["city", "location", "town"]},
  "forbid": ["San Jose", "SJ"],
  "expect": "San Francisco",
  "scope": {"url_match": ["vouch", "lu.ma", "luma.com", "*/apply*"], "page_kinds": ["job_application", "event_signup"]},
  "message": "Your sessions say San Francisco here, not San Jose.",
  "provenance": ["sess_2026_11_16_vouch", "sess_2026_11_16_luma"],
  "senso_node": "…"
}
```

Kinds, in the order they get built:

1. `forbid_value` / `require_value` (city, phone). Deterministic match.
2. `ask_when_missing` (work-type preference). Warns on submit if the field is empty or defaulted.
3. `never_check` (consent and judge-applicant boxes, from the Luma session).
4. `trace_claim` (numbers on a page you are authoring must trace to a run). Needs an LLM or a regex plus a source list. Hardest, built last.

Cards are the unit stored in Senso (one node per rule set version) and the unit Cognee reasons over. Cards are produced from sessions by an LLM extractor, then reviewed by hand once. Review is a one-time cost per card and is the only reliable way to get precision.

### 3.2 Who does what

- **Local matcher (extension, deterministic):** decides whether a field value violates a card. This is what runs on each change. It must not depend on a network call. This is deliberate: the model is not trusted with the warn/no-warn decision, only with finding and writing cards.
- **Senso (read path):** the backend fetches the active rule set version. `GET /skill` returns `{version, cards, senso_node}`. The extension caches by version. A new promotion is visible on the next refresh or poll. This is the "v2 Senso Verified" badge, driven by a real read.
- **Cognee `recall()`:** given a page context (URL, title, field labels, other-tab titles), return the sessions and constraints relevant to it. Used in two places: (a) `/assist` on page load, to pick which cards apply when `scope` is not enough, and to explain "this came from your Vouch session"; (b) the mutator, below. Needs verification of recall latency and quality before anything depends on it.
- **JSONL:** stays the source of truth for sessions. It feeds Cognee ingest and the card extractor. Takeout and Muse sessions enter through the same schema.
- **Replay engine and ledger:** unchanged in role. They measure whether a rule set is good before it is promoted. See section 5.

## 4. The smallest end-to-end slice

**Assist: a city-field warning on a job or event application form.**

This is the Vouch/Luma lesson. It proves every claim in the proposal at the smallest size: structured constraint, Senso read, Cognee recall, on-page UI, cross-session grounding, a version change visible on the page.

### 4.1 What the extension detects

- Inputs and comboboxes whose label, `name`, `id`, `placeholder`, `aria-label` or `autocomplete` indicates a city or location. Classify with a scored matcher (label text and `autocomplete="address-level2"` weigh most). Handle `<label for>`, wrapping labels, `aria-labelledby`, and React-controlled inputs (listen to `input`, `change` and `blur`, not just attribute reads).
- Page kind: URL and title heuristics plus presence of an application form (a `<form>` with a submit button and 3 or more fields).
- Out of scope for the slice: shadow-DOM-heavy widgets, iframes from other origins, address autocomplete popups that set the value programmatically. Record which target pages need these.

### 4.2 What it queries

On page load, one call: `POST /assist {url, title, fields: [{semantic, label}], other_tabs: [{title, url}]}`.

The backend:
1. Reads the active rule set from Senso (cached server-side by version).
2. Calls Cognee `recall()` with the page context. Returns the matching sessions.
3. Returns `{version, senso_node, cards: [...applicable], evidence: [{session_id, excerpt}]}`.

The extension caches the cards for the page. The per-keystroke decision is the local matcher on the cached cards. If the backend is down, the last cached cards still work.

### 4.3 What it shows

When she types or selects "San Jose" in a city field covered by `rule.city.sf`:

```
San Jose  ┌──────────────────────────────────────────────┐
          │ Your sessions say San Francisco here.        │
          │ Rule city.sf v3 · from Vouch, Nov 16         │
          │ [Use San Francisco]  [Keep San Jose]         │
          └──────────────────────────────────────────────┘
```

- Small shadow-DOM chip anchored below the field. No overlay, no modal, no chat.
- "Use San Francisco" sets the value using the native setter plus dispatched `input` and `change` events, so React forms register it. This only happens on her click.
- "Keep San Jose" suppresses the chip for that field and logs a dismissal to `/feedback`.
- No warning when the value is San Francisco, empty, or the field is outside the rule's scope.
- A header badge shows the active rule set version and Senso status ("v2 · Senso verified" only when the node was actually read, otherwise "offline cache").

Second assist added in the same slice if time allows: when the page is a form and another open tab is a profile page with a different value, surface it with the same card UI. That covers the cross-tab claim.

### 4.4 How it is tested

1. **Unit (Node):** field classifier on a corpus of saved label/attribute combinations. Matcher on card x value cases, including `san jose`, `San José`, `SJ`, `San Jose, CA`, and a near miss like `San Jose Street` in an address line (must not fire). These are the cases that decide precision.
2. **Fixture e2e (Playwright with the unpacked extension):** local HTML fixtures `vouch_form.html`, `luma_form.html`, a plain React-style controlled-input form, and a negative fixture (shipping address form, out of scope). Backend runs in stub mode with a seeded rule set. Assert: chip appears on San Jose, not on San Francisco, not on the shipping form, "Use San Francisco" produces a value React reads, "Keep" persists the dismissal.
3. **Version change e2e:** seed Senso stub with v1 (no city rule) and v2 (rule present). Load page on v1: no chip. Promote v2. Refresh: chip appears and the badge reads v2. This is the demo climax as an automated test.
4. **Live test (gated by env):** real Senso node read and real Cognee recall. Assert recall returns the Vouch session for a Vouch-like context, and record latency.
5. **Assist eval (new, separate from skill replay):** a labeled set of saved page snapshots with (field, value, expected warn or not). Report precision and recall for the assist. Target precision of 1.0 on the labeled negative set before enabling by default. Without this there is no evidence the assistant is good, only that the code runs.
6. **Manual check on the real Vouch and Luma pages**, with screenshots recorded in TRACKING.md.

Done means: on the real Vouch application page, typing San Jose triggers the chip, accepting the fix works, the chip cites a Senso rule read at runtime, and promoting a new rule set changes the behavior on refresh with no code edits.

## 5. Making the loop real

### 5.1 Cognee recall drives the mutator

Current: failed check name maps to a step name (`CHECK_FIX`). The mutator cannot propose anything outside that map.

Change:
1. The replay run produces failures: task, answer, failed check, and the tabs.
2. For each failure the mutator calls Cognee `recall(failure_context)` and receives the relevant past sessions and their constraints.
3. The LLM mutator is given the failure, the recalled evidence, and the current rule set. It proposes a change to the rule set: a new or edited constraint card plus the instruction text. Proposals are free-form cards, not a choice among 4 names.
4. Proposals are validated against the card schema. Invalid proposals are rejected and logged.
5. The gate decides (section 5.3).

`CHECK_FIX` is deleted from the live path. A mapping from failure to fix will remain only in the offline mock executor used for unit tests.

Honest risk: if recall returns noise, the mutator gets worse, not better. The ledger must record which evidence each proposal used, so we can tell whether recall helped (compare the same mutator with recall removed, as an ablation).

### 5.2 Real LLM executor

Current: `agent.py` computes the answer from slots. Replace with an LLM call.

Change:
1. Executor builds a prompt from the active rule set (rendered by `skill_prompt.py`, which already exists) plus the task's tabs and query, and asks the LLM to answer.
2. Checks (`must_include`, `must_not_include`, `asks_clarification`) run on the real text. These are cheap and stay deterministic.
3. `no_unsupported_claims` is the weak point: string checks on free text miss paraphrases. Add an LLM judge for it, from a different model than the executor, with a fixed rubric, and report judge agreement against a hand-labeled sample.
4. LLM output varies. Run each task N=3 at temperature 0 (or lowest allowed), score as pass rate, and require a candidate to beat the baseline by more than the noise measured on repeated baseline runs. Cache by (prompt hash, model) to keep cost and flakiness down.
5. Keep `agent.py` as `mock_executor` for offline tests and CI only. Label it so in code and docs.

### 5.3 The gate

TypeSafe Jev is gone, and we will not pretend the old deterministic gate was the design. The gate becomes a layered check on real outputs:

1. Deterministic checks on real LLM outputs (above).
2. Regression: no task that passed on the active version may fail on the candidate.
3. Held-out tasks: a split of tasks the mutator never sees failures from. A candidate must not lose on held-out. This is what catches overfitting.
4. Noise margin from repeated baseline runs.
5. Independent judge for the claim check.

This does not replace a formal verifier and we should say so. It is stronger than the current gate because the thing being measured is a real model answer.

### 5.4 Open-ended, not bounded

- Tasks grow: new sessions (Muse logs, Takeout import, live assist dismissals) become new tasks through `make_tasks.py` with the extractor reviewed by hand.
- "Dismissed warnings" from `/feedback` are a source of both tasks and card corrections. A dismissal is evidence that a rule is wrong or too broad.
- The loop stops when a candidate fails to beat baseline beyond noise for K consecutive proposals, not when a list runs out.
- The bad candidate is whatever the mutator actually produces. The injected v1.3 is deleted. If the demo needs a rollback, it must come from a real failed proposal, recorded in the ledger.

## 6. What stays, changes, and is added

**Stays**
- `replay_loop.py`, `replay_gate.py`, the ledger and `state/`: the quality gate and audit trail. Its UI moves out of the chip into the options page and `dashboard.html`.
- Senso write path (`senso_promote`) and polling.
- `sessions.jsonl`, schema, `validate.py`, redaction rules, `make_tasks.py`, `import_takeout.py`, candidates.
- Server origin allow-list, extension ID check, health probes.
- `skill_prompt.py` and prompt sync (becomes secondary: the same rule set also feeds an external agent).

**Replaced**
- Chip proof table: replaced by inline assist chips. The ledger view moves to the options page.
- `agent.py` as primary executor: replaced by the LLM executor. Kept as the offline mock.
- `CHECK_FIX` in the live mutator: replaced by recall-driven proposals.
- The injected bad v1.3: removed.
- Free-text constraints as the only form: supplemented by cards.

**Added**
- Constraint card schema, extractor, and a review step.
- Senso read path: `GET /skill`, caching, version badge.
- Cognee `recall()` in `/assist` and in the mutator.
- Extension: field detector, local matcher, shadow-DOM chip, tab context collector with per-tab opt-in, rule cache, `/feedback`.
- LLM executor, judge, repeated runs, held-out split.
- Assist eval set of saved pages.
- Playwright e2e suite.

## 7. Phases in priority order, with honest sizing

Estimates are for one person working focused days, including debugging against real pages and real services. They carry the most uncertainty where they depend on Cognee and on third-party form markup.

| Phase | Build | Est. | Why this order |
|-------|-------|------|----------------|
| 0 | Reframe docs (README, SUBMISSION, TRACKING) to describe the current build honestly and point to this plan | 0.5 d | Stops misdescribing the project |
| 1 | Card schema, LLM extractor over `sessions.jsonl`, hand review of the 8 existing constraints, validation | 1 to 1.5 d | Everything else consumes cards |
| 2 | Slice step A: field detector, local matcher, shadow-DOM chip, fixtures, unit tests, matcher precision cases. Backend serves seeded cards, no cloud yet | 2 to 3 d | Proves the on-page experience, the hardest unknown (real form markup) |
| 3 | Slice step B: Senso read path, `/skill`, version badge, refresh behavior, version-change e2e | 1 to 1.5 d | Delivers the demo climax and read path |
| 4 | Slice step C: Cognee recall in `/assist`, evidence in chip, latency and quality measurement, fallback when recall is slow | 1 to 2 d | Validates the Cognee claim. If recall is poor, find out here |
| 5 | Assist eval set and precision report, real-page checks on Vouch and Luma, `/feedback` | 1.5 to 2 d | Evidence the assistant is good |
| 6 | LLM executor, repeated runs, judge, held-out split, noise margin, mock executor kept | 2 to 3 d | Makes the loop honest |
| 7 | Recall-driven free-form mutator, schema-validated proposals, evidence in ledger, recall ablation | 2 to 3 d | Makes Cognee drive the loop |
| 8 | Task growth from dismissals, Takeout and Muse sessions, stop-on-convergence rule | 1.5 to 2 d | Open-ended loop |
| 9 | More assists: phone card, `ask_when_missing`, consent checkboxes, cross-tab value mismatch | 3 to 4 d | Breadth after the first is proven |
| 10 | `trace_claim` assist for pages she is authoring | 3 to 5 d | Hardest, least certain, last |

Totals: the slice (phases 0 to 4) is about 6 to 9 working days. The full vision through phase 9 is about 3 to 4 weeks. Phase 10 is open-ended research. Do not describe the project as finished before phase 5, because before then there is no measured evidence the assistant helps.

## 8. Risks and open questions

- **Cognee recall:** latency and relevance are unmeasured. The earlier silent-add incident (200 response, nothing stored) shows ingest can fail without errors. Phase 4 starts with a probe, and the design degrades to scope-only matching if recall is poor, which weakens the "Cognee drives it" claim and must be reported if so.
- **Form markup:** Vouch and Luma may use custom components that defeat label-based detection. Phase 2 starts with saved snapshots of both pages to decide this early.
- **False positives:** a "city" rule scoped too broadly will fire on shipping forms. Scope fields and the negative set are mandatory, not optional.
- **LLM variance and cost:** N=3 runs over a growing task set multiplies calls. Caching and a small held-out set manage this. Gateway rate limits are unmeasured.
- **Privacy:** sending page and tab content to cloud services needs per-tab opt-in, redaction before send, and a visible indicator. Raw transcripts remain out of the repo.
- **Judge reliability:** an LLM judge can be wrong in the same direction as the executor. Use a different model and hand-label a sample to report agreement.
- **Gate strength:** with Jev gone there is no formal verification. Claims about the gate must say "measured on N tasks with a noise margin of X", not "verified".
- **Scope of the "personal" claim:** most of the 183 Takeout conversations are writing and resume work. The code-related subset is about 49. The assistant's first rules come from form-filling and verification lessons. Broader personal-assistant behavior is not evidenced by current data.

## 9. Immediate next step when building starts

Phase 0 and phase 1, then capture HTML snapshots of the Vouch and Luma application pages for the phase 2 fixtures. That settles the largest uncertainty (how real forms behave) before any matcher code is written.
