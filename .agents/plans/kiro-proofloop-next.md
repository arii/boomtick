# Kiro next instruction — ProofLoop (send when session reachable)

Session: https://app.kiro.dev/session/80013a4a-ee1c-4caf-85e3-7218e0e32149
Branch: `feat/proofloop`, HEAD `89c3b5b`. Do not re-send earlier standing
instructions (auto-repeat loop, conflict-warning slice only, observer
extension, task determination, live Cognee with facer key, real Senso and
TWT, no hardcoding) — those stand.

## Task: resolve the `tabs` permission contract failure

HEAD added `"tabs"` to `proofloop/extension/manifest.json` permissions
(for `chrome.tabs.query` in `watchAll` and `chrome.tabs.get` in
`onActivated`), but `proofloop/harness/tests/test_assist.cjs:90` asserts
`!mf.permissions.includes('tabs')`. Result: `pnpm run test:proofloop`
fails on its third leg (Python 29 pass, background contracts pass,
`test_assist.cjs` errors on the assertion).

Decide, then make code and test agree:

- Option A (keep): justify why the all-hosts grant is not sufficient for
  the snapshot (`snapTab` titles/urls on tabs without a granted origin)
  and update the contract test to assert the exact permission list
  including `tabs`.
- Option B (drop): remove `"tabs"` from the manifest if the all-hosts
  grant already yields `tab.url`/`tab.title` everywhere `snapTab` runs,
  and leave the test as is.

## Acceptance criteria

- `pnpm run test:proofloop` fully green (Python suite, background
  contracts, assist contracts) with no skips.
- No new extension permission without a matching contract-test update.
- No changes to the promotion gate, ledger schema, or task set.

## Follow-up: SUBMISSION refresh, checkout check, /assist gap analysis

1. `SUBMISSION.md` is stale (describes the old stub harness). Update it
   to the current milestone-2/3 observer build.
2. In your Chromium, reload the unpacked extension and confirm a
   checkout page no longer shows city or phone warnings. Report the
   exact page and result.
3. Analysis only, no implementation: diff the current `/assist`
   request/response against the Gemini wire-shape spec below and report
   the gap field by field, so the milestone check-in has a concrete
   brief. Do not implement the spec without explicit approval.

### Gemini wire-shape spec (reference for gap analysis only)

Request (`background.js` on active-tab trigger): `token`,
`trigger` (`tab_activated` | `tab_updated` | `chip_action` |
`manual_refresh`), `active_tab` (`tab_id`, `url`, `origin`, `title`,
`is_terminal`, optional `context_hint`), `open_tabs` (each with
`tab_id`, `url`, `origin`, `title`, `is_terminal`, `last_active_ts`),
`feedback` (`action` `apply` | `keep` | `dismiss` | `null`, `item_id`,
`observed_value`).

Response (to `content.js` per-tab rendering): `active_skill_version`,
`senso_synced`, `loop_status` (`state` `idle` | `running` |
`rolled_back`, `last_delta`, `last_gate_decision`), `items` (each with
`id`, `kind` `warning` | `cross_tab_match` | `session_rule`,
`severity` `info` | `warn`, `summary`, `citation` with
`source`/`ref`, `actions`).

Terminal tab (`127.0.0.1:8082`): extra-light corner chip only, renders
loop status plus one-line reminders, never covers the prompt.

## Out of scope

- Extension ID questions: IDs are per-machine (unpacked loads), the
  backend takes the local ID from `PROOFLOOP_EXTENSION_ID`. Not a bug.
- Buttons issues #1487–#1491: backlog, do not touch.
- No loop runs on the dev-terminal machine; the live Nebius loop is owned
  by the other terminal. Do not start a duplicate.
