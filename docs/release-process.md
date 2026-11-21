# Release Process

Releases are driven by one workflow, [`.github/workflows/release.yml`](../.github/workflows/release.yml) ("Release Orchestrator"). It covers three targets: the Python CLI (`boomtick-cli` on PyPI), the MCP server (`@arii/boomtick-mcp` on npm) and the composite GitHub Action.

## Versioning

Semantic Versioning for every component.

- **CLI**: version in `cli/pyproject.toml`.
- **MCP**: version in `mcp/package.json`.
- **Action**: git tags only (`action-vX.Y.Z`).

`release-please` (config in `release-please-config.json`, state in `.release-please-manifest.json`) opens release PRs for `cli` and `mcp` from commits on `main`.

## Conventional Commits requirement

Use [Conventional Commits](https://www.conventionalcommits.org/) (`fix: ...`, `feat: ...`, `refactor: ...`) for every commit. `release-please` parses that format to choose version bumps. A commit such as `Refactor ...` or `Fix ...` without the conventional prefix makes it skip the affected component's release PR.

## Triggering a release

Push a tag. The workflow picks the target from the tag prefix.

| Tag | Target |
| :--- | :--- |
| `cli-v*` (e.g. `cli-v0.2.1`) | CLI |
| `mcp-v*` (e.g. `mcp-v0.2.1`) | MCP |
| `action-v*` (e.g. `action-v0.2.0`) | Action |

Steps:

1. Update the version (CLI: `cli/pyproject.toml`; MCP: `pnpm --filter @arii/boomtick-mcp version <patch|minor|major>`), or merge the `release-please` PR.
2. Commit and push to `main`.
3. Tag and push:
   ```bash
   git tag cli-v0.2.1
   git push origin cli-v0.2.1
   ```

## What the workflow does

For tag pushes, a non-dry-run is implied. Steps run according to the target:

- MCP target: run MCP tests, build, publish to npm.
- CLI target: run CLI tests, build MCP and bundle it into the CLI, build `sdist` and `wheel`, publish to PyPI, then build and push the Docker image (`ghcr.io/arii/boomtick`).
- All targets: build MCP, run `pnpm run verify:schemas`, then create a GitHub Release with `--generate-notes` (CLI artifacts are attached when present).
- Action target: move the floating major tag (for example `action-v0`) to the new release.

## Manual dispatch

`workflow_dispatch` takes a `target` (`cli`, `mcp`, `action`, `all`) and a `dry_run` flag. `dry_run` defaults to `true`, which builds and tests without publishing.

## Changelog

`CHANGELOG.md` files are maintained by `release-please`. Nothing else updates them.
