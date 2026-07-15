# Release Process

boomtick uses automated release pipelines for both the Python CLI and the TypeScript MCP tools.

## Versioning Strategy

We use Semantic Versioning (SemVer) for all components.

- **CLI**: Versions are managed in `cli/pyproject.toml`.
- **MCP**: Versions are managed in `mcp/package.json`.

## Triggering a Release

Releases are triggered by pushing specific Git tags:

- **CLI Release**: Push a tag matching `cli-v*` (e.g., `cli-v0.2.1`).
- **MCP Release**: Push a tag matching `mcp-v*` (e.g., `mcp-v0.2.1`).

### Step-by-Step Instructions

1. **Update Version**:
   - For CLI: Update `version` in `cli/pyproject.toml`.
   - For MCP: Run `pnpm --filter @arii/boomtick-mcp version <patch|minor|major>`.

2. **Commit and Push Changes**:
   ```bash
   git add .
   git commit -m "chore: bump version to x.y.z"
   git push origin main
   ```

3. **Create and Push Tag**:
   ```bash
   # For CLI
   git tag cli-v0.2.1
   git push origin cli-v0.2.1

   # For MCP
   git tag mcp-v0.2.1
   git push origin mcp-v0.2.1
   ```

## Automated Pipelines

### Release CLI (`.github/workflows/release-cli.yml`)
- Triggers on `cli-v*` tags.
- Runs CLI unit tests.
- Builds MCP tools and bundles them into the CLI distribution.
- Syncs schemas and contracts.
- Builds the Python package (`sdist` and `wheel`).
- Publishes to PyPI.
- Creates a GitHub Release with generated notes and artifacts.

### Release MCP (`.github/workflows/release-mcp.yml`)
- Triggers on `mcp-v*` tags.
- Runs MCP unit tests.
- Builds the TypeScript project.
- Publishes to npm (under the `@arii` scope).
- Creates a GitHub Release with generated notes.

## Manual Dispatch

Both workflows can be triggered manually via the GitHub Actions UI for dry-runs or debugging.
