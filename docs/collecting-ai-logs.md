# Collecting and Auditing AI Review Logs

This guide describes how to use the provided shell scripts to download and audit the AI code review logs (specifically from the `Deployment Impact Analysis` workflow) directly to your local machine.

## Prerequisites

You must have the GitHub CLI (`gh`) installed and authenticated.

1. **Install GitHub CLI**:
   - macOS: `brew install gh`
   - Linux: `sudo apt install gh`

2. **Authenticate**:
   Run `gh auth login` and follow the prompts. You need the `repo` scope to read actions and download artifacts.

## Scripts Overview

These scripts are located in the `scripts/` directory. By default, they will output artifacts into a local `collected-logs/` (or `runs/`) directory, which is excluded from version control via `.gitignore`.

### `scripts/download_run.sh`

Downloads the `deployment-review` artifact for a single, specific GitHub Actions run.

**Usage:**
```bash
./scripts/download_run.sh <RUN_ID>
```
**Example:**
```bash
./scripts/download_run.sh 29507773139
```

**Environment Variables:**
* `REPO` (Optional): Override the target repository. Defaults to `arii/boomtick`.

### `scripts/bulk_collect_runs.sh`

Fetches the most recent workflow runs (defaults to 50) and downloads their `deployment-review` artifacts in parallel. This is incredibly useful for gathering historical data to audit AI review performance, quota issues, or hallucination rates.

**Usage:**
```bash
./scripts/bulk_collect_runs.sh
```

**Environment Variables:**
* `WORKFLOW_NAME` (Optional): The workflow to target. Defaults to `Deployment Impact Analysis`.
* `REPO` (Optional): Override the target repository. Defaults to `arii/boomtick`.
* `LIMIT_RUNS` (Optional): Number of recent runs to evaluate. Defaults to `50`.

**Example:**
```bash
LIMIT_RUNS=10 WORKFLOW_NAME="Smoke Test Impact Analysis" ./scripts/bulk_collect_runs.sh
```

## Auditing the Output

Once downloaded, your directory will populate with runs, for example:

```text
collected-logs/
├── run-29507773139/
│   ├── gemini-code-review.md
│   ├── github-models-code-review-verdict.json
│   └── logs/
│       └── ai/
│           ├── review-run.jsonl
```

You can then write custom scripts (e.g. in Python or `jq`) to parse the JSON verdicts and JSONL log trails to extract patterns.
