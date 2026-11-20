# ProofLoop

Measured replay-gated skill upgrades with a local Replay Gate, optional Cognee memory and optional Senso storage/retrieval, plus a Chrome status chip. TypeSafe is not used.

The executor is a deterministic model of behavior on six derived tasks. A 6/6 result is a result on that suite, not evidence of improved live LLM behavior or absolute safety.

## Offline run

Install `jsonschema` if needed. No sponsor keys are required.

```sh
cd proofloop/harness
PROOFLOOP_FORCE_STUB=1 PROOFLOOP_STATE=/tmp/proofloop-demo python3 replay_loop.py --reset --bad-demo
PROOFLOOP_FORCE_STUB=1 PROOFLOOP_STATE=/tmp/proofloop-demo python3 validate.py
python3 -m unittest discover -s tests -v
```

Expected deterministic sequence: 2/6 baseline, 5/6 candidate, 6/6 candidate, 4/6 regression rejected. The active version stays v1.2. Stub readback is labeled `stub`; it is not sponsor execution proof.

`bash proofloop/demo.sh` from the repo root is now always offline and exits after replay. Pass `--serve` only when you intend to start the loopback backend. `health.py` shows configuration without calls by default; `--probe-live` explicitly probes separately enabled services, may consume credits and may leave synthetic remote test data. A successful health endpoint is not full replay proof.

## Local Replay Gate

The gate compares the same nonempty suite and individual required checks. Promotion requires a strict increase in passed tasks, no previously passing check becoming a failure, and no increase in failed checks. Regressions are rejected. No improvement is held, not described as a rollback. Intermediate candidates may still have failed checks. No confidence or constraint probability is invented from counts.

Promotion also requires storage processing to finish and readback search to find the uploaded content. Failed/malformed readback records `promotion_failed` and preserves the active version. A failed attempt may leave a remote document behind; this code does not delete it or promise an automatic retry without cost.

New ledgers have `schema_version: 2`, `replay_gate` and `retrieval` fields. Legacy ledgers are not silently converted or called verified. Select a separate `PROOFLOOP_STATE` directory to preserve them. `--reset` explicitly deletes JSON state in the selected directory except legacy keys.json, which is never used by this version. Do not point it at unrelated files.

## Credential and activation boundaries

This version does not read `.env`, `state/keys.json` or Chrome-saved credentials. It accepts credentials only from the process environment supplied by an approved secret manager. The options page neither collects nor sends keys. Old secret files/storage are not deleted; this patch does not claim to remove existing copies.

A credential alone does not activate calls. The process must also explicitly list services in `PROOFLOOP_LIVE_SERVICES` (`cognee,senso,llm`). `PROOFLOOP_FORCE_STUB=1` overrides activation. Config status says **enabled, unverified**, not connected, healthy or verified. Cognee uploads additionally require `PROOFLOOP_ALLOW_SESSION_UPLOAD=1`. Empty-recall fallback to local skill documents is off unless `PROOFLOOP_INCLUDE_LOCAL_SKILLS=1`; only opt in after reviewing those documents and approving their upload. These flags do not create user permission. Enabling a service can spend credits and disclose its inputs; get approval for exact data, destination and usage before enabling it. No live execution is established by these instructions or tests.

| Service | Required environment | Data sent when explicitly enabled |
|---|---|---|
| Cognee | `COGNEE_API_URL`, `COGNEE_API_KEY` (tenant ID if required) | Sessions and optional local skill docs, plus recall queries |
| Senso | `SENSO_API_KEY` | Candidate skill, replay proof, gate decision, timestamps and search query |
| Mutation LLM | `OPENROUTER_API_KEY` | Known step definitions, current step IDs and failure counts |

The existing OpenRouter default model is unverified. Do not assume a `:free` slug establishes availability, privacy or zero cost. Live integration claims require actual successful evidence, separate from config labels and protocol mocks.

## Browser status, not background sponsor calls

The backend is read-only and binds loopback. `/augment` returns local replay state only. It never searches Senso with page titles, URLs or snippets. `/config` writes are disabled. Exact loopback origins/Host values are required; set `PROOFLOOP_EXTENSION_ID` to the unpacked extension's exact ID to allow that extension's origin. Broad prefix matches are not used.

For a separately approved local demo, start the backend with the same state directory and load `extension/` unpacked. No server or extension is started by tests. The chip does not read page body content or call built-in AI. It asks for local status without sending page metadata. Other tab titles can be displayed locally only if the user opts in on the options page; default is off. This local list is not semantic relatedness or evidence of grounded agent action.

```sh
PROOFLOOP_FORCE_STUB=1 PROOFLOOP_STATE=/tmp/proofloop-demo PROOFLOOP_EXTENSION_ID=<exact-extension-id> python3 server.py
```

## Scope and sponsor claims

Cognee/Senso adapters remain optional and unverified live. Their current API-shape references are https://docs.cognee.ai/cognee-cloud/http-api and https://www.docs.senso.ai/docs/quickstart . Protocol mocks test code paths, not vendor availability or prize eligibility. Sponsor-specific challenges can have stricter requirements than the general event. No TypeSafe prize/credit dependency remains. Earlier planning notes in TRACKING.md are historical, not current instructions or authorization.
