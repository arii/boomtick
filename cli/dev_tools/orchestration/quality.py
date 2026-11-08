"""Ratchets, audits, and review tracking."""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dev_tools.ux_report import generate_report
from dev_tools.handlers.command_handler import CommandHandler
from dev_tools.utils import (
    log_info,
    CLIError,
    clean_gha_logs,
    extract_failing_info,
    find_patterns_in_file,
    get_any_count,
    get_bundle_size,
    get_github_client,
    log_warn,
    resolve_resource_path,
    set_gha_variable,
    verify_pr_scope,
    walk_tsx)
from dev_tools.orchestration.issues import IssueMixin
import dev_tools.orchestrator



class QualityMixin(IssueMixin):
    """Ratchets, audits, and review tracking."""

    def ratchet_any(
        self, update: bool = False, baseline_file: Optional[str] = None, dry_run: bool = True
    ) -> Dict[str, Any]:
        """Enforce a numeric ratchet gate."""
        current = get_any_count()
        baseline = self.resolve_baseline(baseline_file, "ANY_COUNT_BASELINE", 0)
        res = {
            "current": current,
            "baseline": baseline,
            "status": "success" if current <= baseline else "error",
        }
        if current > baseline:
            res["message"] = f"'any' count increased from {baseline} to {current}."
        if update:
            if not dry_run:
                if baseline_file:
                    with open(baseline_file, "w", encoding="utf-8") as f:
                        f.write(str(current))
                else:
                    set_gha_variable("ANY_COUNT_BASELINE", str(current))
            res["updated"] = not dry_run
        return res

    def check_bundle_size(
        self,
        update: bool = False,
        baseline_file: Optional[str] = None,
        threshold: int = 50,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Check the bundle size against its budget."""
        size = get_bundle_size()
        baseline = self.resolve_baseline(baseline_file, "BUNDLE_BASELINE_KB", 3080)
        threshold_kb = baseline + threshold
        res = {
            "size_kb": size,
            "baseline_kb": baseline,
            "threshold_kb": threshold_kb,
            "status": "success" if size <= threshold_kb else "error",
        }
        if size > threshold_kb:
            res["message"] = f"Bundle size exceeds threshold ({size}KB > {threshold_kb}KB)."
        if update:
            if not dry_run:
                if baseline_file:
                    with open(baseline_file, "w", encoding="utf-8") as f:
                        f.write(str(size))
                else:
                    set_gha_variable("BUNDLE_BASELINE_KB", str(size))
            res["updated"] = not dry_run
        return res

    def migrate_tokens(
        self,
        find: Optional[str] = None,
        migrate: Optional[Tuple[str, str]] = None,
        dry_run: bool = True,
    ) -> List[Dict[str, Any]]:
        """Migrate stored tokens to the current scheme."""
        root_dir = "src"
        matches = []
        if find:
            for filepath in walk_tsx(root_dir):
                findings = find_patterns_in_file(filepath, [(re.escape(find), "Found")])
                for ln, _, content in findings:
                    matches.append({"file": filepath, "line": ln, "content": content.strip()})
        elif migrate:
            old, new = migrate
            for filepath in walk_tsx(root_dir):
                with open(filepath, "r", encoding="utf-8") as f:
                    c = f.read()
                if old in c:
                    matches.append({"file": filepath})
                    if not dry_run:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(c.replace(old, new))
        return matches

    def audit_pr(
        self,
        prNumber: int,
        fetch: bool = False,
        audit: bool = False,
        submit: bool = False,
        cleanup: bool = False,
        dry_run: bool = True,
        event: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Run the audit pipeline for a pull request."""
        if "pr_number" in kwargs:
            prNumber = kwargs["pr_number"]
        review_dir = dev_tools.orchestrator.get_or_create_log_dir("reviews")
        ctx_path = os.path.join(review_dir, f"pr-context-{prNumber}.md")
        rev_path = os.path.join(review_dir, f"pr-review-{prNumber}.md")
        res: Dict[str, Any] = {"pr": prNumber, "files": {}}
        if fetch:
            self._fetch_pr_context_files(prNumber, ctx_path, rev_path)
            res["files"]["context"] = ctx_path
            res["files"]["review"] = rev_path
        if audit:
            res["auto_findings"] = self._run_antipattern_audit(ctx_path)
        if submit:
            self.github.submit_pr_review(prNumber, rev_path, cleanup=cleanup, dry_run=dry_run, event_override=event)
        return res

    def _fetch_pr_context_files(self, prNumber: int, ctx_path: str, rev_path: str) -> None:
        repo = get_github_client().get_repo(dev_tools.orchestrator.get_repo_name())
        pr = repo.get_pull(prNumber)
        title = pr.title
        author = pr.user.login
        desc = pr.body or "_No description provided._"
        context_lines = [
            f"# PR Context: #{pr.number} — {title}",
            f"**Author:** @{author}\n",
            f"## Description\n{desc}\n",
            "## CI Status",
        ]

        check_runs = self.github.fetch_check_runs(pr.head.sha)
        failed_check_names = []
        detected_errors = []

        # Pre-fetch logs for failed runs in parallel to minimize sequential GHA latency
        failed_runs = [run for run in check_runs if run.get("conclusion") == "failure"]
        fetched_logs = {}
        if failed_runs:
            from dev_tools.utils.concurrency import run_concurrently
            log_info(f"⚡ Pre-fetching logs for {len(failed_runs)} failed check runs in parallel...")
            def fetch_logs_for_run(run_item):
                r_id = run_item.get("id")
                if isinstance(r_id, int):
                    try:
                        return r_id, self.github.fetch_check_run_logs(r_id, external_id=run_item.get("external_id"))
                    except Exception as e:
                        log_warn(f"Failed to fetch logs for run {r_id}: {e}")
                return r_id, ""

            results = run_concurrently(fetch_logs_for_run, failed_runs, max_workers=4, ignore_exceptions=True)
            for r_id, r_logs in results:
                if r_id is not None:
                    fetched_logs[r_id] = r_logs

        if check_runs:
            for run in check_runs:
                status_icon = (
                    "✅"
                    if run.get("conclusion") == "success"
                    else "❌" if run.get("conclusion") == "failure" else "⏳"
                )
                context_lines.append(
                    (
                        f"- "
                        f"{status_icon} **{run.get('name')}**: "
                        f"{run.get('status')} ({run.get('conclusion') or 'in_progress'})"
                    )
                )
                if run.get("conclusion") == "failure":
                    failed_check_names.append(run.get("name"))
                    run_id = run.get("id")
                    findings: List[Dict[str, Any]] = []
                    if isinstance(run_id, int):
                        # Retrieve pre-fetched logs with a fallback
                        logs = fetched_logs.get(run_id, "")
                        if not logs:
                            logs = self.github.fetch_check_run_logs(run_id, external_id=run.get("external_id"))

                        # Structured failure analysis
                        findings = extract_failing_info(logs)
                    if findings:
                        context_lines.append("  **Failing Tests/Build Errors:**")
                        for f in findings:
                            error_msg = f"🔴 `{f['file']}:{f['line']}`: {f['message']} ({f['type']})"
                            context_lines.append(f"  - {error_msg}")
                            detected_errors.append(error_msg)

                    # Extract a snippet of the logs (last 50 lines or search for 'error')
                    cleaned_logs = clean_gha_logs(logs)
                    log_lines = cleaned_logs.splitlines()
                    error_lines = [
                        l
                        for l in log_lines
                        if any(x in l.lower() for x in ["error", "fail", "ts", "vitest", "playwright", "🔴"])
                    ]
                    snippet = "\n".join(error_lines[-20:] if error_lines else log_lines[-30:])
                    context_lines.append(
                        f"  <details><summary>Failure Logs Snippet</summary>\n\n  ```\n  {snippet}\n  ```\n  </details>"
                    )
        else:
            context_lines.append("_No check runs found._")

        context_lines.extend(["\n## Files Changed"])
        pr_files = list(pr.get_files())
        for f in pr_files:
            context_lines.append(
                f"- {'🟢' if f.status == 'added' else '🔴' if f.status == 'removed' else '🟡'} `{f.filename}`"
            )
        context_lines.append("\n## Diffs")
        for f in pr_files:
            context_lines.append(f"\n### `{f.filename}` ({f.status})")
            patch = f.patch or "_No textual diff available._"
            annotated = []
            line_num = 0
            if patch != "_No textual diff available._":
                for line in patch.splitlines():
                    if line.startswith("@@"):
                        m = re.search(r"\+(\d+)", line)
                        line_num = int(m.group(1)) if m else line_num
                        annotated.append(line)
                    elif line.startswith("+"):
                        annotated.append(f"{line_num:4d} |{line}")
                        line_num += 1
                    elif line.startswith("-"):
                        annotated.append(f"     |{line}")
                    else:
                        annotated.append(f"{line_num:4d} |{line}")
                        line_num += 1
            context_lines.append("```diff\n" + "\n".join(annotated) + "\n```")
        with open(ctx_path, "w", encoding="utf-8") as context_file:
            context_file.write("\n".join(context_lines))

        failed_checks_str = (
            "\n".join(f"- {name}" for name in failed_check_names) if failed_check_names else "_None_"
        )
        errors_str = (
            "\n".join(f"- {err}" for err in detected_errors) if detected_errors else "_None detected by parser._"
        )

        template_path = resolve_resource_path("review_template.md")
        with open(template_path, "r", encoding="utf-8") as template_file:
            template = template_file.read().format(
                pr_num=prNumber,
                head_sha=pr.head.sha,
                failed_checks=failed_checks_str,
                detected_errors=errors_str,
            )

        with open(rev_path, "w", encoding="utf-8") as review_file:
            review_file.write(template)

    def _run_antipattern_audit(self, ctx_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(ctx_path):
            raise CLIError(f"Context file missing: {ctx_path}")
        with open(ctx_path, "r", encoding="utf-8") as context_file:
            context = context_file.read()
        changed_files = re.findall(r"### `([^`]+)`", context)
        auto_findings = []
        scope_warning = verify_pr_scope(changed_files)
        if scope_warning:
            auto_findings.append({"path": "PR SCOPE", "issue": scope_warning, "severity": "major"})
        files_to_audit = [
            f for f in changed_files if (f.endswith(".tsx") or f.endswith(".ts")) and os.path.exists(f)
        ]
        if files_to_audit:
            script_path = self._resolve_antipatterns_script()
            if script_path and os.path.exists(script_path):
                audit_res = dev_tools.orchestrator.run_command(
                    ["node", script_path, "--json"] + files_to_audit,
                    check=False,
                )
                output = audit_res.stdout if isinstance(audit_res, subprocess.CompletedProcess) else str(audit_res)
            else:
                output = ""
            if output and "{" in output:
                json_start = output.find("{")
                json_end = output.rfind("}") + 1
                try:
                    audit_data: Any = json.loads(output[json_start:json_end])
                    # Ensure audit_data is a dictionary, and recursively parse if it's a stringified JSON
                    if isinstance(audit_data, str):
                        try:
                            audit_data = json.loads(audit_data)
                        except json.JSONDecodeError:
                            audit_data = {}
                except json.JSONDecodeError:
                    audit_data = {}

                if isinstance(audit_data, dict):
                    violations_map = audit_data.get("violations", {})
                    if isinstance(violations_map, dict):
                        for filepath, violations in violations_map.items():
                            if isinstance(violations, list):
                                for v in violations:
                                    if isinstance(v, dict):
                                        auto_findings.append(
                                            {
                                                "path": str(filepath),
                                                "issue": (
                                                    f"{v.get('pattern', 'N/A')}: "
                                                    f"{v.get('message', 'No message')} (value: "
                                                    f"{v.get('value', 'N/A')})"
                                                ),
                                                "severity": str(v.get("severity", "minor")),
                                            }
                                        )
        return auto_findings

    def handle_comment_command(self, prNumber: int, command: str, comment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Delegates command handling to the CommandHandler.
        """
        handler = CommandHandler(self)
        return handler.handle(prNumber, command, comment_id)

    def parse_comment(self, body: str, author_association: str) -> Dict[str, Any]:
        """
        Parses a comment body and returns the intended actions.
        Consolidates detection logic using regex patterns with word boundaries.
        """
        results = {k: bool(re.search(v, body)) for k, v in self._CMD_PATTERNS.items()}

        return {
            "conflict_resolve": results["conflict_resolve"],
            "update_snapshots": results["update_snapshots"],
            "ai_chatops": results["ai_fix"] or results["ai_review"],
        }

    def handle_audit_gate(self) -> Dict[str, Any]:
        """Evaluate the audit gate."""
        script_path = self._resolve_antipatterns_script()
        if not script_path or not os.path.exists(script_path):
            return {"current": 0, "baseline": 0, "status": "skipped", "reason": "detect-antipatterns.mjs not found"}
        current_count = int(dev_tools.orchestrator.run_command(["node", script_path, "--count-only"]) or 0)
        baseline_count = self.resolve_baseline(None, "AUDIT_BASELINE", -1)

        is_shallow = dev_tools.orchestrator.run_command(["git", "rev-parse", "--is-shallow-repository"],
            check=False).stdout.strip() == "true"

        if baseline_count == -1 or is_shallow:
            val = self.get_env_or_gha("AUDIT_BASELINE")
            if val:
                return {
                    "current": current_count,
                    "baseline": int(val),
                    "status": "success" if current_count <= int(val) else "error",
                }

            if is_shallow:
                # In a shallow clone, git ls-tree/show on base branch will fail or be incomplete.
                log_warn("Shallow repository detected and no AUDIT_BASELINE variable found. Falling back to 0.")
                return {
                    "current": current_count,
                    "baseline": 0,
                    "status": "success" if current_count <= 0 else "error",
                }

            baseline_count = 0
            # Robust base branch discovery: try config, then origin/main, then main
            base_candidates = [dev_tools.orchestrator.get_config().base_branch, "origin/main", "main"]
            base_ref = None
            for cand in base_candidates:
                if (
                    cand
                    and dev_tools.orchestrator.run_command(["git", "rev-parse", "--verify", cand],
                        check=False,
                        log_on_error=False).returncode
                    == 0
                ):
                    base_ref = cand
                    break

            if not base_ref:
                log_warn("Could not determine base branch for audit baseline. Falling back to 0.")
                return {
                    "current": current_count,
                    "baseline": 0,
                    "status": "success" if current_count <= 0 else "error",
                }

            base_files = dev_tools.orchestrator.run_command(["git",
                "ls-tree",
                "-r",
                base_ref,
                "--name-only"]).splitlines()
            # Ensure AUDIT_CHECK_DIRS are handled as a list of prefixes
            relevant = [
                mf
                for mf in base_files
                if (mf.endswith(".tsx") or mf.endswith(".ts"))
                and any(mf == d or mf.startswith(d + "/") for d in dev_tools.orchestrator.get_config().audit_check_dirs)
            ]
            for mf in relevant:
                res_show = dev_tools.orchestrator.run_command(["git", "show", f"{base_ref}:{mf}"],
                    check=False,
                    log_on_error=False)
                if res_show.returncode == 0:
                    baseline_count += int(
                        dev_tools.orchestrator.run_command(
                            [
                                "node",
                                script_path,
                                "--count-only",
                                "-",
                            ],
                            input_str=res_show.stdout,
                        )
                        or 0
                    )
        return {
            "current": current_count,
            "baseline": baseline_count,
            "status": "success" if current_count <= baseline_count else "error",
        }

    def manage_reviews(
        self,
        check_responses: bool = False,
        cleanup_comments: bool = False,
        dry_run: bool = True,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Check review responses and clean up comments."""
        g = get_github_client()
        repo = g.get_repo(dev_tools.orchestrator.get_repo_name())
        login = g.get_user().login
        prs_data = []
        # PyGithub get_pulls handles per_page internally. Directly slice the paginated list.
        for pr in repo.get_pulls(state="open", sort="updated", direction="desc")[:limit]:
            last_review = next((r for r in pr.get_reviews().reversed if r.user.login == login), None)
            status = (
                "ACTION: Needs Review"
                if not last_review
                else ("ACTION: Needs Re-Review" if last_review.commit_id != pr.head.sha else "STATE: Up-To-Date")
            )
            item = {"number": pr.number, "title": pr.title, "status": status, "unaddressed": []}
            if check_responses:
                our_coms = [c for c in pr.get_review_comments() if c.user.login == login]
                after_coms = [
                    c
                    for c in pr.get_review_comments()
                    if c.user.login != login and any(c.in_reply_to_id == oc.id for oc in our_coms)
                ]
                if our_coms and not after_coms:
                    item["unaddressed"] = [f"{c.path}:{c.position}" for c in our_coms]
            if cleanup_comments:
                for c in pr.get_issue_comments():
                    if c.user.login == login and "<!-- td-review-manager-comment -->" in c.body:
                        if not dry_run:
                            c.delete()
            prs_data.append(item)
        return prs_data

    def track_review(self, pr_num: int, status: str, auditor: str, dry_run: bool = True) -> Dict[str, Any]:
        """Record a review status entry."""
        tracking_file = "REVIEW_TRACKING.md"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        content = (
            open(tracking_file, encoding="utf-8").read()
            if os.path.exists(tracking_file)
            else (
                "# "
                "PR Review "
                "Tracking\n\n| PR "
                "| Status "
                "| Auditor "
                "| Last "
                "Updated |\n|----|--------|---------|--------------|\n"
            )
        )
        lines = content.splitlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("|") and f"| #{pr_num} |" in line:
                new_lines.append(f"| #{pr_num} | {status} | {auditor} | {now} |")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"| #{pr_num} | {status} | {auditor} | {now} |")
        if not dry_run:
            from dev_tools.utils import safe_write_file

            safe_write_file(tracking_file, "\n".join(new_lines) + "\n")
        return {"pr": pr_num, "status": status, "updated": not dry_run}

    def run_ux_audit(
        self,
        route: Optional[str] = None,
        all_routes: bool = False,
        desktop: bool = False,
        mobile: bool = False,
        screenshots_only: bool = False,
        images_only: bool = False,
        contrast_only: bool = False,
        overflow_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs the UX audit suite using Playwright.
        """
        # Ensure routes are discovered
        dev_tools.orchestrator.run_command(["pnpm", "exec", "tsx", "scripts/ux-discover-routes.ts"])

        routes = ["/"]
        if all_routes:
            with open("artifacts/ux-audit/routes.json", "r", encoding="utf-8") as f:
                routes = json.load(f)["routes"]
        elif route:
            routes = [route]

        viewports = []
        if desktop:
            viewports = ["desktop-1280", "desktop-1440"]
        elif mobile:
            viewports = ["mobile-375", "mobile-390", "mobile-430"]

        flags = []
        if images_only:
            flags.append("--images-only")
        if overflow_only:
            flags.append("--overflow-only")
        if contrast_only:
            flags.append("--contrast-only")

        results = []
        for r in routes:
            cmd = ["pnpm", "exec", "tsx", "scripts/ux-audit-runner.ts", r]
            if viewports:
                for vp in viewports:
                    res = dev_tools.orchestrator.run_command(cmd + [vp] + flags, check=False)
                    results.append(
                        {
                            "route": r,
                            "viewport": vp,
                            "status": "success" if res.returncode == 0 else "error",
                        }
                    )
            else:
                res = dev_tools.orchestrator.run_command(cmd + flags, check=False)
                results.append({"route": r, "status": "success" if res.returncode == 0 else "error"})

        return {"status": "success", "results": results}

    def run_lighthouse(self, route: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs Lighthouse audits.
        """
        # Ensure routes are discovered
        dev_tools.orchestrator.run_command(["pnpm", "exec", "tsx", "scripts/ux-discover-routes.ts"])

        cmd = ["pnpm", "exec", "tsx", "scripts/ux-lighthouse-runner.ts"]
        if route:
            # Note: Lighthouse runner might need updates to handle single route arg if desired,
            # but for now it uses routes.json.
            pass

        res = dev_tools.orchestrator.run_command(cmd, check=False)
        return {"status": "success" if res.returncode == 0 else "error", "output": res.stdout}

    def generate_ux_report(self) -> Dict[str, Any]:
        """
        Aggregates results into a Markdown report.
        """
        generate_report()
        return {"status": "success", "report": "artifacts/ux-audit/ux-audit-report.md"}
