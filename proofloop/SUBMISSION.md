# ProofLoop: self-proving page and cross-tab personal agent

**One line:** ProofLoop is a non-chat personal agent that lives on the page as a quiet chip. It only offers a skill upgrade after replaying your own past tasks proves the upgrade is better, and it shows that proof.

## Short description (for the form)

Most personal agents sit in a chat box and forget what went wrong last time. ProofLoop does not chat. It is a Chrome extension plus a background replay engine. The engine takes real session logs, replays the historical tasks against the current skill (v0) and a mutated candidate, and promotes the candidate only if a local, deterministic Replay Gate says it is strictly better with no regressions. Proven skills are stored in Senso and read back before they go live. On the page, ProofLoop shows a quiet, dismissible chip with the active skill version and an expandable proof table, plus cross-tab context from your other open tabs (local only, opt-in). When a mutation makes things worse, the gate rejects it and rolls back automatically.

## What it does

1. **Ingest.** Eight real session excerpts (cross-tab misses, fabricated or unverified claims, and successes; personal data redacted) are ingested into Cognee, which recalls the matching sessions for the six replay tasks derived from them.
2. **Replay.** The engine runs the six tasks against the v0 baseline skill and records which individual checks pass or fail.
3. **Mutate.** A new skill version is proposed from the failure pattern. The default is a rule-based mutator; an LLM through the local Tokens with Taste gateway or OpenRouter is optional.
4. **Gate.** A local deterministic Replay Gate decides: promote only if strictly more tasks pass, no previously passing check newly fails, and failed checks do not increase. Equal results hold. Any regression is rejected and rolled back. There is no model call in the decision, so every decision can be audited from the ledger.
5. **Store.** A promoted skill and its proof are written to Senso. The new version becomes active only after Senso finishes processing and a search readback finds it. A failed readback keeps the old version.
6. **Show.** The extension chip reads the proof ledger from a read-only loopback backend and shows the active version, replay pass count, and a proof table of every cycle (version, pass counts, delta, gate decision, Senso node, status).

## Demo results

Measured on the six replay tasks derived from real sessions:

| Version | Passed | Gate decision |
|---|---|---|
| v0 baseline | 2/6 | n/a |
| v1.1 | 5/6 | promote |
| v1.2 | 6/6 | promote (active) |
| v1.3 (deliberately bad) | 4/6 | reject and roll back; v1.2 stays active |

The pass counts come from running the task checks, not from fixed numbers. The table above is the run with the rule-based mutator.

Latest live run (Cognee, Senso and the mutation LLM all live): v0 2/6, v1.1 6/6 promoted, deliberately bad v1.3 4/6 rejected and rolled back, v1.1 stays active. When an LLM proposes the new steps (through the local gateway), the engine can reach 6/6 in a single cycle. The Replay Gate rules and the rollback behavior are identical either way.

## Tools used

- **Cognee (Cognee Cloud)**: memory graph for session history. The eight sessions are ingested through the Cognee HTTP API and the replay recalls all six task sessions from it. A built-in local graph is the offline fallback.
- **Senso**: storage and verified readback of promoted skills and their proof.
- **Chrome extension (Manifest V3)**: content script chip, background service worker, options page.
- **Python replay harness**: replay engine, deterministic Replay Gate, proof ledger, read-only local backend, 39 offline tests.
- **Tokens with Taste (optional)**: local OpenAI-compatible gateway that routes the mutation call across free providers.

## Privacy and safety

- No page title, URL, snippet or body is sent to the backend or to any sponsor. Other-tab titles are shown locally only, behind an opt-in that is off by default.
- Credentials alone never turn on a service. Live services need an explicit opt-in, and offline stubs are labeled on screen.
- The backend is read-only and loopback-only, with exact Host and Origin checks and no credential forms.

## Honest limits

- The replay executor is a deterministic model of agent behavior on six tasks. A 6/6 result is a result on that suite, not evidence of better live-LLM behavior or a safety guarantee.
- The proof shown is measured replay of past tasks, not a claim about future ones.
- The loop is bounded, not open-ended. A mutation can only switch on or off four fixed skill steps, the six tasks are a fixed set, and the loop ends when all of them pass or the steps run out. It does not write new rules or learn from new data on its own.
- The replay executor is a deterministic model and does not run an agent. The promoted skill is rendered into a prompt block (rules plus the constraints it passed) that can be written into an agent instruction file; whether that prompt improves a live agent has not been measured.

## Links

- Code: https://github.com/arii/boomtick/tree/feat/proofloop/proofloop
- Run offline: `bash proofloop/demo.sh` (add `--serve` for the backend), tests: `python3 -m unittest discover -s proofloop/harness/tests -v`
- Setup, activation and extension steps: `proofloop/README.md`
