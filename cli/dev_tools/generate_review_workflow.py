#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import re

def run_command(cmd: list) -> str:
    try:
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
        return result.stdout.strip() + ("\n" + result.stderr.strip() if result.stderr.strip() else "")
    except Exception as e:
        return f"Execution failed: {e}"

def main():
    parser = argparse.ArgumentParser(description="Generate deterministic review workflow plan.")
    parser.add_argument("--pr", required=True, help="Pull Request number")
    parser.add_argument("--issue", required=False, help="Issue number")
    args = parser.parse_args()

    pr_number = args.pr
    issue_number = args.issue

    print(f"Generating workflow plan for PR #{pr_number}...")

    # 1. Environment Validation
    env_output = run_command(["bash", "dev-tools/verify.sh"])

    # 2. Issue Validation
    issue_output = "No issue number provided."
    if issue_number:
        issue_output = run_command(["td-cli", "gh", "validate-issue", "--issue-number", issue_number])

    # 3. Conflict Detection
    conflict_output = run_command(["td-cli", "gh", "conflicts", "--pr", pr_number])

    # 4. PR Context Generation
    run_command(["td-cli", "gh", "audit-pr", pr_number, "--fetch"])

    pr_context_file = f"boomtick-pkg/cli/logs/reviews/pr-context-{pr_number}.md"
    pr_summary = ""
    ci_status = ""
    failure_logs = ""

    if not os.path.exists(pr_context_file):
        print(f"Error: Context file {pr_context_file} was not generated.", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(pr_context_file):
        with open(pr_context_file, "r") as f:
            pr_context_content = f.read()

        summary_match = re.search(r'(# PR Context:.*?)(?=## CI Status|## Diff Stats)', pr_context_content, re.DOTALL)
        if summary_match:
            pr_summary = summary_match.group(1).strip()

        ci_status_match = re.search(r'(## CI Status.*?)(?=## Diff Stats|## Failing Tests)', pr_context_content, re.DOTALL)
        if ci_status_match:
            ci_status = ci_status_match.group(1).strip()

        failure_logs_match = re.search(r'(## Failing Tests.*?)(?=## Diff Stats|$)', pr_context_content, re.DOTALL)
        if failure_logs_match:
            failure_logs = failure_logs_match.group(1).strip()

        if not pr_summary: pr_summary = "See " + pr_context_file
        if not ci_status: ci_status = "See " + pr_context_file
        if not failure_logs: failure_logs = "See " + pr_context_file

    # 5. Impact Analysis
    impact_output = "Not available."
    if os.path.exists("scripts/impact-analysis.ts"):
        impact_output = run_command(["npx", "tsx", "scripts/impact-analysis.ts"])

    # 6. Existing Review Data
    gemini_review = "None."
    if os.path.exists("artifacts/gemini-code-review.md"):
        with open("artifacts/gemini-code-review.md", "r") as f:
            gemini_review = f.read()

    github_models_review = "None."
    if os.path.exists("artifacts/github-models-code-review.md"):
        with open("artifacts/github-models-code-review.md", "r") as f:
            github_models_review = f.read()

    # Fix: Ensure all {pr_number} template variables in markdown are resolved

    # Generate workflow plan
    plan_path = f"boomtick-pkg/cli/logs/workflows/workflow-plan-pr-{pr_number}.md"
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)

    with open(plan_path, "w") as f:
        f.write(f"""# Workflow Plan: PR #{pr_number}

## Agent Instructions

- setup complete
- validation complete
- context collected
- diagnostics collected

Agent must not repeat these steps.

---

## Workflow State

[x] Environment Validation
[x] Issue Validation
[x] Conflict Detection
[x] Context Collection
[x] Impact Analysis
[ ] Review Analysis
[ ] Review Authoring
[ ] Completion Verification

---

## Collected Context

### Validation Output
```text
{env_output}
```

### Issue Validation Output
```text
{issue_output}
```

### Conflict Output
```text
{conflict_output}
```

### PR Summary
Relevant excerpts from:
`{pr_context_file}`

```text
{pr_summary}
```

### CI Status
Relevant excerpts:
```text
{ci_status}
```

### Failure Logs
Relevant excerpts:
```text
{failure_logs}
```

### Impact Analysis
Relevant excerpts:
```text
{impact_output}
```

### Existing AI Reviews
**Gemini:**
```markdown
{gemini_review}
```

**GitHub Models:**
```markdown
{github_models_review}
```

---

## Allowed Files

Agent may read:
`.agents/workflows/REVIEW_INSTRUCTIONS.md`
`boomtick-pkg/cli/logs/reviews/pr-review-{pr_number}.md`

---

## Writable Files

Agent may modify:
`boomtick-pkg/cli/logs/reviews/pr-review-{pr_number}.md`

---

## Remaining Tasks

### Step 1
Review supplied evidence.

### Step 2
Populate review file.

### Step 3
Verify:
- JSON valid
- checklist complete
- comments reference valid diff lines

---

## Completion Criteria

All checklist items resolved.

No placeholders remain.

No guessed line numbers.

No invented findings.

Every finding must reference supplied evidence.

---

## Final Output

Output exactly:

```bash
td-cli gh audit-pr {pr_number} --submit --cleanup
```

Only after successful completion.
""")

    print(f"Workflow plan generated: {plan_path}")

if __name__ == "__main__":
    main()
