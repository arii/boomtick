# boomtick-workflows

Constrained, fixed-graph workflows for boomtick, built on LangGraph.js. Exposed
to MCP clients through the single `run_workflow` tool backed by a server-side
registry — there is no autonomous agent loop in this package.

## Design

- **Fixed graphs, not ReAct loops.** Every workflow is a `StateGraph` over the
  shared `WorkflowState` (`src/state.ts`); the graph shape is the contract.
- **Deterministic-first.** Request validation, schema repair, and provider
  selection are plain code. LLM calls happen only in graph nodes that need
  structured output.
- **Provider chain, schema-preserving.** Each provider is wrapped in
  structured-output *before* composition (`src/providers/chain.ts`): local
  Ollama → OpenRouter (free tier, pinned model) → Nebius. Transient failures
  retry on the same candidate (2 attempts); schema rejections never retry —
  they move to the next tier.
- **Receipts.** Every run returns `{ status, workflow, result, steps, tier,
  model, error }`; `steps` carries one record per provider attempt with the
  answering tier, so traces show which tier answered.

## Workflows

| id | graph | purpose |
|---|---|---|
| `echo` | `START → echo → END` | Deterministic smoke path; no provider calls. |
| `structured_extract` | `START → extract → (schema ok ? END : repair → END)` | Extract structured output with exactly one bounded repair attempt (validation error fed back). |

Registry introspection: MCP resource `boomtick://workflows/registry` lists
every workflow id, description, and per-workflow input schema.

## Provider configuration

Environment (all optional): `OLLAMA_BASE_URL`, `OLLAMA_TOOL_MODEL`
(default `phi4-mini`), `OLLAMA_STRUCTURED_MODEL` (default `gemma3:4b`),
`OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (required if the key is set — the
free router picks models at random, so pin one), `NEBIUS_API_KEY`,
`NEBIUS_MODEL`, `NEBIUS_BASE_URL`. With no keys the chain degrades to
local-only and surfaces a clear error when no local model answers.

Temperature is 0 everywhere. `num_ctx` defaults are deliberately conservative;
raising them is a RAM-budget decision, not a default.

## Honest known limitations

- **Not production-ready.** The benchmark evidence behind the model choices is
  hobby-hardware directional data; on-target CPU benchmarks are a separate,
  pending task. Do not promise latency or accuracy numbers from this package.
- **Small models pick tools badly.** That is why tool selection is not in
  these graphs at all; open-ended tool choice belongs to the cloud tier and
  stays out of this package until benchmarks say otherwise.
- **Cloud hops are mock-tested only.** OpenRouter and Nebius candidates are
  integration-tested against mocks; no real-key smoke test has run in this
  repo. Manual smoke with real keys is a documented follow-up.
- **No checkpointing.** Graphs run in-memory; there is no durable execution
  or human-in-the-loop interrupt yet.
- **Context budgets are unmeasured.** No workflow currently profiles token
  usage against the practical 8–16K budget recommended by the runtime research.
