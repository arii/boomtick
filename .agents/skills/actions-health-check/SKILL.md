---
name: actions-health-check
description: Audit recent GitHub Actions workflow runs for repeated failures, cancellations, and slow runs without running builds or paid models. Use when reviewing CI reliability, time, or cost across repositories.
---

# GitHub Actions health check

Use an authenticated GitHub CLI and Python 3. Pass one or more `owner/repo` names. The script is read-only: it samples the latest 50 runs across workflows in each repo, without rerunning anything or calling a model.

Save this as `actions-health.py`, then run `python3 actions-health.py --limit 50 OWNER/REPO`.

```python
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
import statistics
import subprocess

parser = argparse.ArgumentParser(description="Sample recent GitHub Actions runs")
parser.add_argument("repos", nargs="+", metavar="OWNER/REPO")
parser.add_argument("--limit", type=int, default=50)
args = parser.parse_args()
if args.limit < 1:
    parser.error("--limit must be positive")

def elapsed_minutes(run):
    if run["status"] != "completed" or run["conclusion"] == "skipped":
        return None
    try:
        start, end = (
            datetime.fromisoformat(run[key].replace("Z", "+00:00"))
            for key in ("startedAt", "updatedAt")
        )
    except (AttributeError, ValueError):
        return None
    seconds = (end - start).total_seconds()
    return seconds / 60 if seconds >= 0 and start.year > 1 else None

failed = {"failure", "timed_out", "startup_failure"}
had_error = False
for repo in args.repos:
    cmd = [
        "gh", "run", "list", "--repo", repo, "--limit", str(args.limit), "--all",
        "--json", "workflowDatabaseId,workflowName,status,conclusion,startedAt,updatedAt,url",
    ]
    try:
        runs = json.loads(subprocess.check_output(cmd, text=True))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"\n{repo}: unable to fetch runs ({exc})")
        had_error = True
        continue

    print(f"\n{repo}: {len(runs)} recent runs (limit {args.limit})")
    groups = defaultdict(list)
    for run in runs:
        groups[run["workflowDatabaseId"]].append(run)
    for workflow_id, group in groups.items():
        name = next((run["workflowName"] for run in group if run["workflowName"]), "Unnamed")
        counts = Counter(
            (run["conclusion"] or "unknown") if run["status"] == "completed" else "pending"
            for run in group
        )
        times = [t for run in group if (t := elapsed_minutes(run)) is not None]
        outcomes = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
        median = f"{statistics.median(times):.1f} min (n={len(times)})" if times else "n/a"
        print(f"  {name} [{workflow_id}]: {outcomes}; median elapsed {median}")
        sample = next((run for run in group if run["conclusion"] in failed), None)
        if sample:
            print(f"    Example failed run: {sample['url']}")

raise SystemExit(1 if had_error else 0)
```

## Explain what changed

1. Report the sample size, workflow, and outcome counts. Keep cancellations, skipped runs and pending runs separate from failures. A workflow absent from this sample isn't necessarily disabled.
2. Inspect a representative failure with `gh run view RUN_ID --repo OWNER/REPO --log-failed`. Name the failing step and link its run. Don't generalize a single log to every failure, or call the test flaky without same-commit rerun evidence.
3. Read the corresponding YAML before recommending trigger, cache or concurrency changes. Check for duplicate push/PR runs, frequent schedules, and slow dependency installation. Keep required checks and deployment behavior intact.
4. Rank the fixes by likely time saved and confidence. Elapsed run time from these timestamps is a proxy, not billed runner minutes or model spend. Flag any unknown cost separately. Don't change workflows, rerun CI, or read billing data unless asked.
