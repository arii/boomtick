# Boomtick

Boomtick provides developer tooling for GitHub work: a Python CLI, an MCP server, workflow helpers and Gemini review entrypoints. It includes verification pipelines used by Vite projects such as `arii/tech-dancer`.

The repository keeps human design decisions separate from automated implementation and checks. A generated report is evidence to inspect, not permission to merge or deploy.

---

## Quick Start

From a local clone, use Node.js 24, pnpm 10.28.2 and Python 3 (the CLI package declares Python 3.8 or newer; the separate tokens-with-taste gateway requires 3.11 or newer). The setup script installs dependencies and browser tooling, configures Git hooks and persists shell settings. Its validation step also attempts MCP host registration and context-index warming. Review these effects before running it:

```bash
./setup-agent.sh
```

Open a new shell after setup, or load its saved environment in your current shell. Build the MCP server explicitly before using its generated entrypoint:

```bash
source "$HOME/.config/boomtick/env.sh"
pnpm --filter @arii/boomtick-mcp run build

# Register boomtick-mcp with local agent hosts (Antigravity CLI, Claude Code, Cursor, VS Code)
td mcp install --execute

# Or run directly via stdio
node mcp/dist/index.js
```

---

## Repository Architecture

The codebase has three main areas:

* **`mcp/` (Model Context Protocol Server):** Provides structured access to GitHub pull requests, repository state, CI logs and validation tools, including conflict resolution and branch creation.
* **`cli/` (`td`):** A terminal-based fallback and local automation toolkit. Integrates directly with the GitHub CLI (`gh`) to handle manual PR audits, conflict detection, and runtime consistency checks.
* **[`tokens-with-taste/`](tokens-with-taste/README.md):** Standalone Python 3.11+ LLM gateway, provider catalog, and token/cost audits (`twt`).

### Zero-Submodule Integration

Boomtick uses a direct standalone package, container, and composite action integration strategy. See [docs/onboarding.md](docs/onboarding.md) for how to integrate Boomtick into downstream repositories via PyPI (`boomtick-cli`), Docker (`ghcr.io/arii/boomtick`), npm (`@arii/boomtick-mcp`), or composite actions.

---

## Advanced AI Integration

* **Gemini API:** The code and visual review entrypoints support Gemini. A usable API key and available project capacity are required. Inspect the actual review output and logs: the current main implementation can return incomplete or empty results without a failed job. Do not treat that as approval. The corrective native-context/fail-closed work is on a separate branch, not part of main.
* **Review orchestration:** TypeScript clients call the Gemini REST API directly and combine specialist review results. GitHub Models command aliases remain in package scripts, but their provider argument is rejected by the current review runner.
* **Context retrieval:** The Python CLI includes dependency-graph and vector-store tools. The review context command returns direct dependencies and dependents; it does not run vector search.

Documentation source check: November 21, 2026. Local documentation links and setup-shell syntax were checked against this repository. A fresh-machine installation, host registration and live API review were not executed as part of that check.

---

## Documentation Index

* [Reusable Agent Skills](.agents/README.md#installable-skills) — Install the GitHub Actions health check or BoomTick review setup in your agent.
* [Developer Onboarding & Workflows](docs/onboarding.md) — Onboarding guide, codebase context, and collaboration workflows.
* [Agent Contracts and Standards](.agents/AGENT_CONTRACT.md) — Invariant rules for autonomous agent behavior.
* [Agent Workflows & MCP Protocol](.agents/README.md) — Tooling hierarchies (MCP → `td` → Bash) and enforcement rules.
* [CLI Developer Tooling](cli/README.md) — Guide to `td`, the Tier 2 local developer fallback.
* [MCP Server Configuration](mcp/README.md) — Setup, capabilities, and tools for the Boomtick MCP.
* [Release Process](docs/release-process.md) — Guidelines for deployment and release pipelines.
* [Impact Analysis Integration](docs/impact-analysis-integration.md) — Running and integrating blast-radius checks.
* [MCP Testing](mcp/docs/testing.md) — Step-by-step verification protocols.

---

## Showcase / Live Projects

* **boomtick.blog**: [https://boomtick.blog](https://boomtick.blog) (Dance tech platform, event scheduling & digital business systems)
* **arii.github.io**: [https://arii.github.io](https://arii.github.io) (Personal portfolio & developer projects)

---

## Author

Created by **[Ariel Anders](https://arii.github.io)**, creator of **[Boomtick Blog](https://boomtick.blog)**.

<hr>

*Tags: #DevAI #EngineeringOperations #GeminiAPI #RAG #VectorStore #AgenticExecution #MCP #TypeScript #Python #Vite*
