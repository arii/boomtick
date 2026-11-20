# ProofLoop

Measured replay-gated skill upgrades with a local Replay Gate, optional Cognee memory and optional Senso storage/retrieval, plus a Chrome status chip.

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

## Mutation LLM via Tokens with Taste (local gateway)

`tokens-with-taste/` in this repo is a local OpenAI-compatible gateway that tries free providers in order (Google, Groq, NVIDIA, Mistral, OpenRouter, SambaNova) and records traces. ProofLoop can use it for the one LLM call it makes: proposing which skill steps to add after a replay. It replaces the OpenRouter-only path when OpenRouter free quota is gone.

```sh
# Terminal 1: export at least one provider key you actually have (the gateway holds them, ProofLoop never sees them)
cd tokens-with-taste && python3.11 -m venv .venv && . .venv/bin/activate && python -m pip install -e '.[test]'
export GROQ_API_KEY=...        # or GOOGLE_API_KEY, NVIDIA_API_KEY, MISTRAL_API_KEY, SAMBANOVA_API_KEY
twt sync && twt serve          # 127.0.0.1:8000/v1
# Terminal 2: explicit opt-in, no ProofLoop key needed
PROOFLOOP_LIVE_SERVICES=twt python3 proofloop/harness/health.py --probe-live
PROOFLOOP_LIVE_SERVICES=senso,twt SENSO_API_KEY=... python3 proofloop/harness/replay_loop.py --reset --bad-demo
```

No provider keys at all: run Ollama locally and `export TWT_OLLAMA_MODEL=qwen2.5:0.5b` before `twt sync && twt serve` (see `tokens-with-taste/README.md`). A model that small may not return valid JSON; the harness then falls back to the rule-based mutator.

- Off by default. `twt` must be listed in `PROOFLOOP_LIVE_SERVICES`; credentials alone never activate anything. `twt` wins over `llm` (OpenRouter) when both are listed.
- The gateway URL must be loopback `http://` (`TWT_BASE_URL`, default `http://127.0.0.1:8000/v1`). Any other host is ignored.
- The prompt contains only check names, failure counts and step ids. No session text, URLs, phone placeholders or page data. The gateway still stores full prompts in its own local SQLite file (`TWT_DB`, mode 0600).
- If the gateway is down or the waterfall is exhausted (it returns 503 listing missing credentials, never a fake completion), the harness logs the failure and uses the rule-based mutator. Replay results and the gate do not depend on the LLM.
- Checked against the real gateway with no provider keys: sync, serve, 503 with missing-env list, harness fallback. A successful provider completion has not been exercised (no provider key in the build sandbox).

## Auto-updating agent prompt

After every run the active skill is rendered into `state/active_prompt.md`: one rule per step in the skill, plus the constraints of the replayed tasks that pass. To keep an agent's instructions current, name a file:

```sh
python3 harness/replay_loop.py --reset --sync-prompt ~/AGENTS-or-GEMINI.md --create-target   # or PROOFLOOP_PROMPT_TARGET
```

Only the text between `<!-- PROOFLOOP:BEGIN -->` and `<!-- PROOFLOOP:END -->` is replaced; the rest of the file is never touched. It refuses `.env`, anything under `.git`, and any file that is not `.md`, `.mdc` or `.txt`. A rejected or rolled-back candidate leaves the previous block, and an unpromoted v0 never overwrites an existing block. The backend serves the text at `GET /prompt`, the chip has a "Copy active prompt" button, and the dashboard shows it.

Scope: the rules are fixed text per step, and the loop is bounded to four fixed steps. See TRACKING.md, "What the loop is and is not".

## Credential and activation boundaries

This version does not read `.env`, `state/keys.json` or Chrome-saved credentials. It accepts credentials only from the process environment supplied by an approved secret manager. The options page neither collects nor sends keys. Old secret files/storage are not deleted; this patch does not claim to remove existing copies.

A credential alone does not activate calls. The process must also explicitly list services in `PROOFLOOP_LIVE_SERVICES` (`cognee,senso,llm`). `PROOFLOOP_FORCE_STUB=1` overrides activation. Config status says **enabled, unverified**, not connected, healthy or verified. Cognee uploads additionally require `PROOFLOOP_ALLOW_SESSION_UPLOAD=1`. Empty-recall fallback to local skill documents is off unless `PROOFLOOP_INCLUDE_LOCAL_SKILLS=1`; only opt in after reviewing those documents and approving their upload. These flags do not create user permission. Enabling a service can spend credits and disclose its inputs; get approval for exact data, destination and usage before enabling it. No live execution is established by these instructions or tests.

| Service | Required environment | Data sent when explicitly enabled |
|---|---|---|
| Cognee | `COGNEE_API_URL`, `COGNEE_API_KEY` (tenant ID if required) | Sessions and optional local skill docs, plus recall queries |
| Senso | `SENSO_API_KEY` | Candidate skill, replay proof, gate decision, timestamps and search query |
| Mutation LLM | `OPENROUTER_API_KEY` | Known step definitions, current step IDs and failure counts |

The OpenRouter default is `openrouter/free`, preserving the upstream replacement for its reported retired model; routing, successful calls and account terms remain unverified here. All harness HTTP clients retain the upstream custom User-Agent fix. Do not assume a `:free` slug establishes availability, privacy or zero cost. Live integration claims require actual successful evidence, separate from config labels and protocol mocks.

## Browser status, not background sponsor calls

The backend is read-only and binds loopback. `/augment` returns local replay state only. It never searches Senso with page titles, URLs or snippets. `/config` writes are disabled. Exact loopback origins/Host values are required; set `PROOFLOOP_EXTENSION_ID` to the unpacked extension's exact ID to allow that extension's origin. Broad prefix matches are not used.

For a separately approved local demo, start the backend with the same state directory and load `extension/` unpacked. No server or extension is started by tests. The chip does not read page body content or call built-in AI. It asks for local status without sending page metadata. Other tab titles can be displayed locally only if the user opts in on the options page; default is off. This local list is not semantic relatedness or evidence of grounded agent action.

```sh
PROOFLOOP_FORCE_STUB=1 PROOFLOOP_STATE=/tmp/proofloop-demo PROOFLOOP_EXTENSION_ID=<exact-extension-id> python3 server.py
```

## Scope and sponsor claims

Cognee/Senso adapters remain optional and unverified live. Their current API-shape references are https://docs.cognee.ai/cognee-cloud/http-api and https://www.docs.senso.ai/docs/quickstart . Protocol mocks test code paths, not vendor availability or prize eligibility. Sponsor-specific challenges can have stricter requirements than the general event. Earlier planning notes in TRACKING.md are historical, not current instructions or authorization.
