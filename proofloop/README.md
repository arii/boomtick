# ProofLoop

Replay-gated skill upgrades (Cognee memory, local deterministic promotion gate, Senso promotion) plus a quiet Chrome chip.

## Run (stub mode needs no keys)
```sh
python3 -m venv .venv && .venv/bin/pip install jsonschema   # validation only
cd harness
../.venv/bin/python make_tasks.py          # derive data/replay_tasks.json from data/sessions.jsonl
../.venv/bin/python validate.py
../.venv/bin/python replay_loop.py --reset --bad-demo
python3 server.py                          # http://127.0.0.1:8787 (dashboard at /, /augment, /config)
```
Extension: chrome://extensions -> Developer mode -> Load unpacked -> `proofloop/extension`.
Test pages: `cd extension/test && python3 -m http.server 8788`, open `demo.html` plus `related-1.html`, `related-2.html` in one window.

## Live vs stub
Chosen per service in `harness/config.py` from env vars or `state/keys.json`
(written by the extension options page). `PROOFLOOP_FORCE_STUB=1` forces stubs.

| Service | Live when set | Stub |
|---|---|---|
| Cognee | `COGNEE_API_URL` (+ `COGNEE_API_KEY`) | `state/cognee_stub.json` |
| Gate | local deterministic gate (default, no API) | `PROOFLOOP_GATE=jev` + `TYPESAFE_API_KEY` re-enables the Jev client (disabled, no sponsor credits) |
| Senso | `SENSO_API_KEY` | `state/senso_stub.json` |
| Mutation LLM | `OPENROUTER_API_KEY` | rule-based mutator |

## API shapes (checked against public docs, not against live keys)
- **Senso** ([quickstart](https://www.docs.senso.ai/docs/quickstart)): base `https://apiv2.senso.ai/api/v1` (not `api.senso.ai`), header `X-API-Key`. Poll `kb_node_id` until `content.processing_status == complete`. Search hits match on `content_id`. Identical text returns 409, so promoted text carries version, cycle and timestamp.
- **Jev** ([unofficial HTTP reference](https://github.com/typesafe-docs/typesafeai)): `questions` is a map of `{type: choice|score|noul, instructions, criteria}`, answers come back under `answers`. That guide lists `jev-latest` / `jev-1.13.0`, not the spec's `typesafe/jev-1.14.0`. The harness tries the spec model first (override with `TYPESAFE_MODEL`) and retries once with `jev-latest` on 400/404/422. The ledger records the model the API reports. A code guard stops Jev from promoting a candidate that is not strictly better.
- **Cognee** ([HTTP API](https://docs.cognee.ai/cognee-cloud/http-api)): `add` is multipart (`datasetName`, repeated `raw_data`), `cognify` takes `{"datasets": [...]}`, `search` takes `{"query", "search_type"}`. Cloud auth is `X-Api-Key` plus `X-Tenant-Id` (set `COGNEE_TENANT_ID`); self-hosted uses Bearer. Cloud tenant URLs look like `https://tenant-<id>.aws.cognee.ai`.
- **OpenRouter**: model defaults to `arcee-ai/trinity-large-thinking:free` (override `OPENROUTER_MODEL`). Slug not confirmed against a live key.

`harness/mock_sponsors.py` is an offline mock of these shapes. It lets the live code paths run without keys:
`python3 mock_sponsors.py 9001`, then set `COGNEE_API_URL`, `TYPESAFE_BASE_URL`, `SENSO_BASE_URL` to `http://127.0.0.1:9001` and the key vars to any value.
