# Fix ERR_MODULE_NOT_FOUND when running check-visual-changes.ts in tech-dancer

## UNDERSTAND THE ISSUE

When the `boomtick` repository is used as a submodule in a downstream repository like `tech-dancer`, the composite action `mcp/actions/impact-analysis/action.yml` attempts to execute the `check-visual-changes.ts` script. The GitHub Actions runner currently throws an `ERR_MODULE_NOT_FOUND` error because Node.js (`tsx`) is unable to resolve the correct path for the script when it is called with `../../../` pathing containing relative dots inside an absolute path string (under node `v24.x`).

## DETERMINE APPROACH

Update the "Check if visual changes exist" step to use robust path resolution using shell fallback logic and `realpath`, similar to how `send-jules-impact.py` is invoked.

Instead of directly appending `../../../scripts/check-visual-changes.ts` to `pnpm exec tsx`, we should:
1. Try resolving the file natively via `[ -f "scripts/check-visual-changes.ts" ]` in case it runs in a context where `boomtick` is the root.
2. Fall back to `${{ github.action_path }}/../../../scripts/check-visual-changes.ts` if running as a submodule.
3. Critically, use `realpath` to flatten the path string, eliminating the `../` segments that cause `ERR_MODULE_NOT_FOUND` with node module resolution.
4. Default to outputting `changed_routes=0` and skipping if the script cannot be found.

## SPECIFY SCOPE

- Updating the bash script inside the "Check if visual changes exist" step within `mcp/actions/impact-analysis/action.yml`.
- Implementing path validation and fallback using `realpath`.

## DEFINITION OF DONE

- The "Check if visual changes exist" step in `mcp/actions/impact-analysis/action.yml` is updated to gracefully resolve `scripts/check-visual-changes.ts` using `realpath`.
- The bash step includes conditional fallbacks (`if [ -f ... ]`) to gracefully skip or output default values (`changed_routes=0`) if the script is not found.
- The workflow correctly passes when `boomtick` is included as a submodule in a superproject without throwing `ERR_MODULE_NOT_FOUND`.
