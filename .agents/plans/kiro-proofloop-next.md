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

## Out of scope

- Extension ID questions: IDs are per-machine (unpacked loads), the
  backend takes the local ID from `PROOFLOOP_EXTENSION_ID`. Not a bug.
- Buttons issues #1487–#1491: backlog, do not touch.
- No loop runs on the dev-terminal machine; the live Nebius loop is owned
  by the other terminal. Do not start a duplicate.
