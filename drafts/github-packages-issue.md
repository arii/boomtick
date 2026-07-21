# Fix @arii/boomtick-mcp package publishing to GitHub Packages registry

# Problem Statement

Currently, the `mcp` package (`@arii/boomtick-mcp`) is configured to publish to the public npm registry (`registry.npmjs.org`). The `.github/workflows/release.yml` workflow has the npm publishing step disabled due to authentication errors. Even if enabled, the package would not automatically appear on the GitHub repository's Packages page because it is lacking the necessary repository links and GitHub registry configurations in `package.json`.

# Goal

- Configure the `mcp/package.json` to publish directly to the GitHub Packages registry (`npm.pkg.github.com`).
- Properly link the package to the `arii/boomtick` repository so it shows up on the repository's packages page.
- Fix the `.github/workflows/release.yml` to authenticate and publish the package to GitHub Packages correctly.

# Non-Goals

- Migrating the Python CLI package from PyPI to GitHub Packages.
- Updating local developer workflow to pull from GitHub Packages instead of building from source (this is strictly for remote distribution).

# Proposed Approach

1.  **Update `mcp/package.json`**:
    -   Add the `repository` field linking to the GitHub repository:
        ```json
        "repository": {
          "type": "git",
          "url": "https://github.com/arii/boomtick.git"
        }
        ```
    -   Update the `publishConfig` block to target the GitHub registry:
        ```json
        "publishConfig": {
          "access": "public",
          "registry": "https://npm.pkg.github.com"
        }
        ```
2.  **Update `.github/workflows/release.yml`**:
    -   Re-enable the "Publish MCP to npm" step (remove `if: github.event_name == 'none'`).
    -   Change the `NODE_AUTH_TOKEN` secret to use `${{ secrets.GITHUB_TOKEN }}` since we are publishing to the GitHub Packages registry.
    -   Ensure the `Setup Environment` (or a node setup step before `pnpm publish`) generates an `.npmrc` file authenticated against `https://npm.pkg.github.com` using the `GITHUB_TOKEN`.
3.  **Manual Verification (Post-Merge)**:
    -   Once the package is successfully published via the GitHub Action, navigate to the organization profile (`https://github.com/arii`).
    -   If the package is not automatically linked to the repository, navigate to the package's settings, find "Connect repository", and explicitly associate it with the `boomtick` repository.
    -   Under the package's access settings, check "Inherit access from source repository (recommended)" to ensure it inherits visibility.

# Alternatives Considered

-   **Publishing to public npm (registry.npmjs.org)**: Rejected because the organization prefers consolidating internal tooling artifacts in GitHub Packages for closer repository integration.
-   **Using `.npmrc` exclusively without `publishConfig`**: Rejected because explicitly defining the registry in `package.json`'s `publishConfig` is the standard, foolproof way to ensure `pnpm publish` routes to the correct registry regardless of local environments.

# Architectural Impact

-   **Artifact Storage**: NPM packages will now be hosted on GitHub Packages alongside Docker images (`ghcr.io`).
-   **Authentication**: Consumers of the package (if private/internal in the future) will need a Personal Access Token (PAT) with `read:packages` scope to install it. Since it's public, anonymous reads may be supported depending on org settings, but explicit repository linking ensures it's easily discoverable.

# Scope

This issue covers the modification of `mcp/package.json`, `.github/workflows/release.yml`, and post-publish manual configurations on the GitHub interface to ensure the package appears under the `boomtick` repository packages list.

# Understand the Issue

The release workflow is currently disabled for NPM packages due to auth issues with the public registry. Furthermore, a package published to the public registry doesn't automatically show up on the GitHub Repo Packages page. We must point the package to `npm.pkg.github.com` and embed the `repository.url` into the package metadata.

# Determine Approach

1.  Open `mcp/package.json`.
2.  Modify the `publishConfig` to include `"registry": "https://npm.pkg.github.com"`.
3.  Add the `repository` object with `url` set to `https://github.com/arii/boomtick.git`.
4.  Open `.github/workflows/release.yml`.
5.  Locate the step named `Publish MCP to npm`.
6.  Remove the `if: github.event_name == 'none'` condition.
7.  Change the environment variable `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` to `NODE_AUTH_TOKEN: ${{ secrets.GITHUB_TOKEN }}`.
8.  Ensure an `.npmrc` file is created pointing `@arii:registry=https://npm.pkg.github.com` before the publish step in the workflow.

# Specify Scope

The changes are restricted to:
- `mcp/package.json`
- `.github/workflows/release.yml`

# DEFINITION OF DONE

1. `mcp/package.json` contains the `repository` URL and `publishConfig.registry` pointing to GitHub Packages.
2. The release workflow is re-enabled to publish the MCP package.
3. The release workflow authenticates using `GITHUB_TOKEN` instead of `NPM_TOKEN`.
4. After a release, the `@arii/boomtick-mcp` package successfully appears under the `arii/boomtick` repository's Packages page on GitHub.