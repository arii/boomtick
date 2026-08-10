# Fix `td-cli: command not found` in Verify CI Metrics step of impact-analysis action

# Problem Statement

The parent submodule integration fails during the `Deployment Impact Analysis` job (specifically in the `Verify CI Metrics` step). The CI logs show a failure with `td-cli: command not found`. For example, this issue was observed in run `https://github.com/arii/tech-dancer/actions/runs/30965987188/job/92181223332`.

Yes, this failure is due to boomtick code. The root cause is that the `Verify CI Metrics` step in `mcp/actions/impact-analysis/action.yml` forcefully overwrites `$PATH` to only include local bin directories (`export PATH="$HOME/.local/bin:/github/home/.local/bin:$PATH"`), but fails to include the dynamic `PYTHON_SCRIPTS_PATH` where `pip install --break-system-packages` installs user binaries (like `td-cli`), e.g., `/usr/local/bin` or `/app/.venv/bin`.

# Goal

- Fix the `td-cli: command not found` error in the `Verify CI Metrics` step of the `mcp/actions/impact-analysis/action.yml` action.
- Ensure `td-cli` can be successfully resolved when `verify-metrics` is called.

# Non-Goals

- Refactoring the entire setup-workspace logic.
- Fixing other workflow files unless they have the exact same problem.

# Proposed Approach

Update `mcp/actions/impact-analysis/action.yml`. In the `Verify CI Metrics` step, replace the hardcoded `PATH` export with the dynamic resolution logic used successfully in `.github/actions/setup-workspace/action.yml`.

Specifically, before resolving `td-cli`, inject the Python scripts path dynamically:
```bash
        # Inject custom CLI path for td-cli resolution
        PYTHON_SCRIPTS_PATH=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))")
        export PATH="$PYTHON_SCRIPTS_PATH:$HOME/.local/bin:/github/home/.local/bin:$PATH"
```

# Alternatives Considered

- Hardcoding `/usr/local/bin` in the `PATH` string. This was rejected because Python environments (such as `.venv`) or different OS runners might resolve user binaries to different paths. Dynamically resolving via `sysconfig` is safer and aligns with `setup-workspace/action.yml`.
- Re-running the `setup-workspace` composite action inside the `Verify CI Metrics` step. This was rejected because it would unnecessarily re-install Node.js and dependencies, slowing down the CI pipeline.

# Architectural Impact

This change increases robustness in how the `impact-analysis` composite action resolves CLI dependencies in isolated workflow steps. It creates better parity with how `.github/actions/setup-workspace/action.yml` guarantees executable resolution.

# Scope

This issue affects only the `mcp/actions/impact-analysis/action.yml` GitHub Action workflow file, specifically the `Verify CI Metrics` step.

# UNDERSTAND THE ISSUE

The issue stems from Python's package installation behavior on GitHub runners. When `td-cli` is installed in `setup-workspace`, it might land in a non-standard scripts directory (e.g., `/usr/local/bin` or a virtual environment bin) depending on the Python environment. The `Verify CI Metrics` step in `impact-analysis/action.yml` blindly prepends `$HOME/.local/bin:/github/home/.local/bin` to the path, missing the actual `PYTHON_SCRIPTS_PATH` where `td-cli` lives.

# DETERMINE APPROACH

We will mirror the established pattern from `.github/actions/setup-workspace/action.yml` which dynamically resolves the Python script path and adds it to the `$PATH` before attempting to invoke `td-cli`.

# SPECIFY SCOPE

File to modify:
- `mcp/actions/impact-analysis/action.yml`

# DEFINITION OF DONE

- The `Verify CI Metrics` step in `mcp/actions/impact-analysis/action.yml` dynamically sets `PYTHON_SCRIPTS_PATH` and prepends it to `$PATH`.
- `td-cli gh summary-report` and `td-cli gh verify-metrics` successfully resolve and execute.
- Unit and integration tests pass successfully without regression.
