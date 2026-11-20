# Resilient Shopping & Task Agent with Persistent Audit Trail

## What runs now

An offline, synthetic Capture -> Coordinate -> Handoff -> Audit scaffold in the
existing workspace. Python 3.8+ on Linux/macOS, standard library only. No package
installation, credentials, network, purchase, Sheet write, observer connection,
server restart or deployment is needed. Product IDs and prices are fictional.

From the repository root, pick a new receipt path outside the repository:

```sh
python3 scripts/shopping_demo.py run --receipt /tmp/shopping-normal.jsonl
python3 scripts/shopping_demo.py audit --receipt /tmp/shopping-normal.jsonl
```

For a recorded primary timeout and a handoff across two fresh processes:

```sh
python3 scripts/shopping_demo.py run --receipt /tmp/shopping-handoff.jsonl \
  --actor assistant-a --simulate-failure --stop-after-handoff
python3 scripts/shopping_demo.py resume --receipt /tmp/shopping-handoff.jsonl \
  --actor assistant-b
python3 scripts/shopping_demo.py audit --receipt /tmp/shopping-handoff.jsonl
python3 scripts/shopping_demo.py integrations
```

Use a new filename on each demonstration. Existing receipts are never replaced.
Retrying `resume` on a completed receipt is read-only and does not duplicate Audit.
Actor names are local demo labels, not authenticated identities or real assistants.
A separate-process replay is not proof of a real two-assistant handoff.

## Four phases

1. **Capture:** persist a synthetic shopping request, budget in integer USD cents,
   a stable task key and the pending sponsor integration inventory.
2. **Coordinate:** filter out over-budget fixtures and sort by price. Optionally
   record a synthetic primary timeout before the fixture fallback. The proposal
   remains `Needs Okay`; there is no checkout implementation.
3. **Handoff:** persist the recipient label and minimal comparison context under
   the same task key. Stop here to demonstrate that a second process reads the
   receipt rather than inheriting an in-memory object.
4. **Audit:** validate the chain and phase order, then append the outcome with the
   previous receipt hash, actor and execution type. `audit` itself is read-only.

Each append is flushed and fsynced. A local advisory lock serializes cooperating
writers. Truncated, hash-mismatched, reordered and mixed-task receipts fail
closed and are preserved for inspection. The chain detects accidental changes;
it is not signed, tamper-proof, an append-only service or proof of who wrote it.
A whole receipt can be rewritten and rehashed by someone with filesystem access.
An interrupted write is not automatically repaired. Preserve the receipt and use
a new path. Resume currently requires a complete Handoff checkpoint.

This local receipt is deliberately separate from `scripts/agent_ledger.py` and
its shared form/Sheet/Drive snapshot store. No live host OAuth reader or shared
Sheet freshness claim follows from this demo.

## Sponsor adapter boundaries

The `SPONSORS` inventory preserves the intended roles while explicitly reporting
that all live integrations remain pending. It is a replacement seam, not an API
implementation. No invented tool names, request schemas or endpoints are called.
Do not describe the fixture behavior as sponsor integration proof.

| Sponsor | Intended role | Contract/access work before any live claim |
| --- | --- | --- |
| Senso.ai | Shopping/finance discovery via Senso MCP | Official MCP describes an organization's knowledge base and AI visibility, not a public product/finance feed. Verify the intended dataset, exact MCP tool, authorization and credits. Do not substitute the separate sensomcp.com product. |
| Cognee | Cross-assistant session graph memory | Confirm shared dataset permissions, graph/embedding configuration and model costs. `add()` stages content; `cognify()` builds memory. Local JSONL replay is not Cognee graph persistence. |
| Superlinked | Multimodal product ranking | Choose the SDK/server contract, schema, embedding model, image handling and budget. Price ordering is not vector search. |
| Firedrill | Simulation/failover benchmark | Set up workspace, review scenario and credit estimate, then obtain approval before running. Local failure injection produces no Firedrill report. |
| Tokens& | Repo observer connection | Verify project-specific Connect app setup, checksum-pinned private Python SDK and disclosure scope. Explicit instrumentation plus a fresh accepted request/flush is needed. No repository is connected by this script. |

Official sources checked November 20, 2026:

- Senso MCP: https://docs.senso.ai/docs/mcp-server
- Senso entry points: https://docs.senso.ai/docs/connect-your-agent
- Cognee staging: https://docs.cognee.ai/python-api/add
- Cognee graph build: https://docs.cognee.ai/python-api/cognify
- Superlinked multimodal encoding: https://superlinked.com/docs/encode/multimodal
- Firedrill hackathon setup: https://firedrill.run/hacker-docs
- Tokens& observer/setup contract: https://tokensand.com/docs/api

Do not pass personal tasks, the shared ledger, private planning documents,
credentials or session history to sponsors. Adding an SDK is not evidence of a
successful integration. Free credits are still a spend decision. Live execution,
repository grants and external disclosures need their own authorized scope.

## Tests and demo evidence

```sh
python3 -m pytest cli/tests/test_shopping_demo.py cli/tests/test_agent_ledger.py
```

Tests cover all four phases, separate-process handoff, recipient mismatch,
idempotent resume, recorded simulated failure, budget filtering, receipt
integrity errors, pending sponsors and lack of a live execution mode.

For a submission recording, show the three commands and the resulting JSONL
phases/task key. Label it **offline fixture scaffold**. Keep the code/test proof
separate from the still-open live sponsor, host-reader and real two-assistant
proof. The event submission checklist lives in the canonical planning document,
not in a new dashboard or a parallel checklist here.
