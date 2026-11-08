"""CI logs, merge conflicts, and shaped PR views."""
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dev_tools.models import PrDiffResponse, PrViewResponse, RunJobsResponse
from dev_tools.utils import log_info, CLIError, log_error, log_warn
from dev_tools.orchestration.runtime import RuntimeMixin
import dev_tools.orchestrator



class CIOpsMixin(RuntimeMixin):
    """CI logs, merge conflicts, and shaped PR views."""

    def plan_workflow_audit(self, workflow: Optional[str] = None) -> Dict[str, Any]:
        """
        Builds a deterministic roadmap and status checklist for auditing GitHub workflows.
        """
        if workflow:
            # 1. Path Sanitization & Validation
            # Restrict to .github/workflows directory and ensure valid extensions
            workflow_path = os.path.normpath(workflow)
            if not (workflow_path.endswith(".yml") or workflow_path.endswith(".yaml")):
                raise CLIError(f"Invalid workflow file extension: {workflow}. Must be .yml or .yaml")

            if not workflow_path.startswith(".github/workflows" + os.sep) and workflow_path != os.path.join(
                ".github", "workflows", os.path.basename(workflow_path)
            ):
                # Allow relative paths that point into the directory
                if not os.path.dirname(workflow_path) == os.path.join(".github", "workflows"):
                    raise CLIError(f"Workflow file must reside in .github/workflows/: {workflow}")

            if not os.path.exists(workflow_path):
                raise CLIError(f"Workflow file not found: {workflow_path}")
            files = [workflow_path]
        else:
            files = self._scan_workflows()

        if not files:
            return {
                "status": "success",
                "message": "No workflows found to audit.",
                "files_count": 0,
                "status_file": ".boomtick/workflow-audit-status.md",
            }

        # 1. Cache compliance checks to avoid redundant processing
        file_audit_results = {}
        for f_path in files:
            file_audit_results[f_path] = self._check_workflow_compliance(f_path)

        # 2. Summary Checklist Generation (.boomtick/workflow-audit-status.md)
        status_path = os.path.join(".boomtick", "workflow-audit-status.md")
        os.makedirs(".boomtick", exist_ok=True)
        status_lines = [
            "# Workflow Audit Status",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "\n## Compliance Checklist\n",
        ]

        for f_path in files:
            name = os.path.basename(f_path)
            violations = file_audit_results[f_path]
            status = "✅" if not violations else "❌"
            status_lines.append(f"- [ ] {status} `{name}`: {len(violations)} violation(s)")

        with open(status_path, "w", encoding="utf-8") as f:
            f.write("\n".join(status_lines) + "\n")

        # 3. Individual Workflow Plan Generation
        plan_dir = dev_tools.orchestrator.get_or_create_log_dir("workflows")
        generated_plans = []

        for f_path in files:
            name = os.path.basename(f_path)
            plan_path = os.path.join(plan_dir, f"workflow-plan-{name}.md")
            violations = file_audit_results[f_path]
            violations_text = "" if not violations else "\n".join(f"- {v}" for v in violations)

            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(f"""# Workflow Audit Plan: {name}

## File Path
`{f_path}`

## Compliance Status
{"✅ All rules followed." if not violations else "❌ Non-compliant patterns found."}

### Violations
{violations_text}

## Audit Instructions

Review `.github/workflows/` files to align them with `AGENTS.md` runtime policies and version pinning rules.

### Step 1: Manual Review
Verify if the regex patterns missed any semantic violations (e.g., complex shell scripts using forbidden tools).

### Step 2: Version Alignment
Ensure all GitHub Actions are pinned to their latest major versions (e.g. `actions/checkout@v4`).

### Step 3: Runtime Policy Alignment
Confirm `actions/setup-node` uses `node-version-file: '.node-version'`.

### Step 4: Verification
Run the workflow (if possible via `gh workflow run` or by pushing a test branch) to ensure the changes don't break the CI/CD pipeline.

---

## Remediation Suggestions
- Replace `node-version: 24` (or other version) with `node-version-file: '.node-version'`.
- Replace `npm install` with `pnpm install`.
- Update `@v2` or `@v3` tags to `@v4` (checkout) or `@v4` (setup-node).
""")
            generated_plans.append(plan_path)

        return {
            "status": "success",
            "files_count": len(files),
            "status_file": status_path,
            "workflow_plans": generated_plans,
        }

    def plan_issue_audit(
        self,
        issueNumbers: Optional[List[int]] = None,
        all_open: bool = False,
        limit: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Builds a deterministic roadmap and status checklist for auditing open issues.
        """
        issues = []
        if "issue_numbers" in kwargs and issueNumbers is None:
            issueNumbers = kwargs["issue_numbers"]
        if "limit" in kwargs:
            limit = kwargs["limit"]
        if all_open:
            issues = self.github.list_issues(state="open", limit=limit)
        elif issueNumbers:
            for num in issueNumbers:
                issue = self.github.fetch_issue_details(num)
                # Normalize format to match list_issues
                issues.append(self.github.normalize_issue(issue))
        else:
            raise CLIError("Provide --issue or --all-open")

        # 1. Summary Checklist Generation (.boomtick/issue-audit-status.md)
        status_path = os.path.join(".boomtick", "issue-audit-status.md")
        os.makedirs(".boomtick", exist_ok=True)
        status_lines = [
            "# Issue Audit Status",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "\n## Open Issues Checklist\n",
        ]
        for issue in issues:
            status_lines.append(f"- [ ] #{issue['number']}: {issue['title']}")

        with open(status_path, "w", encoding="utf-8") as f:
            f.write("\n".join(status_lines) + "\n")

        # 2. Individual Workflow Plan Generation
        plan_dir = dev_tools.orchestrator.get_or_create_log_dir("workflows")
        generated_plans = []

        for issue in issues:
            plan_path = os.path.join(plan_dir, f"workflow-plan-issue-{issue['number']}.md")

            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(f"""# Workflow Plan: Issue #{issue['number']}

## Agent Instructions
- **Environment Check**: Ensure Python dependencies and pnpm {dev_tools.orchestrator.get_config().pnpm_version} are available.

## Issue Context
- **Title:** {issue['title']}
- **URL:** {issue['html_url']}
- **Labels:** {', '.join(issue['labels']) if issue['labels'] else '_None_'}

## Audit Instructions

Before auditing, read `docs/agent/issue-audit-rules.md`.

### Step 1: Understand Intent
Analyze the problem statement and goal in the issue description.

### Step 2: Codebase Inspection
Locate relevant files, components, or routes described in the issue.

### Step 3: Verification
Verify if the requested change is already implemented, partially addressed, or missing.

### Step 4: Documentation & Closure Recommendation
Follow the "Audit comment template" in `docs/agent/issue-audit-rules.md` to post your findings.

---

## Issue Body Excerpt
```markdown
{issue['body'] or '_No description provided._'}
```
""")
            generated_plans.append(plan_path)

        return {
            "status": "success",
            "issues_count": len(issues),
            "status_file": status_path,
            "workflow_plans": generated_plans,
        }

    def run_playwright(self, grep: Optional[str] = None, worktree_path: Optional[str] = None) -> Dict[str, Any]:
        """Runs Playwright tests and parses the JSON report."""
        playwright_args = ["playwright", "test", "--reporter=json"]
        if grep:
            playwright_args.extend(["--grep", grep])

        res = dev_tools.orchestrator.run_command(["pnpm"] + playwright_args, cwd=worktree_path, check=False)

        failed_tests = []
        try:
            if "{" in res.stdout:
                json_data = res.stdout[res.stdout.find("{") :]
                try:
                    report = json.loads(json_data)
                    for suite in report.get("suites", []):
                        for spec in suite.get("specs", []):
                            if not spec.get("ok"):
                                error = "Unknown error"
                                if (
                                    spec.get("tests")
                                    and spec["tests"][0].get("results")
                                    and spec["tests"][0]["results"][0].get("error")
                                ):
                                    error = spec["tests"][0]["results"][0]["error"].get("message", "Unknown error")

                                failed_tests.append(
                                    {
                                        "title": spec.get("title"),
                                        "file": spec.get("file"),
                                        "error": error,
                                    }
                                )
                except json.JSONDecodeError as e:
                    log_error(f"Failed to parse Playwright JSON report: {e}\nRaw output: {res.stdout}")
        except Exception as e:
            log_error(f"Unexpected error parsing Playwright output: {e}")

        return {
            "success": res.returncode == 0,
            "command": " ".join(["pnpm"] + playwright_args),
            "failedTests": failed_tests,
        }

    def sync_pr(self, prNumber: int) -> Dict[str, Any]:
        """Reliably pull the latest remote PR state to local, overwriting messy rebases."""
        pr_data = self.github.fetch_pr_details(prNumber)
        head_ref = pr_data.get("head", {}).get("ref")

        if not head_ref:
            raise CLIError(f"Could not determine head ref for PR #{prNumber}")

        log_info(f"Fetching remote state for PR #{prNumber} ({head_ref})...")
        # Use pull ref to be robust against forks and ensure we get the exact commit
        dev_tools.orchestrator.run_command(["git", "fetch", "origin", f"pull/{prNumber}/head"])

        current_branch = dev_tools.orchestrator.run_command(["git", "branch", "--show-current"]).strip()
        if current_branch != head_ref:
            log_info(f"Switching from {current_branch} to {head_ref}")
            dev_tools.orchestrator.run_command(["git", "checkout", "-B", head_ref, "FETCH_HEAD"])
        else:
            log_info(f"Hard resetting {head_ref} to remote state...")
            dev_tools.orchestrator.run_command(["git", "reset", "--hard", "FETCH_HEAD"])

        return {
            "status": "success",
            "message": f"Successfully synced local branch `{head_ref}` with remote state of PR #{prNumber}.",
            "branch": head_ref,
        }

    def get_ci_logs(self,
        prNumber: int,
        include_all: bool = False,
        repo: Optional[str] = None,
        **kwargs) -> Dict[str,
        Any]:
        if "pr_number" in kwargs:
            prNumber = kwargs["pr_number"]
        if "repo" in kwargs and repo is None:
            repo = kwargs["repo"]
        """Fetches CI logs for failing (or all) check runs in a PR."""
        # Get PR head SHA
        pr_data = self.github.fetch_pr_details(prNumber, repo=repo)
        head_sha = pr_data.get("head", {}).get("sha")

        if not head_sha:
            raise CLIError(f"Could not determine head SHA for PR #{prNumber}")

        # Get check runs
        checks = self.github.fetch_check_runs(head_sha, repo=repo)
        failed_checks = [c for c in checks if c.get("conclusion") == "failure"]

        logs: dict[str, str] = {}
        # Get check suites to find workflow runs
        check_suites = self.github.fetch_check_suites(head_sha, repo=repo)

        all_runs = []
        from dev_tools.utils.concurrency import run_concurrently
        if check_suites:
            def fetch_suite_runs(suite):
                try:
                    return self.github.fetch_check_runs_for_suite(suite["id"], repo=repo)
                except Exception as e:
                    log_warn(f"Failed to fetch runs for suite {suite.get('id')}: {e}")
                    return []

            results = run_concurrently(fetch_suite_runs, check_suites, max_workers=4, ignore_exceptions=True)
            for runs in results:
                all_runs.extend(runs)

        runs_to_fetch = [run for run in all_runs if include_all or run.get("conclusion") == "failure"]

        def fetch_log(run):
            try:
                run_id = run.get("id")
                if isinstance(run_id, int):
                    return run["name"], self.github.fetch_check_run_logs(run_id,
                        external_id=run.get("external_id"),
                        repo=repo)
            except Exception as e:
                log_warn(f"Failed to fetch log for run {run.get('id')}: {e}")
            return None, None

        if runs_to_fetch:
            log_results = run_concurrently(fetch_log, runs_to_fetch, max_workers=4, ignore_exceptions=True)
            for name, log_content in log_results:
                if name and isinstance(name, str) and log_content and isinstance(log_content, str):
                    logs[name] = log_content[:10000]

        return {"checks": checks, "failedChecks": failed_checks, "logs": logs}

    def stream_ci_logs(self, prNumber: int, grep: Optional[str] = None, repo: Optional[str] = None) -> str:
        """Fetches and combines all CI logs for the latest workflow run of a PR."""
        # Get PR head SHA
        pr_data = self.github.fetch_pr_details(prNumber, repo=repo)
        head_sha = pr_data.get("head", {}).get("sha")

        if not head_sha:
            raise CLIError(f"Could not determine head SHA for PR #{prNumber}")

        # Get all check runs for this SHA
        check_runs = self.github.fetch_check_runs(head_sha, repo=repo)

        all_logs = []
        # Limit to latest 20 jobs to avoid extreme memory usage
        for run in check_runs[:20]:
            # Fetch logs via API to avoid terminal paging/buffering issues
            run_id = run.get("id")
            if not isinstance(run_id, int):
                continue
            log_content = self.github.fetch_check_run_logs(run_id, external_id=run.get("external_id"), repo=repo)
            header = f"--- LOGS FOR JOB: {run['name']} (ID: {run_id}) ---"
            all_logs.append(header)
            # Truncate each log to 20k chars to balance detail vs memory
            all_logs.append(log_content[-20000:])
            all_logs.append("\n")

        combined_logs = "\n".join(all_logs)

        if grep:
            grep_pattern = grep.lower()
            lines = combined_logs.splitlines()
            filtered_lines = [line for line in lines if grep_pattern in line.lower()]
            return "\n".join(filtered_lines)

        return combined_logs

    def get_merge_conflicts(self, prNumber: int, base_branch: Optional[str] = None) -> Dict[str, Any]:
        """Detects merge conflicts for a PR against a base branch using a temporary worktree."""
        if base_branch is None:
            base_branch = dev_tools.orchestrator.get_config().base_branch_name
        # Get PR head ref
        pr_data = self.github.fetch_pr_details(prNumber)
        head_ref = pr_data.get("head", {}).get("ref")

        if not head_ref:
            raise CLIError(f"Could not determine head ref for PR #{prNumber}")

        # Ensure we have the latest
        dev_tools.orchestrator.run_command(["git", "fetch", "origin", head_ref])
        dev_tools.orchestrator.run_command(["git", "fetch", "origin", base_branch])

        worktree_path = os.path.join(os.getcwd(), f"worktree-conflict-{prNumber}.tmp")
        self._cleanup_worktree(worktree_path)

        dev_tools.orchestrator.run_command(["git", "worktree", "add", worktree_path, f"origin/{head_ref}"])

        conflict_files = []
        command_log = ""
        try:
            merge_cmd = ["git", "merge", "--no-commit", "--no-ff", f"origin/{base_branch}"]
            res = dev_tools.orchestrator.run_command(merge_cmd, cwd=worktree_path, check=False)
            command_log = (res.stdout or "") + (res.stderr or "")

            if res.returncode != 0:
                # Detect and retry unrelated histories
                if "unrelated histories" in command_log.lower():
                    log_warn(
                        (
                            f"Disjoint "
                            f"history detected "
                            f"for conflict "
                            f"check of "
                            f"PR #{prNumber}. "
                            f"Retrying with "
                            f"--allow-unrelated-histories"
                        )
                    )
                    res = dev_tools.orchestrator.run_command(merge_cmd + ["--allow-unrelated-histories"],
                        cwd=worktree_path,
                        check=False)
                    command_log += "\n--- RETRY WITH --allow-unrelated-histories ---\n"
                    command_log += (res.stdout or "") + (res.stderr or "")

            if res.returncode != 0:
                res_diff = dev_tools.orchestrator.run_command(
                    ["git", "diff", "--name-only", "--diff-filter=U"],
                    cwd=worktree_path,
                    check=False,
                )
                conflict_files = [f.strip() for f in res_diff.stdout.splitlines() if f.strip()]
                dev_tools.orchestrator.run_command(["git", "merge", "--abort"], cwd=worktree_path, check=False)
        finally:
            dev_tools.orchestrator.run_command(["git", "worktree", "remove", "-f", worktree_path], check=False)
            if os.path.exists(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)

        return {
            "prNumber": prNumber,
            "baseBranch": base_branch,
            "headRef": head_ref,
            "conflictFiles": conflict_files,
            "commandLog": command_log,
        }

    def get_pr_diff_shapen(self, prNumber: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches PR diff, applies truncation and shapes file info."""
        extra_kwargs = {"repo": repo} if repo else {}
        # Get files list
        files = self.github.fetch_pr_files(prNumber, **extra_kwargs)

        # Get diff text
        diff_text = self.github.fetch_pr_diff(prNumber, **extra_kwargs)

        MAX_DIFF_SIZE = 50000
        truncated = False
        if len(diff_text) > MAX_DIFF_SIZE:
            diff_text = diff_text[:MAX_DIFF_SIZE] + "\n\n... [Diff truncated due to size] ..."
            truncated = True

        resp = PrDiffResponse(
            pr_number=prNumber,
            files=[
                {
                    "path": f.get("filename"),
                    "status": f.get("status") or "modified",
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                }
                for f in files
            ],
            diff_text=diff_text,
            is_truncated=truncated,
        )
        return resp.model_dump()

    def get_pr_view_shapen(self, prNumber: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches a single PR state snapshot: title, state, draft, reviewDecision, mergeable, checks."""
        extra_kwargs = {"repo": repo} if repo else {}
        pr = self.github.fetch_pr_details(prNumber, **extra_kwargs)
        review_decision = self.github.fetch_pr_review_decision(prNumber, **extra_kwargs)
        head_sha = (pr.get("head") or {}).get("sha")
        check_runs = self.github.fetch_check_runs(head_sha, **extra_kwargs) if head_sha else []
        checks = [
            {"name": c.get("name"), "status": c.get("status"), "conclusion": c.get("conclusion")}
            for c in (check_runs or [])
        ]
        summary = {"total": len(checks), "passed": 0, "failed": 0, "pending": 0, "skipped": 0}
        for check in checks:
            conclusion = (check.get("conclusion") or "").lower()
            status = (check.get("status") or "").lower()
            if status != "completed" or not conclusion:
                summary["pending"] += 1
            elif conclusion == "success":
                summary["passed"] += 1
            elif conclusion in ("skipped", "neutral"):
                summary["skipped"] += 1
            else:
                summary["failed"] += 1
        mergeable_raw = pr.get("mergeable")
        if mergeable_raw is True:
            mergeable = "MERGEABLE"
        elif mergeable_raw is False:
            mergeable = "CONFLICTING"
        else:
            mergeable = "UNKNOWN"
        resp = PrViewResponse.model_validate(
            {
                "pr_number": prNumber,
                "title": pr.get("title"),
                "state": (pr.get("state") or "").upper() or None,
                "draft": bool(pr.get("draft", False)),
                "review_decision": review_decision,
                "mergeable": mergeable,
                "checks": checks,
                "checks_summary": summary,
            }
        )
        return resp.model_dump()

    def get_run_jobs_shapen(self, run_id: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches workflow run jobs shaped to name/conclusion/steps."""
        extra_kwargs = {"repo": repo} if repo else {}
        jobs = self.github.fetch_workflow_run_jobs(run_id, **extra_kwargs) or []
        resp = RunJobsResponse.model_validate({"run_id": run_id, "total_count": len(jobs), "jobs": jobs})
        return resp.model_dump()
