# Boomtick

Boomtick is a template repository providing foundational developer tooling, workflow orchestration, and an advanced AI review framework for autonomous agent systems. While framework-agnostic at its core, it includes built-in verification pipelines optimized for Vite applications (as demonstrated in `arii/tech-dancer`).

Boomtick strictly separates human-led strategic system design from agentic execution—reserving automation for repetitive engineering tasks, compilation, data validation, and operational compliance.

---

## Quick Start

Initialize the agent environment and set up the local CLI:

```bash
./setup-agent.sh
```

Run the MCP server locally (requires Node.js):

```bash
cd mcp
pnpm install
pnpm build
node dist/index.js
```

---

## Repository Architecture

The codebase is split into two primary operational layers:
* **`mcp/` (Model Context Protocol Server):** Empowers AI agents with structured access to GitHub Pull Requests, repository state, CI logs, and validation tools. Facilitates conflict resolution, branch creation, and interaction with the Jules macro-agent.
* **`cli/` (`td-cli`):** A terminal-based fallback and local automation toolkit. Integrates directly with the GitHub CLI (`gh`) to handle manual PR audits, conflict detection, and runtime consistency checks.

---

## Advanced AI Integration

* **GitHub Models API:** Low-latency code reviews and blast-radius analysis via OpenAI-compatible endpoints.
* **Gemini API:** Multi-modal analysis for deep contextual and visual interface reviews.
* **Orchestration:** Streamlined LLM routing and fallback strategies powered by `@langchain/core`.
* **Contextual Retrieval:** RAG pipeline integration utilizing vector stores for automated triage and overlap analysis.

---

## Planned Updates
* Composite GitHub Actions (for zero-submodule integration)
* Docker Container Packages & PyPI Packaging
* Advanced RAG / Vector Store enhancements

---

## Documentation Index

* [Agent Contracts and Standards](.agents/AGENT_CONTRACT.md) — Invariant rules for autonomous agent behavior.
* [Agent Workflows & MCP Protocol](.agents/README.md) — Tooling hierarchies (MCP → `td-cli` → Bash) and enforcement rules.
* [CLI Developer Tooling](cli/README.md) — Guide to `td-cli`, the Tier 2 local developer fallback.
* [MCP Server Configuration](mcp/README.md) — Setup, capabilities, and tools for the Boomtick MCP.
* [Release Process](docs/release-process.md) — Guidelines for deployment and release pipelines.
* [Impact Analysis Integration](docs/impact-analysis-integration.md) — Running and integrating blast-radius checks.
* [MCP Testing](mcp/docs/testing.md) — Step-by-step verification protocols.

<hr>

*Tags: #DevAI #EngineeringOperations #GitHubModels #GeminiAPI #LangChain #RAG #VectorStore #AgenticExecution #MCP #TypeScript #Python #Vite*