# Boomtick

Container-native AI-enabled workspace implementing decoupled Client-Server Automation Architecture and MCP Gateway.

This repository contains the `boomtick` codebase (formerly `boomtick-pkg` inside `tech-dancer`), structured to be consumed as a submodule or as standalone packages.

## Architecture Overview

Boomtick is composed of:
1. **Python CLI (`cli/`)**: A tool designed to assist with automation, issue validation, PR auditing, and multi-agent coordination.
2. **TypeScript MCP Server (`mcp/`)**: A Model Context Protocol (MCP) server that exposes dev tools, GitHub API access, and workflow automation directly to AI agents.

---

## Installation & Setup

### Inside a Target Repository (as a Submodule)

To add and initialize Boomtick as a submodule in another repository:

```bash
git submodule add git@github.com:arii/boomtick.git boomtick-pkg
git submodule update --init --recursive
```

Then, run the installer:

```bash
cd boomtick-pkg
./install.sh
```

This will:
- Set up a local Python virtual environment (`.venv`) for the CLI.
- Install the `td-cli` command in editable mode.
- Build the Node.js TypeScript MCP server.

### Manual Installations

#### 1. Python CLI (td-cli)

To build and install the Python package manually:

```bash
cd cli/
python3 -m build --wheel
pip install dist/boomtick_cli-0.2.0-py3-none-any.whl
```

#### 2. TypeScript MCP Server

To compile and run the MCP server manually:

```bash
cd mcp/
pnpm install
pnpm run build
node dist/index.js
```

---

## Best Practices for Submodule Development

When developing Boomtick as a submodule in a parent project (e.g. `tech-dancer`):

1. **Submodule First, Parent Second**: Always commit and push changes inside the `boomtick-pkg` subdirectory before committing pointer updates in the parent repo.
2. **Prevent Dirty Submodule Pushes**: Configure the parent repository to check for unpushed submodule commits:
   ```bash
   git config push.recurseSubmodules check
   ```
3. **Synchronize Changes**: Run the following to update your local files:
   ```bash
   git submodule update --init --recursive
   ```

## Development & CI Validation

To ensure consistency with the CI environment, developers can run the following commands from the project root:

- **Environment Check**: `pnpm run doctor`
- **Type Checking**: `pnpm run type-check`
- **Linting**: `pnpm run lint`
- **Testing**: `pnpm run test`

These scripts delegate to the appropriate subpackages using `pnpm --filter`.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
