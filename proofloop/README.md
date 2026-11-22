# ProofLoop

A Chrome extension that watches the sites you turn on and warns when something on the page conflicts with a rule learned from your own past sessions: a forbidden value in a field, a box that should stay unchecked, a choice you wanted to be asked about, or a value that differs from another watched tab. It is an observer. It never types, fills, checks or submits anything.

The rules come from a loop that replays past sessions with a real LLM, proposes rule changes from the failures and from Cognee recall, keeps only changes that beat measured noise on train and holdout tasks, and stores promoted rule sets in Senso. See `PLAN.md` section 0 for the direction and milestones.

## Parts

| Part | Files | What it does |
|------|-------|--------------|
| Sessions | `data/sessions.jsonl` | Redacted excerpts of real sessions (phones masked as `[PHONE-PRO]`, `[PHONE-FAMILY]`). Source of truth |
| Tasks | `harness/tasks.py` → `data/replay_tasks.json` | The LLM turns each session into a replay task with checks. Check values must appear in the session. Marked `reviewed: false` until you review it |
| Loop | `harness/replay_loop.py` | Executor (LLM answers each task, 3 samples), judge (LLM grades clarification and claim checks), mutator (LLM proposes a whole rule set from train failures + Cognee recall + your feedback), gate (`gate.py`), Senso promotion and readback. Repeats until 3 proposals in a row fail to promote, every train task passes, or the 12-proposal cap |
| Rules | `schemas/rules.schema.json`, `harness/rules.py` | Rule sets are validated and grounded: every value a rule names must appear in the sessions it cites |
| Backend | `harness/server.py`, `harness/page_assist.py` | Loopback only, per-run bearer token. Serves promoted page rules for a task with forbidden values as salted hashes, plus short context from past sessions. Records feedback |
| Extension | `extension/` | Watched sites only (toolbar button). Detects fields and the page's task locally, hashes field values locally, shows a pill, warnings and "Context & Rules" cards, holds one submit while a conflict is open |

There are no runtime stubs. If a service is not enabled, the command stops with `BLOCKED: ...`. Tests inject fakes in test code only.

## Run it (your machine)

Requirements: Python 3.11 with `jsonschema`, Node 20+, the TWT gateway (or OpenRouter), Senso and Cognee keys in your shell. Keys are read only from the process environment.

```sh
cd proofloop/harness
export PROOFLOOP_LIVE_SERVICES=twt,senso,cognee      # or llm instead of twt, with OPENROUTER_API_KEY
export SENSO_API_KEY=...  COGNEE_API_URL=...  COGNEE_API_KEY=...  COGNEE_TENANT_ID=...
export PROOFLOOP_ALLOW_SESSION_UPLOAD=1               # sessions.jsonl is redacted; this uploads it to Cognee

python3 health.py --probe-live                       # one call per service
python3 tasks.py --generate                          # writes data/replay_tasks.json; review it, set generated.reviewed to true
python3 replay_loop.py                               # auto-repeat loop; --no-recall runs without Cognee (recorded as disabled)
python3 validate.py
python3 handoff.py > /tmp/proofloop-handoff.json   # after a promotion: redacted bundle for review (see .agents/plans/kiro-loop-handoff.md)
```

Private values for placeholders, so the extension can recognize your real numbers (never committed, never sent to the browser as text):

```sh
mkdir -p ../data/private && cat > ../data/private/values.json   # {"[PHONE-PRO]": "...", "[PHONE-FAMILY]": "..."}
```

Backend and extension:

```sh
PROOFLOOP_EXTENSION_ID=<id from chrome://extensions> python3 server.py 8787   # prints where the token is written
# optional: PROOFLOOP_ASSIST_RECALL=1 lets the page context use Cognee recall (also needs the option in settings)
```

1. `chrome://extensions` → Developer mode → Load unpacked → `proofloop/extension` (reload it after pulling).
2. Settings (extension options): paste the contents of `state/server_token`, save.
3. On a form page, click the ProofLoop toolbar button → "Watch this site" → allow. Reload the page.
4. Dashboard: `http://127.0.0.1:8787/#token=<token>`.

### Backend not on this machine

The extension talks to `http://127.0.0.1:8787` by default. If the backend runs elsewhere, either forward its port so it still appears at that address (below), or reach it by name:

1. Start the server with `PROOFLOOP_BIND_HOST=<interface address>` and `PROOFLOOP_ALLOWED_HOSTS=<host>:<port>`. The value is a comma-separated list of exact `host:port` Host values, such as `proofloop.lan:8787`. Entries without a port, with a scheme or with wildcards are ignored.
2. In the extension settings, set Backend URL to `http://<host>:<port>`, the same host and port as in the list. Any path is dropped. Save asks for permission to reach that host.
3. Paste that backend's `state/server_token`, save, and reload watched pages.

`extension/test/remote_backend_check.cjs` runs this flow against a non-loopback address. Without `PROOFLOOP_ALLOWED_HOSTS`, the server accepts only Host `127.0.0.1:<port>` or `localhost:<port>`, so another name gets 403.

- SSH: `ssh -L 8787:127.0.0.1:8787 <host>` (the server stays on the remote loopback).
- Docker: publish to loopback only, `-p 127.0.0.1:8787:8787`, and start the server in the container with `PROOFLOOP_BIND_HOST=0.0.0.0` so the published port can reach it.

The server binds `127.0.0.1` unless `PROOFLOOP_BIND_HOST` is set. A non-loopback bind prints a warning: only the bearer token protects the backend, and traffic is plain HTTP, so use TLS or a tunnel. The Host and Origin checks still apply and expect `127.0.0.1:<port>` or `localhost:<port>` (the same port the server listens on), which the forwards above preserve.

## Tests

```sh
pnpm run test:proofloop          # Python (loop, gate, grounding, server) + extension offline tests (detector, hashing parity with Python, task classifier, source rules, background contracts) + assist eval (fails below precision 1.0)
pnpm run test:proofloop:e2e      # real Chromium + unpacked extension + real backend on fixtures re-captured from live Luma and Vouch
node proofloop/extension/test/live_sites.cjs                # the observer on the real luma.com and apply.vouch.us pages with YOUR promoted rule set
node proofloop/extension/test/live_sites.cjs --test-rules   # same, with a temporary test rule set
```

The assist eval (`extension/test/assist_eval.cjs`, cases in `extension/test/eval/`) is 36 hand-labeled form states on the captured Luma and Vouch pages plus synthetic job, checkout, profile and blog pages. It reports precision and recall per rule. Add a case whenever a warning is wrong or missing in real use.

The live script never fills name or email, never clicks Vouch's "Start Application", and clicks Luma's "Request to Join" only while a conflict is open with name and email empty, so nothing can be submitted.

## Privacy and security

- The extension runs only on sites you turn on (optional host permissions). `/assist` receives the page origin and task id only. Field values never leave the browser; matching uses salted SHA-256 of normalized values. Hashes of phone numbers are guessable by brute force, so treat the backend state and browser storage as private.
- Cross-tab comparison (off by default) keeps hashes in session memory and shows at most the last 4 digits of a phone.
- Cognee page recall (off by default) sends the origin and task name to Cognee through the backend.
- Rule sets served to the browser are re-validated (schema, grounding, hash). UI text is inserted with `textContent` in a closed shadow root.
- API errors pass through secret redaction. The backend binds 127.0.0.1, checks Host and Origin, and requires the token on every API route.
