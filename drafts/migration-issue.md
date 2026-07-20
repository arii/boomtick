# Migrate downstream consumers from Git submodule to Zero-Submodule integration

# Problem Statement

Currently, downstream consumers (such as `tech-dancer`) integrate `boomtick` as a Git submodule. This approach introduces overhead in managing submodule pointers, increases CI pipeline latency due to cloning deeply nested submodules, and tightens coupling between the filesystem layout of the parent repository and `boomtick`. A streamlined "Zero-Submodule integration" approach is already supported and documented in `docs/onboarding.md`, but consumers have not yet been migrated to it.

# Goal

- Migrate downstream repositories (e.g., `tech-dancer`) to use Boomtick's composite GitHub Actions directly (e.g., `uses: arii/boomtick/.github/actions/...@main`) instead of relying on a local `mcp` Git submodule.
- Remove the `mcp/` submodule from the downstream repository.
- Ensure all GitHub Actions workflows (chatops, ci-repair, issue-operations) function seamlessly via the remote reusable actions.

# Non-Goals

- Deprecating the `td-cli` developer tool or MCP server for local development. This migration primarily targets CI pipeline integration and remote AI reviews.
- Changes to `td-cli` or `boomtick-mcp` implementations.

# Proposed Approach

1.  **Remove Submodule**: In the downstream repository (e.g., `tech-dancer`), execute the following from the root to safely detach the submodule:
    ```bash
    git submodule deinit -f mcp
    git rm -f mcp
    rm -rf .git/modules/mcp
    ```
2.  **Update GitHub Workflows**: Modify the following downstream GitHub Action workflow files located in `.github/workflows/`:
    - `chatops-trigger.yml`
    - `ci-repair.yml`
    - `issue-operations.yml`

    You must replace all local relative action paths referencing the `mcp` submodule with absolute remote references to the `arii/boomtick` repository. Specifically:
    - Change `uses: ./mcp/.github/actions/setup-workspace` to `uses: arii/boomtick/.github/actions/setup-workspace@main`
    - Change `uses: ./mcp/.github/actions/chatops` to `uses: arii/boomtick/.github/actions/chatops@main`
    - Change `uses: ./mcp/.github/actions/ci-repair` to `uses: arii/boomtick/.github/actions/ci-repair@main`
    - Change `uses: ./mcp/.github/actions/issue-operations` to `uses: arii/boomtick/.github/actions/issue-operations@main`
    - Change `uses: ./mcp/.github/actions/ai-review` to `uses: arii/boomtick/.github/actions/ai-review@main`

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

This issue covers the migration of existing downstream GitHub Actions workflows (`chatops-trigger.yml`, `ci-repair.yml`, `issue-operations.yml`) to directly use `arii/boomtick/.github/actions/*@main` and the removal of the Git submodule directory (`mcp`).

# Understand the Issue

The underlying problem stems from the legacy choice of embedding Boomtick workflows via a submodule. According to `docs/onboarding.md`, a Zero-Submodule Strategy is now preferred because referencing BoomTick's composite actions directly via `uses: arii/boomtick/.github/actions/...@main` removes direct filesystem dependency coupling.

# Determine Approach

To execute this transition safely, the implementing engineer must perform the following explicit steps:
1. In the target consumer repo (e.g. `tech-dancer`), open the `.github/workflows/chatops-trigger.yml`, `.github/workflows/ci-repair.yml`, and `.github/workflows/issue-operations.yml` files.
2. Perform a strict string replacement on the `uses:` declarations:
   - Replace any occurrence of `uses: ./mcp/.github/actions/setup-workspace` with `uses: arii/boomtick/.github/actions/setup-workspace@main`.
   - Replace any occurrence of `uses: ./mcp/.github/actions/chatops` with `uses: arii/boomtick/.github/actions/chatops@main`.
   - Replace any occurrence of `uses: ./mcp/.github/actions/ci-repair` with `uses: arii/boomtick/.github/actions/ci-repair@main`.
   - Replace any occurrence of `uses: ./mcp/.github/actions/issue-operations` with `uses: arii/boomtick/.github/actions/issue-operations@main`.
   - Replace any occurrence of `uses: ./mcp/.github/actions/ai-review` with `uses: arii/boomtick/.github/actions/ai-review@main`.
3. Verify that all required secrets (e.g., `GITHUB_TOKEN`, `JULES_API_KEY`) continue to map correctly to the action inputs as defined in the remote composite actions.
4. Execute `git submodule deinit -f mcp` and `git rm -f mcp` to formally detach and remove the submodule from the repository, followed by `rm -rf .git/modules/mcp`.

# Specify Scope

The boundaries of this issue strictly encompass:
- Alteration of exactly three downstream workflow files: `.github/workflows/chatops-trigger.yml`, `.github/workflows/ci-repair.yml`, and `.github/workflows/issue-operations.yml`.
- Modification of downstream `.gitmodules` and local workspace to completely remove the `mcp/` directory.
- Ensuring the Python-based `td-cli` remains accessible via the newly invoked composite actions (e.g., `setup-workspace` caching and installation).

# DEFINITION OF DONE

1. The `mcp/` directory (or wherever the `boomtick` submodule is located) is entirely removed from the downstream repository.
2. `.gitmodules` no longer contains the `boomtick` submodule.
3. All `.github/workflows/*.yml` files reference `arii/boomtick/.github/actions/*@main` instead of local paths.
4. CI workflows execute successfully without relying on the submodule.