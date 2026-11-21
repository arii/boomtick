# Status

Last verified: 2026-11-21 on Node 22.23.4 (repo pins 24.16.0) and Python 3.11, on branch `chore/ai-slop-cleanup`. "Verified" means the listed command passed in that run. Update this file when you change a component's state.

| Component | State | Evidence |
| :--- | :--- | :--- |
| `cli/` (`td`) | Working | `PYTHONPATH=cli pytest cli/tests`: 570 passed, 6 skipped |
| `mcp/` | Working | `pnpm --filter @arii/boomtick-mcp run type-check` passes. Vitest: 382 passed, 2 failed. The failures need `td` on `PATH` and an unset `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` pair, so they are environment-dependent. |
| `workflows/` | Working | `pnpm --filter @arii/boomtick-workflows run test`: 58 passed |
| Root review/impact code (`lib/`, `scripts/`, `src/`) | Working | `pnpm run type-check:ts` passes; `vitest run --config vitest.root.config.ts`: 152 passed |
| `tokens-with-taste/` (`twt`) | Working | `pytest` in `tokens-with-taste/`: 210 passed |
| `proofloop/` offline suite | Working | `pnpm run test:proofloop` passes (detector, matcher, background contracts, assist eval) |
| `proofloop/` live services | Not verified | Needs Senso, Cognee and a gateway with keys. See `proofloop/TRACKING.md`. |
| Gemini code and visual review | Experimental | Needs API keys, not run here. `README.md` notes it can return incomplete results without failing the job. |
| MCP host registration, `setup-agent.sh`, Docker, release workflow | Not verified | Not run here. |

## Known gaps

- `cli/dev_tools/utils/__init__.py: call_ai` always returns `None`. It is kept for downstream importers named in `cli/tests/test_retained_ai_utils.py`. Remove it or make it raise once those importers are confirmed gone.
- `lib/impact-analysis-utils.ts` has no sitemap source, so `authoritativeSitemapUrls` is always empty. Route filtering that depends on it always sees an empty list. Wire a real route source or drop that logic.
- `AGENTS.md` section 7 is a machine-specific ProofLoop handoff (local paths, session links). It belongs in `proofloop/` and goes stale quickly.
