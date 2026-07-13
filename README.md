# boomtick

Container-native AI-enabled workspace implementing decoupled Client-Server Automation Architecture and MCP Gateway.

## Overview

This repository contains the BoomTick developer tools, including the `td-cli` (Python) and the MCP server (TypeScript). These tools are designed to facilitate agentic developer workflows, merge conflict resolution, and PR management.

## Project Structure

- `cli/`: Python-based developer tools and SDK.
- `mcp/`: TypeScript-based Model Context Protocol (MCP) server.
- `lib/`: Shared TypeScript libraries.
- `scripts/`: Utility scripts for build, impact analysis, and workspace management.

## Installation

To set up the complete development environment, run the provided bootstrap script:

```bash
./setup-agent.sh
```

This script will:
1. Create a Python virtual environment (`.venv`).
2. Install the `td-cli` tool in editable mode.
3. Install Node.js dependencies using `pnpm`.
4. Install Playwright browsers.

Alternatively, you can use the installer for just the ported packages:

```bash
./install.sh
```

## Usage

### BoomTick CLI (`td`)

The `td` command provides a unified interface for repository and GitHub operations.

```bash
# Verify the installation
td doctor

# View current configuration
td config view

# Search for open PRs
td gh search-prs
```

### MCP Server

The MCP server can be started using the following scripts:

```bash
# Start GitHub MCP server
./mcp/start_github_mcp.sh

# Start Browser MCP server
./mcp/start_browsermcp.sh
```

## Contribution Guidelines

1. Ensure you have Node.js 24+ and Python 3.10+ installed.
2. Run `./setup-agent.sh` to initialize your workspace.
3. Use `pnpm test` and `pytest cli/tests` to run unit tests.
4. Follow the anti-pattern audit guidelines documented in `ROADMAP.md`.
