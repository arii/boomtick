# Boomtick

Boomtick is a template repository providing foundational developer tooling, workflow orchestration, and an advanced AI review framework for autonomous agent systems. It is designed to be somewhat agnostic but currently supports Vite applications. An example of a project using these tools is `arii/tech-dancer`.

Boomtick strictly separates human-led strategic system design from agentic execution, reserving automation for repetitive engineering tasks, compiling, data validation, and operational compliance.

The repository architecture is primarily split into two main components:
- **`mcp/`**: A Model Context Protocol (MCP) server (the Boomtick MCP) designed to empower AI agents with structured access to GitHub Pull Requests, repository state, CI logs, and validation tools. It facilitates operations like conflict resolution, branch creation, and interacting with the Jules macro-agent.
- **`cli/`**: The Command-Line Interface (`td-cli`) acts as a fallback and developer toolkit for local repository automation, integrating directly with GitHub via `gh` to handle PR audits, conflict detection, and runtime consistency checks.

## Advanced AI Integration & Capabilities

Boomtick utilizes cutting-edge AI features and Native REST commands to provide seamless intelligent workflows:
- **GitHub Models Integration:** Leverage OpenAI-compatible models directly via the GitHub Models API for code reviews and blast-radius analysis.
- **Gemini API:** Built-in multi-modal capabilities powered by the Gemini API for deep contextual and visual reviews.
- **LangChain Core:** Uses `@langchain/core` abstractions for streamlined model orchestration and fallback strategies.
- **RAG & Vector Store:** Robust pipeline designed to leverage vector stores to fetch contextual knowledge for AI tasks like automated triage and overlap analysis.

## Planned Updates

To ensure seamless onboarding without the need for submodule integration, the following updates are planned:
- Composite GitHub Actions
- Docker Container Package
- PyPI Packaging
- Advanced RAG / Vector Store enhancements

## Documents

- [Agent Contracts and Standards](.agents/AGENT_CONTRACT.md): Invariant rules for agent behavior.
- [Agent Workflows and MCP Protocol](.agents/README.md): Primary tooling and MCP protocol documentation, including the three-tier tool hierarchy (MCP → `td-cli` → bash), tool mapping tables, and enforcement rules.
- [CLI Developer Tooling](cli/README.md): Documentation for `td-cli`, the Tier 2 fallback for agents when MCP tools are unavailable.
- [MCP Server Configuration](mcp/README.md): Documentation for the Boomtick MCP Server, its capabilities, tools, and setup instructions.
- [Release Process](docs/release-process.md): Documentation detailing the release pipelines and tools used.
- [Impact Analysis Integration](docs/impact-analysis-integration.md): Details on integrating and running impact analyses.
- [MCP Testing](mcp/docs/testing.md): Detailed verification steps for MCP server testing.

<hr>

*Tags: #DevAI #EngineeringOperations #GitHubModels #GeminiAPI #LangChain #RAG #VectorStore #AgenticExecution #MCP #TypeScript #Python #Vite*