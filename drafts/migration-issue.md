# Migrate downstream consumers from Git submodule to Zero-Submodule integration

# Problem Statement

Currently, downstream consumers (such as `tech-dancer`) integrate `boomtick` as a Git submodule. This approach introduces overhead in managing submodule pointers, increases CI pipeline latency due to cloning deeply nested submodules, and tightens coupling between the filesystem layout of the parent repository and `boomtick`. A streamlined "Zero-Submodule integration" approach is already supported and documented in `docs/onboarding.md`, but consumers have not yet been migrated to it.

# Goal

- Migrate downstream repositories (e.g., `tech-dancer`) to utilize Boomtick's composite GitHub Actions directly (e.g., `uses: arii/boomtick/.github/actions/...@main`) instead of relying on a local `mcp` Git submodule.
- Remove the `mcp/` submodule from the downstream repository.
- Ensure all CI workflows (chatops, ci-repair, issue-operations) function seamlessly via the remote reusable actions.

# Non-Goals

- Deprecating the `td-cli` developer tool or MCP server for local development. This migration primarily targets CI pipeline integration and remote AI reviews.
- Changes to the underlying implementations of `td-cli` or `boomtick-mcp`.

# Proposed Approach

1.  **Remove Submodule**: In the downstream repository (e.g., `tech-dancer`), execute `git submodule deinit -f mcp` and `git rm -f mcp` to remove the submodule.
2.  **Update GitHub Workflows**: Modify all downstream GitHub Action workflow files (e.g., `.github/workflows/chatops-trigger.yml`, `.github/workflows/ci-repair.yml`, `.github/workflows/issue-operations.yml`) to replace local path references with Boomtick's composite action references.
    -   Example: Replace `uses: ./mcp/.github/actions/setup-workspace` with `uses: arii/boomtick/.github/actions/setup-workspace@main`.
    -   Example: Replace `uses: ./mcp/.github/actions/chatops` with `uses: arii/boomtick/.github/actions/chatops@main`.
3.  **Local Tooling Access (If applicable)**: For developers needing `td-cli` locally, rely on the `boomtick-cli` PyPI package installation, which will be facilitated by the updated remote `setup-workspace` action.
4.  **Verify Setup**: Run `pnpm run verify:schemas` and run the CI test suite to ensure the migration did not break the downstream workflows.

# Alternatives Considered

-   **Retaining the Submodule approach**: Rejected because `docs/onboarding.md` explicitly calls out the "Zero-Submodule Strategy" as the preferred path to decouple workflows from the direct filesystem dependency tree and speed up CI pipelines.
-   **Publishing as a Private npm/pip Dependency Only**: Rejected (as noted in `docs/onboarding.md`) because local repository actions require tight access to worktrees and local filesystems, which is best handled via submodules for deep local work, but GitHub Actions are best served by the remote composite actions.

# Architectural Impact

-   **Zero-Submodule Integration**: Downstream CI workflows will fetch Boomtick's composite actions dynamically at runtime in GitHub Actions.
-   **Path Resolution**: The `.github/actions/setup-workspace` composite action already implements dynamic path resolution utilizing `${{ github.action_path }}` to securely find the correct `td-cli` installation path regardless of whether Boomtick is a submodule or invoked remotely.
-   **Reduced CI Overhead**: CI runs will be faster as they no longer need to execute `git submodule update --init --recursive`.

# Scope

This issue covers the migration of existing downstream GitHub Actions workflows (specifically in consumer repos like `tech-dancer`) to directly use `arii/boomtick/.github/actions/*` and the removal of the Git submodule.

# UNDERSTAND THE ISSUE

The underlying problem stems from the legacy choice of embedding Boomtick workflows via a submodule. According to `docs/onboarding.md`, a Zero-Submodule Strategy is now preferred because referencing BoomTick's composite actions directly via `uses: arii/boomtick/.github/actions/...@main` removes direct filesystem dependency coupling.

# DETERMINE APPROACH

To execute this transition safely:
1. Identify all occurrences of `./mcp/.github/actions/` in the `tech-dancer` (or target consumer repo) `.github/workflows/` YAML files using text search.
2. Substitute those lines with the equivalent `arii/boomtick/.github/actions/...@main` references.
3. Validate that the required secrets (e.g., `GITHUB_TOKEN`, `JULES_API_KEY`) map correctly to the action inputs as expected by the composite actions defined in Boomtick.
4. Finally, formally detach and remove the `mcp` submodule from the `.gitmodules` and repository structure.

# SPECIFY SCOPE

The boundaries of this issue strictly encompass:
- Alteration of downstream `.github/workflows/*.yml` files.
- Modification of downstream `.gitmodules` and local workspace to remove the `mcp/` directory.
- Ensuring the Python-based `td-cli` remains accessible via the newly invoked composite actions (e.g., `setup-workspace` caching and installation).

# DEFINITION OF DONE

1. The `mcp/` directory (or wherever the `boomtick` submodule is located) is entirely removed from the downstream repository.
2. `.gitmodules` no longer contains the `boomtick` submodule.
3. All `.github/workflows/*.yml` files reference `arii/boomtick/.github/actions/*@main` instead of local paths.
4. CI workflows execute successfully without relying on the submodule.
