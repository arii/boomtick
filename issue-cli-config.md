# Draft: Fix Config Initialization Error in CLI when run outside repository
## Problem Statement
When running the command `td agent cancel <session_id>` (and potentially others) outside of the repository directory (e.g., in `~`), the CLI crashes with `ValueError: Missing required configuration: github_repo. Please provide it in project_config.json.`. This happens because `get_config()` fails to detect the `project_config.json` file or remote git origins when not executing within the project workspace, causing a hard failure before the command can execute.

## Goal
Make the `dev_tools/config.py` loading process more resilient so that commands that don't strictly require `project_config.json` can still execute when run outside the repository, or at least provide a graceful error message rather than a raw Python traceback.

## Non-Goals
*   We will not change how `td-cli` is installed globally.
*   We will not make `github_repo` optional for commands that actually require it.

## Proposed Approach
1.  Investigate `cli/dev_tools/config.py:__post_init__` to see where the `ValueError` is raised.
2.  Delay the validation of `github_repo` and `vite_base_path` until they are actually accessed, or handle the `ValueError` gracefully within the CLI entrypoint (`cli/dev_tools/cli.py`) so it outputs a user-friendly error (like `CLIError`) instead of crashing.
3.  Ensure `load_project_config` handles the missing file without throwing if possible.

## Alternatives Considered
*   Hardcode a fallback repository name. This is dangerous because it could lead to actions being performed against the wrong repository.
*   Require users to always set the `GITHUB_REPOSITORY` environment variable. While good practice, it doesn't solve the immediate crash experience.

## Architectural Impact
Improves the user experience and resilience of the CLI tool when used globally or in automated environments where the working directory might not be the repository root.

## Scope
*   `cli/dev_tools/config.py`
*   `cli/dev_tools/cli.py`

## UNDERSTAND THE ISSUE
The traceback shows that `PROJECT_CONFIG = get_config()` happens at the module level in `cli.py`. Since it's evaluated upon import, any CLI command will fail if `project_config.json` is missing, even if the specific command (like `agent cancel`) does not actually need the `github_repo` config.

## DETERMINE APPROACH
Modify `cli/dev_tools/cli.py` to lazily instantiate `PROJECT_CONFIG`, or modify `ProjectConfig.__post_init__` in `cli/dev_tools/config.py` to not raise a `ValueError` immediately on load, but rather when the missing properties are accessed. Since `ProjectConfig` is a dataclass, we could use `@property` for `github_repo` that raises the error only when accessed, or change the `__post_init__` to just log a warning and let downstream functions handle the missing value. A safer approach for backward compatibility is wrapping the module-level instantiation in `cli.py` or providing a safe getter.

## SPECIFY SCOPE
*   `cli/dev_tools/config.py`
*   `cli/tests/test_config.py`

## DEFINITION OF DONE
*   Running `td-cli` commands outside the repository does not produce a raw traceback.
*   Required configurations still throw an appropriate `CLIError` when an operation genuinely requires them.
