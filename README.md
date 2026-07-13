# Document packaging & usage guide for boomtick-pkg in external repositories

## Overview
This documentation outlines the final guidelines for using the boomtick-pkg tooling (both the td-cli Python package and the TypeScript MCP server) inside other repositories, as well as the packaging / release pipeline.

## Version Status
The official release version has been bumped to v0.2.0 (attached to GitHub Release v0.2.0):

- Python package: `boomtick_cli-0.2.0-py3-none-any.whl`
- Source tarball: `boomtick-pkg-0.2.0.tar.gz`
- Source zip: `boomtick-pkg-0.2.0.zip`

## How to Use boomtick-pkg in a Different Repository

### Option A: Copy the package directory (Recommended for local dev / scripting)
You can copy or mount the entire `boomtick-pkg` directory into the root of the target repository and use its installer:

1. **Copy the directory:**
   ```bash
   cp -r /path/to/tech-dancer/boomtick-pkg /path/to/other-repo/
   ```

2. **Run the installer:**
   ```bash
   cd /path/to/other-repo/boomtick-pkg
   ./install.sh
   ```
   This automatically sets up a local Python virtual environment (`.venv`), installs the `td-cli` command in editable mode, and builds the Node.js TypeScript MCP server.

### Option B: Separate package distributions
If you prefer not to keep the source files in the target repo:

#### For the Python CLI (td-cli / td):
1. **Build the wheel package:**
   ```bash
   cd boomtick-pkg/cli
   python3 -m build --wheel
   ```
2. **Install the generated .whl in the other repository:**
   ```bash
   pip install dist/boomtick_cli-0.2.0-py3-none-any.whl
   ```

#### For the TypeScript MCP Server:
1. **Compile the TypeScript code:**
   ```bash
   cd boomtick-pkg/mcp
   pnpm install
   pnpm run build
   ```
2. **Run the server directly:**
   ```bash
   node /path/to/boomtick-pkg/mcp/dist/index.js
   ```
   (Or generate a tarball using `npm pack` and install it in the target project's dependencies).
