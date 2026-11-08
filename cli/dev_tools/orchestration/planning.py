"""Review/aggregation workflow planning."""
import json
import os
import re
import subprocess
from collections import defaultdict
from typing import Any, Dict, Optional
from dev_tools.utils import get_github_client
from dev_tools.orchestration.merge_gate import MergeGateMixin
import dev_tools.orchestrator



class PlanningMixin(MergeGateMixin):
    """Review/aggregation workflow planning."""

    def generate_review_workflow(self, prNumber: int, issueNumber: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        if "prNumber" in kwargs:
            prNumber = kwargs["prNumber"]
        if "issue_number" in kwargs and issueNumber is None:
            issueNumber = kwargs["issue_number"]
        """Generates a deterministic review workflow plan for an agent."""
        context_data = self._gather_review_workflow_context(prNumber, issueNumber)
        return self._render_workflow_plan(prNumber, context_data)

    def _gather_review_workflow_context(self, prNumber: int, issueNumber: Optional[int] = None) -> Dict[str, Any]:
        # 1. Environment Validation
        env_res = self.runtime_check()
        env_output = f"Runtime OK: node {env_res['node']}, pnpm {env_res['pnpm']}"

        # 2. Issue Validation
        issue_output = "No issue number provided."
        if issueNumber:
            res = self.validate_issue(issueNumber=issueNumber)
            issue_output = json.dumps(res, indent=2)

        # 3. Conflict Detection
        conflicts = self.handle_detect_conflicts(pr_num=prNumber)
        conflict_output = json.dumps(conflicts, indent=2)

        # 4. PR Context Generation
        audit_res = self.audit_pr(prNumber, fetch=True)
        pr_context_file = audit_res["files"]["context"]

        pr_summary = ""
        ci_status = ""
        failure_logs = ""

        if os.path.exists(pr_context_file):
            with open(pr_context_file, "r", encoding="utf-8") as f:
                pr_context_content = f.read()

            summary_match = re.search(
                r"(# PR Context:.*?)(?=## CI Status|## Diff Stats)", pr_context_content, re.DOTALL
            )
            if summary_match:
                pr_summary = summary_match.group(1).strip()

            ci_status_match = re.search(
                r"(## CI Status.*?)(?=## Diff Stats|## Failing Tests)",
                pr_context_content,
                re.DOTALL,
            )
            if ci_status_match:
                ci_status = ci_status_match.group(1).strip()

            failure_logs_match = re.search(r"(## Failing Tests.*?)(?=## Diff Stats|$)", pr_context_content, re.DOTALL)
            if failure_logs_match:
                failure_logs = failure_logs_match.group(1).strip()

            if not pr_summary:
                pr_summary = "See " + pr_context_file
            if not ci_status:
                ci_status = "See " + pr_context_file
            if not failure_logs:
                failure_logs = "See " + pr_context_file

        # 5. Impact Analysis
        impact_output = "Not available."
        impact_script = "scripts/impact-analysis.ts"
        if not os.path.exists(impact_script):
            impact_script = "scripts/impact-analysis.ts"

        if os.path.exists(impact_script):
            # Use check=False to swallow errors from impact analysis in the planning phase
            impact_res = dev_tools.orchestrator.run_command(
                ["npx", "tsx", impact_script],
                check=False,
                log_on_error=False,
            )
            if isinstance(impact_res, subprocess.CompletedProcess):
                impact_output = (impact_res.stdout or "") + (impact_res.stderr or "")
                if impact_res.returncode != 0:
                    impact_output = f"Impact analysis failed (exit {impact_res.returncode}):\n{impact_output}"

        # 6. Existing Review Data
        gemini_review = "None."
        if os.path.exists("artifacts/gemini-code-review.md"):
            with open("artifacts/gemini-code-review.md", "r", encoding="utf-8") as f:
                gemini_review = f.read()

        github_models_review = "None."
        if os.path.exists("artifacts/github-models-code-review.md"):
            with open("artifacts/github-models-code-review.md", "r", encoding="utf-8") as f:
                github_models_review = f.read()

        return {
            "env_output": env_output,
            "issue_output": issue_output,
            "conflict_output": conflict_output,
            "pr_context_file": pr_context_file,
            "pr_summary": pr_summary,
            "ci_status": ci_status,
            "failure_logs": failure_logs,
            "impact_output": impact_output,
            "gemini_review": gemini_review,
            "github_models_review": github_models_review,
        }

    def _render_workflow_plan(self, prNumber: int, context_data: Dict[str, Any]) -> Dict[str, Any]:
        plan_dir = dev_tools.orchestrator.get_or_create_log_dir("workflows")
        plan_path = os.path.join(plan_dir, f"workflow-plan-pr-{prNumber}.md")

        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(f"""# Workflow Plan: PR #{prNumber}

## Agent Instructions

- **Environment Check**: Ensure Python dependencies and pnpm {dev_tools.orchestrator.get_config().pnpm_version} are available.
- setup complete
- validation complete
- context collected (via `td agent plan-review --pr {prNumber}`)
- diagnostics collected

**IMPORTANT: Context collection and audit are COMPLETE. Do NOT run --fetch or --audit again.**
Agent must not repeat these steps. Redundant fetching (`--fetch`) or auditing (`--audit`) is already handled.

---

## Workflow State

[x] Environment Validation
[x] Issue Validation
[x] Conflict Detection
[x] Context Collection & Audit
[x] Impact Analysis
[ ] Review Analysis
[ ] Review Authoring
[ ] Completion Verification

---

## Collected Context

### Validation Output
```text
{context_data['env_output']}
```

### Issue Validation Output
```text
{context_data['issue_output']}
```

### Conflict Output
```text
{context_data['conflict_output']}
```

### PR Summary
Relevant excerpts from:
`{context_data['pr_context_file']}`

```text
{context_data['pr_summary']}
```

### CI Status
Relevant excerpts:
```text
{context_data['ci_status']}
```

### Failure Logs
Relevant excerpts:
```text
{context_data['failure_logs']}
```

### Impact Analysis
Relevant excerpts:
```text
{context_data['impact_output']}
```

### Existing AI Reviews
**Gemini:**
```markdown
{context_data['gemini_review']}
```

**GitHub Models:**
```markdown
{context_data['github_models_review']}
```

---

## Allowed Files

Agent may read:
`.agents/workflows/REVIEW_INSTRUCTIONS.md`
`cli/logs/reviews/pr-review-{prNumber}.md`

---

## Writable Files

Agent may modify:
`cli/logs/reviews/pr-review-{prNumber}.md`

---

## Merge & Conflict Guidance

If tasks require merging branches (e.g., during PR consolidation or rebase):
- **Unrelated Histories**: If git fails with `fatal: refusing to merge unrelated histories`, use `git merge <branch> --allow-unrelated-histories`.
- **Heavy Conflicts**: If standard merging is too complex, generate a patch using `git diff base...head` and apply it manually.

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
td gh audit-pr {prNumber} --submit --execute
```

Only after successful completion.
""")
        return {"status": "success", "plan_path": plan_path}

    def generate_aggregate_prs_workflow(self) -> Dict[str, Any]:
        """Generates a deterministic aggregation workflow plan for an agent."""
        # 1. Environment Validation
        env_res = self.runtime_check()
        env_output = f"Runtime OK: node {env_res['node']}, pnpm {env_res['pnpm']}"

        # 2. Get Open PRs and Overlaps
        prs_output = "No data."
        # Re-implement minimal overlap logic without pickle
        repo = get_github_client().get_repo(dev_tools.orchestrator.get_repo_name())
        pulls = list(repo.get_pulls(state="open"))[:50]

        file_to_prs = defaultdict(list)
        pr_titles = {}
        for pr in pulls:
            num = str(pr.number)
            pr_titles[num] = pr.title
            # Standardize file fetch to avoid visual snapshots
            files = {f.filename for f in pr.get_files() if not f.filename.startswith("tests/visual.spec.ts-snapshots/")}
            for f in files:
                file_to_prs[f].append(num)

        overlap_groups = defaultdict(list)
        for file, prs in file_to_prs.items():
            if len(prs) > 1:
                overlap_groups[frozenset(prs)].append(file)

        report = ["--- EXACT OVERLAP GROUPS ---"]
        for pr_set, overlap_files in sorted(overlap_groups.items(), key=lambda x: len(x[1]), reverse=True):
            pr_list = sorted(list(pr_set), key=int)
            report.append(f"PRs {', '.join(pr_list)} overlap on {len(overlap_files)} files:")
            for pr_num in pr_list:
                report.append(f"  [{pr_num}] {pr_titles.get(pr_num)}")

        prs_output = "\n".join(report)

        # Generate workflow plan
        plan_dir = dev_tools.orchestrator.get_or_create_log_dir("workflows")
        plan_path = os.path.join(plan_dir, "workflow-plan-aggregate-prs.md")

        with open(plan_path, "w", encoding="utf-8") as f:
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
(Any relevant branch or PR metadata using `td`)

---

## Remaining Tasks

### Step 1
Review the overlap output.

### Step 2
Use `td gh` commands to merge, close, or consolidate redundant pull requests.

### Step 3
Verify all related PRs have been appropriately tagged or closed.

---

## Completion Criteria

Overlapping functionality identified and resolved.

""")
        return {"status": "success", "plan_path": plan_path}
