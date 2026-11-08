"""Merge readiness, approvals, session helpers, aggregation."""
import os
import re
import subprocess
import textwrap
from typing import Any, Dict, List, Optional
from dev_tools.models import IssueSummary, PRSummary
from dev_tools.utils import CLIError, get_github_client, log_warn, run_git_commands
from dev_tools.orchestration.ci_ops import CIOpsMixin
import dev_tools.orchestrator



class MergeGateMixin(CIOpsMixin):
    """Merge readiness, approvals, session helpers, aggregation."""

    def resolve_conflicts_headless(self, strategy: Optional[str] = None) -> List[str]:
        files = self.find_conflict_files()
        resolved, failed = [], []
        for f in files:
            if self.resolve_conflict(f, strategy=strategy):
                resolved.append(f)
            else:
                failed.append(f)
        if failed:
            raise CLIError(f"Failed to resolve: {', '.join(failed)}")
        return resolved

    def repair_context(
        self,
        log: Optional[str] = None,
        log_file: Optional[str] = None,
        prNumber: Optional[int] = None,
    ) -> List[str]:
        from dev_tools.services.repair_service import RepairService

        pipeline = RepairService()
        prompts: List[str] = []
        if log:
            p_log = pipeline.generate_prompt(log)
            if p_log:
                prompts.append(p_log)
        elif log_file:
            with open(log_file, encoding="utf-8") as f:
                for line in f:
                    p = pipeline.generate_prompt(line)
                    if p:
                        prompts.append(p)
        elif prNumber:
            repo_name = dev_tools.orchestrator.get_repo_name()
            g = get_github_client()
            repo = g.get_repo(repo_name)
            pr = repo.get_pull(prNumber)
            check_runs = self.github.fetch_check_runs(pr.head.sha)
            for run in check_runs:
                if run.get("conclusion") == "failure":
                    run_id = run.get("id")
                    if isinstance(run_id, int):
                        logs = self.github.fetch_check_run_logs(run_id, external_id=run.get("external_id"))
                        for line in logs.splitlines():
                            p = pipeline.generate_prompt(line)
                            if p:
                                prompts.append(p)
        # Filter out None values to satisfy return type list[str]
        return [p for p in prompts if p is not None]

    def suggest_next_action(self, repo: Optional[str] = None) -> Dict[str, Any]:
        """Pre-evaluate repository state and provide deterministic suggestions or fallback to LLM."""
        open_prs_res = self.list_prs(state="open", limit=100, repo=repo)
        open_prs_count = len(open_prs_res.get("prs", []))

        extra_kwargs = {"repo": repo} if repo else {}
        workflow_runs = self.github.fetch_workflow_runs(**extra_kwargs)
        failing_runs_count = sum(
            1 for run in workflow_runs
            if run.get("conclusion") in ("failure", "timed_out") or run.get("status") in ("in_progress", "queued") and run.get("conclusion") == "failure"
        )

        from dev_tools.services import local_sessions as _ls
        from dev_tools.services.local_sessions import repo_root_for
        try:
            active_sessions_count = len(
                _ls.scan_sessions(repo_root_for(None)))
        except Exception:
            active_sessions_count = 0

        if open_prs_count == 0 and failing_runs_count == 0 and active_sessions_count == 0:
            suggestion = "SUGGEST: none :: All queues clear and checks green."
            return {
                "status": "success",
                "suggestion": suggestion,
                "fast_path": True,
                "counts": {
                    "open_prs": open_prs_count,
                    "failing_runs": failing_runs_count,
                    "active_sessions": active_sessions_count,
                },
                "runnable_command": None,
            }

        # Determine runnable command based on highest-priority state
        runnable_command = "td --json preflight"
        open_prs = open_prs_res.get("prs", [])

        # 1. Check for merge conflicts
        conflicted_pr = None
        for pr in open_prs:
            merge_state = (pr.get("mergeStateStatus") or "").upper()
            if merge_state in ("DIRTY", "CONFLICTING"):
                conflicted_pr = pr.get("number")
                break
        if conflicted_pr is not None:
            runnable_command = f"td gh resolve-conflicts --pr {conflicted_pr}"
        elif failing_runs_count > 0:
            # 2. Check for failing CI runs
            target_pr = None
            if open_prs:
                target_pr = open_prs[0].get("number")
            if target_pr is not None:
                runnable_command = f"td --json repo ci-logs --pr {target_pr}"
            else:
                runnable_command = "td --json repo ci-logs"
        else:
            # 3. Check for requested changes or merge-ready PRs
            changes_requested_pr = None
            ready_pr = None
            for pr in open_prs:
                pr_num = pr.get("number")
                decision = self.github.fetch_pr_review_decision(pr_num, repo=repo)
                if decision == "CHANGES_REQUESTED":
                    changes_requested_pr = pr_num
                    break
                if decision == "APPROVED" and ready_pr is None:
                    ready_pr = pr_num

            if changes_requested_pr is not None:
                runnable_command = f"td gh read-pr-reviews --pr {changes_requested_pr}"
            elif ready_pr is not None:
                repo_flag = f" -r {repo}" if repo else ""
                runnable_command = f"td agent merge-approved{repo_flag} --execute"
            else:
                runnable_command = "td --json preflight"

        suggestion = f"SUGGEST: triage :: Action items found (Open PRs: {open_prs_count}, Failing Runs: {failing_runs_count}, Active Sessions: {active_sessions_count})."
        return {
            "status": "success",
            "suggestion": suggestion,
            "fast_path": False,
            "counts": {
                "open_prs": open_prs_count,
                "failing_runs": failing_runs_count,
                "active_sessions": active_sessions_count,
            },
            "runnable_command": runnable_command,
        }

    def evaluate_pr_merge_readiness(self, pr_num: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluates deterministic merge eligibility for a single pull request:
        - not a draft
        - reviewDecision == APPROVED
        - no check with a failing conclusion
        - mergeable == MERGEABLE
        """
        pr_details = self.github.fetch_pr_details(pr_num, repo=repo)
        title = pr_details.get("title", "")
        is_draft = bool(pr_details.get("draft"))

        review_decision = self.github.fetch_pr_review_decision(pr_num, repo=repo)

        # Check mergeable status
        raw_mergeable = pr_details.get("mergeable")
        merge_state = pr_details.get("mergeable_state")
        # In GitHub API, mergeable can be True, False, or None (if background check is computing)
        mergeable_str = "MERGEABLE" if raw_mergeable is True else ("CONFLICTING" if raw_mergeable is False else (str(merge_state).upper() if merge_state else "UNKNOWN"))

        # Check check runs on head SHA
        head_sha = pr_details.get("head", {}).get("sha")
        has_failing_checks = False
        if head_sha:
            check_runs = self.github.fetch_check_runs(head_sha, repo=repo)
            failing_conclusions = {"failure", "timed_out", "action_required", "cancelled"}
            has_failing_checks = any(run.get("conclusion") in failing_conclusions for run in check_runs)

        # Refusal reasons evaluation
        refusal_reasons = []
        if is_draft:
            refusal_reasons.append("PR is a draft")
        if review_decision != "APPROVED":
            refusal_reasons.append(f"Review decision is {review_decision or 'unapproved'}")
        if has_failing_checks:
            refusal_reasons.append("Head commit has failing check runs")
        if mergeable_str != "MERGEABLE":
            refusal_reasons.append(f"Mergeable status is {mergeable_str}")

        is_eligible = len(refusal_reasons) == 0
        reason = None if is_eligible else "; ".join(refusal_reasons)

        return {
            "pr_number": pr_num,
            "title": title,
            "draft": is_draft,
            "review_decision": review_decision,
            "has_failing_checks": has_failing_checks,
            "mergeable": mergeable_str,
            "is_eligible": is_eligible,
            "reason": reason,
        }

    def merge_approved(self, repo: Optional[str] = None, execute: bool = False) -> Dict[str, Any]:
        """
        Deterministic merge gate:
        - dry-run: list merge-ready PRs
        - --execute: re-check eligibility immediately before each merge and merge each ready PR

        --execute additionally requires the console credential
        (S5_CONSOLE_MERGE_TOKEN set): agent sessions run without the
        human console env, so a bare --execute from an agent context
        is refused. This is a speed bump, not a sandbox — prompt rules
        remain the primary bar; it stops one-command accidents, not a
        determined shell.
        """
        if execute and not os.environ.get("S5_CONSOLE_MERGE_TOKEN"):
            return {
                "status": "refused",
                "mode": "execute",
                "total_evaluated": 0,
                "eligible_count": 0,
                "merged_count": 0,
                "results": [],
                "reason": ("merge-approved --execute requires the console "
                           "credential (S5_CONSOLE_MERGE_TOKEN); refusing "
                           "agent-context execution"),
            }
        open_prs_res = self.list_prs(state="open", limit=100, repo=repo)
        open_prs = open_prs_res.get("prs", [])

        results = []
        eligible_count = 0
        merged_count: Optional[int] = 0 if execute else None

        for pr in open_prs:
            pr_num = pr.get("number")
            readiness = self.evaluate_pr_merge_readiness(pr_num, repo=repo)
            if readiness["is_eligible"]:
                eligible_count += 1

            if execute:
                if readiness["is_eligible"]:
                    # Immediate re-check before merging to guard against race conditions
                    recheck = self.evaluate_pr_merge_readiness(pr_num, repo=repo)
                    if not recheck["is_eligible"]:
                        results.append({
                            **recheck,
                            "merged": False,
                            "message": f"Refused merge on re-check: {recheck['reason']}",
                        })
                        continue

                    try:
                        target_repo_name = repo or self.github.repo
                        merge_res = self.github.merge_pull_request(
                            pr_num,
                            commit_title=f"Merge pull request #{pr_num} from {target_repo_name}",
                            repo=repo,
                        )
                        if merged_count is not None:
                            merged_count += 1
                        results.append({
                            **recheck,
                            "merged": True,
                            "message": merge_res.get("message", "Merged successfully"),
                        })
                    except Exception as e:
                        results.append({
                            **recheck,
                            "merged": False,
                            "message": f"Merge failed: {str(e)}",
                        })
                else:
                    results.append({
                        **readiness,
                        "merged": False,
                        "message": f"Refused: {readiness['reason']}",
                    })
            else:
                # Dry run preview
                results.append(readiness)

        return {
            "status": "success",
            "mode": "execute" if execute else "dry-run",
            "total_evaluated": len(results),
            "eligible_count": eligible_count,
            "merged_count": merged_count,
            "results": results,
        }

    def list_prs(
        self,
        state: str = "open",
        limit: int = 100,
        includeDrafts: bool = True,
        labels: Optional[List[str]] = None,
        repo: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Lists PRs with optional filtering."""
        if "include_drafts" in kwargs:
            includeDrafts = kwargs["include_drafts"]
        if "labels" in kwargs and labels is None:
            labels = kwargs["labels"]
        extra_kwargs = {"repo": repo} if repo else {}
        prs = self.github.list_pull_requests(state=state, limit=limit, labels=labels, **extra_kwargs)

        if not includeDrafts:
            prs = [pr for pr in prs if not pr.get("isDraft")]

        return {"status": "success", "prs": [PRSummary(**pr).model_dump() for pr in prs]}

    def list_issues(
        self,
        state: str = "open",
        limit: int = 100,
        labels: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Lists issues with optional filtering."""
        if "labels" in kwargs and labels is None:
            labels = kwargs["labels"]
        issues = self.github.list_issues(state=state, limit=limit, labels=labels)

        return {"status": "success", "issues": [IssueSummary(**issue).model_dump() for issue in issues]}

    def get_pr_comments(self, prNumber: int, **kwargs) -> Dict[str, Any]:
        """Fetches and aggregates standard issue comments and inline review comments for a PR."""
        if "prNumber" in kwargs:
            prNumber = kwargs["prNumber"]
        pr = self.github.fetch_pr_details(prNumber)
        issue_comments = self.github.fetch_issue_comments(prNumber)
        review_comments = self.github.fetch_review_comments(prNumber)

        return {
            "pr": {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "html_url": pr.get("html_url"),
            },
            "comments": [
                {
                    "user": c.get("user", {}).get("login"),
                    "body": c.get("body"),
                    "created_at": c.get("created_at"),
                }
                for c in issue_comments
            ],
            "review_comments": [
                {
                    "user": c.get("user", {}).get("login"),
                    "path": c.get("path"),
                    "line": c.get("line"),
                    "body": c.get("body"),
                    "created_at": c.get("created_at"),
                }
                for c in review_comments
            ],
        }

    def get_repo_for_session(self, session: Dict[str, Any]) -> Optional[str]:
        """Extracts the repository name (owner/repo) associated with a session."""
        if session.get("outputs") and isinstance(session["outputs"], list):
            for output in session["outputs"]:
                if output.get("pullRequest") and output["pullRequest"].get("url"):
                    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/\d+", output["pullRequest"]["url"])
                    if match:
                        return match.group(1)

        src = session.get("sourceContext", {}).get("source", "")
        if src.startswith("sources/github/"):
            return src.replace("sources/github/", "")

        return None

    def get_pr_for_session(self, session: Dict[str, Any]) -> Optional[int]:
        """Optimized PR lookup for a session."""
        session_id = session.get("name", "").replace("sessions/", "")

        # 1. Try metadata/outputs first if available (fastest)
        if session.get("outputs") and isinstance(session["outputs"], list):
            for output in session["outputs"]:
                if output.get("pullRequest") and output["pullRequest"].get("url"):
                    match = re.search(r"/pull/(\d+)", output["pullRequest"]["url"])
                    if match:
                        return int(match.group(1))

        # 2. Try branch name from sourceContext (fast - targeted search)
        branch = None
        if session.get("sourceContext"):
            branch = session["sourceContext"].get("githubRepoContext", {}).get("startingBranch")

        if branch:
            # Use search API for targeted branch lookup
            prs = self.github.search_pull_requests(f"head:{branch} state:open", limit=1)
            if prs:
                return prs[0]["number"]

        # 3. Fallback to session ID in body
        safe_id = f'"{session_id}"'
        prs = self.github.search_pull_requests(f"{safe_id} in:body,title state:open", limit=1)
        if prs:
            return prs[0]["number"]

        return None

    def aggregate_prs(self, target_branch: str, prNumbers: List[int]) -> Dict[str, Any]:
        """
        Aggregates multiple PRs into a single target branch and creates a consolidated PR.
        """
        base_branch = dev_tools.orchestrator.get_config().base_branch_name

        # 1. Isolation & Cleanliness
        run_git_commands(
            [
                ["git", "checkout", base_branch],
                ["git", "pull", "origin", base_branch],
                ["git", "checkout", "-b", target_branch],
            ]
        )

        aggregate_body = ""
        successfully_merged = []

        from dev_tools.utils.concurrency import run_concurrently
        pr_details_map = {}
        if prNumbers:
            def fetch_pr_details_with_error(pr_num):
                try:
                    return pr_num, self.github.fetch_pr_details(pr_num)
                except Exception as e:
                    raise CLIError(f"Failed to fetch PR #{pr_num}: {e}")

            results = run_concurrently(fetch_pr_details_with_error, prNumbers, max_workers=4, ignore_exceptions=False)
            for pr_num, pr_detail in results:
                pr_details_map[pr_num] = pr_detail

        for pr_num in prNumbers:
            # 2. Sequential Extraction & Deterministic Sequence
            pr_data = pr_details_map.get(pr_num) or {}
            head_ref = pr_data.get("head", {}).get("ref")
            title = pr_data.get("title")
            body = pr_data.get("body") or ""

            if not head_ref:
                raise CLIError(f"Could not determine head ref for PR #{pr_num}")

            # 2.5 Handle forks by using git fetch
            # This ensures the branch is available locally and handles forks correctly
            # and switch back to target branch.
            run_git_commands(
                [
                    ["git", "fetch", "origin", f"+pull/{pr_num}/head:{head_ref}"],
                    ["git", "checkout", target_branch],
                ]
            )

            # 3. Safety First: Attempt automated integration merge
            # Use 'ort' strategy implicitly by standard merge if git version supports it,
            # or just standard merge.
            merge_cmd = ["git", "merge", head_ref, "-m", f"Merging PR #{pr_num}: {title}"]
            res = dev_tools.orchestrator.run_command(merge_cmd, check=False)

            if not isinstance(res, subprocess.CompletedProcess):
                raise CLIError("Merge execution failed")

            if res.returncode != 0:
                # Detect "refusing to merge unrelated histories" and retry
                # Safely handle potential None values if capture failed
                merge_output = (res.stdout or "") + (res.stderr or "")
                if "unrelated histories" in merge_output.lower():
                    log_warn(f"Disjoint history detected for PR #{pr_num}. Retrying with --allow-unrelated-histories")
                    res = dev_tools.orchestrator.run_command(merge_cmd + ["--allow-unrelated-histories"], check=False)
                    if not isinstance(res, subprocess.CompletedProcess):
                        raise CLIError("Retry merge with --allow-unrelated-histories failed execution")

                if res.returncode != 0:
                    # Conflict encountered
                    dev_tools.orchestrator.run_command(["git", "merge", "--abort"])
                    error_msg = textwrap.dedent(f"""
                        CRITICAL: Conflict in PR #{pr_num}. Restored stable state of {target_branch}.

                        Fallback Strategy:
                        If native merging fails due to heavy conflicts or history divergence:
                        1. Generate a patch: `git diff {target_branch}...{head_ref} > pr_{pr_num}.patch`
                        2. Apply manually: `git apply pr_{pr_num}.patch` and resolve rejects.
                        3. Or retry merge with: `git merge {head_ref} --allow-unrelated-histories`
                    """).strip()
                    raise CLIError(error_msg, code=res.returncode)

            # 4. Metadata Preservation
            successfully_merged.append(pr_num)
            aggregate_body += f"Closes #{pr_num}\n\n### Description from PR #{pr_num} ({title}):\n{body}\n\n---\n"

        # Push the compiled branch
        dev_tools.orchestrator.run_command(["git", "push", "-u", "origin", target_branch])

        # Create consolidated PR
        pr_title = f"Aggregated Feature: {target_branch}"
        pr_res = self.github.create_pull_request(pr_title, aggregate_body, target_branch, base_branch)
        pr_url = pr_res.get("html_url")

        return {
            "status": "success",
            "branch": target_branch,
            "merged_prs": successfully_merged,
            "pr_url": pr_url,
            "message": f"Successfully aggregated {len(successfully_merged)} PRs into {target_branch}",
        }
