import os
import sys
import argparse
import subprocess

def run_command(cmd: list) -> str:
    try:
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
        return result.stdout.strip() + ("\n" + result.stderr.strip() if result.stderr.strip() else "")
    except Exception as e:
        return f"Execution failed: {e}"

def main():
    parser = argparse.ArgumentParser(description="Generate deterministic aggregate PRs workflow plan.")
    args = parser.parse_args()

    print("Generating workflow plan for Aggregate PRs...")

    # 1. Environment Validation
    env_output = run_command(["bash", "boomtick-pkg/cli/verify.sh"])

    # 2. Get Open PRs (Limit 100 per conventions)
    prs_output = run_command(["td-cli", "gh", "overlaps", "--limit", "100"])

    # Generate workflow plan
    plan_path = "boomtick-pkg/cli/logs/workflows/workflow-plan-aggregate-prs.md"
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)

    with open(plan_path, "w") as f:
        f.write(f"""# Workflow Plan: Aggregate PRs

## Agent Instructions

- setup complete
- validation complete
- open PRs retrieved

Agent must not repeat these steps.

---

## Workflow State

[x] Environment Validation
[x] Retrieve Open PRs
[ ] Review Overlaps
[ ] Consolidate/Abandon PRs
[ ] Completion Verification

---

## Collected Context

### Validation Output
```text
{env_output}
```

### Open PRs Output
```text
{prs_output}
```

---

## Allowed Files

Agent may read:
`.agents/workflows/REVIEW_INSTRUCTIONS.md`

---

## Writable Files

Agent may modify:
(Any relevant branch or PR metadata using `td-cli`)

---

## Remaining Tasks

### Step 1
Review the overlap output.

### Step 2
Use `td-cli gh` commands to merge, close, or consolidate redundant pull requests.

### Step 3
Verify all related PRs have been appropriately tagged or closed.

---

## Completion Criteria

Overlapping functionality identified and resolved.

""")

    print(f"Workflow plan generated: {plan_path}")

if __name__ == "__main__":
    main()
