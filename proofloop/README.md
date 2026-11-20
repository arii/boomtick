# ProofLoop

Replay-gated skill upgrades (Cognee memory, TypeSafe Jev gate, Senso promotion) plus a quiet Chrome chip.

## Run (stub mode needs no keys)
```sh
python3 -m venv .venv && .venv/bin/pip install jsonschema   # validation only
cd harness
../.venv/bin/python make_seed_data.py      # placeholder sessions + tasks (replace with real excerpts)
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
| Jev | `TYPESAFE_API_KEY` | threshold gate |
| Senso | `SENSO_API_KEY` | `state/senso_stub.json` |
| Mutation LLM | `OPENROUTER_API_KEY` | rule-based mutator |

## Unverified against live APIs
Endpoints follow the spec. Request/response field names for Cognee, Jev, Senso and OpenRouter
(and the OpenRouter model slug) are best guesses marked UNVERIFIED in `harness/clients.py`.
Check them on the first live call.
