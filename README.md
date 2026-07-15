# DevAI Systems & Engineering Operations

This project serves as the centralized task tracker and roadmap for DevAI and AI Engineering infrastructure. It manages the development lifecycle of autonomous agent systems, custom developer tooling, and automated publishing pipelines.

The architectural vision emphasizes a strict separation between human-led strategy and agentic execution. Strategic system design, architectural planning, and project goals are defined exclusively by human oversight. Automation is reserved for repetitive engineering tasks, compiler pipelines, data validation, and ensuring compliance with platform-level policies.

The core operational scope encompasses several integrated tracks. Foundational tooling development focuses on decoupling core utilities for independent deployment, while the advanced AI review framework centers on intelligent codebase analysis and multi-modal feedback loops. Agentic workflow orchestration is dedicated to maintaining repository health, automated triage, and conflict resolution. Parallel development systems manage concurrent agent edits to ensure merge safety and system stability.

Additionally, the project incorporates programmatic commercial automation pipelines for managing asset workflows and storefront integrations. Finally, the growth engineering and data science track processes telemetry and publishing metrics to inform development priorities and ensure content and operational compliance.

## Documents

* [Agent Contracts and Standards](.agents/AGENT_CONTRACT.md): Invariant rules for agent behavior.
* [Agent Workflows](.agents/README.md): Primary Tooling and MCP Protocol, including the three-tier tool hierarchy (MCP → `td-cli` → bash), the full tool mapping table, and enforcement rules.
* [CLI Developer Tooling](cli/README.md): Developer tooling for the BoomTick repository. The primary entry point is `td-cli`, but agents should always call `boomtick-mcp` Tier 1 tools first — `td-cli` is the Tier 2 fallback.
* [MCP Server Configuration](mcp/README.md): A Model Context Protocol (MCP) server designed to empower AI agents with structured access to GitHub Pull Requests, repository state, CI logs, and validation tools.
* [Release Process](docs/release-process.md): Documentation on the release process.
* [Impact Analysis Integration](docs/impact-analysis-integration.md): Documentation on impact analysis integration.
* [MCP Testing](mcp/docs/testing.md): Detailed verification steps for MCP server testing.
