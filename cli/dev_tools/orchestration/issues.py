"""Issue/PR operations and conflict-file helpers."""
import os
import re
import subprocess
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from dev_tools.models import IssueSummary
from dev_tools.utils import CLIError, get_gha_variable, get_github_client, log_warn, sanitize_path
from dev_tools.orchestration.review import ReviewMixin
import dev_tools.orchestrator



class IssueMixin(ReviewMixin):
    """Issue/PR operations and conflict-file helpers."""

    def resolve_conflict(self, file_path: str, strategy: Optional[str] = None) -> bool:
        """
        Resolves git conflict markers in a file using a deterministic strategy (ours, theirs, union).
        """
        if not os.path.exists(file_path):
            raise CLIError(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if "<<<<<<<" not in content:
                return True

            strat = (strategy or "ours").lower()
            lines = content.splitlines(keepends=True)
            new_lines = []
            in_ours = False
            in_theirs = False
            ours_block: List[str] = []
            theirs_block: List[str] = []

            for line in lines:
                if line.startswith("<<<<<<<"):
                    in_ours = True
                    in_theirs = False
                    ours_block = []
                    theirs_block = []
                elif line.startswith("======="):
                    in_ours = False
                    in_theirs = True
                elif line.startswith(">>>>>>>"):
                    in_ours = False
                    in_theirs = False
                    if strat == "ours":
                        new_lines.extend(ours_block)
                    elif strat == "theirs":
                        new_lines.extend(theirs_block)
                    elif strat == "union":
                        new_lines.extend(ours_block)
                        new_lines.extend(theirs_block)
                    else:
                        new_lines.extend(ours_block)
                elif in_ours:
                    ours_block.append(line)
                elif in_theirs:
                    theirs_block.append(line)
                else:
                    new_lines.append(line)

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            return True
        except Exception as e:
            log_warn(f"Failed to resolve conflicts in {file_path}: {e}")
            return False

    def analyze_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise CLIError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return (
            f"Deterministic "
            f"Analysis for "
            f"{file_path}:\nLength: {len(content)} "
            f"characters, {len(content.splitlines())} "
            f"lines."
        )

    def find_conflict_files(self) -> List[str]:
        """
        Robustly finds files with git conflict markers, ignoring build artifacts and dependencies.
        """
        res = dev_tools.orchestrator.run_command(
            [
                "grep",
                "-lrE",
                "^<<<<<<<|^=======|^>>>>>>>",
                ".",
                "--exclude-dir=node_modules",
                "--exclude-dir=dist",
                "--exclude-dir=.git",
                "--exclude-dir=build",
                "--exclude-dir=target",
                "--exclude-dir=.venv",
            ],
            check=False,
            log_on_error=False,
        )
        if isinstance(res, subprocess.CompletedProcess) and res.returncode == 0 and res.stdout:
            return [f.strip() for f in res.stdout.splitlines() if f.strip()]
        return []

    def get_env_or_gha(self, env_var: str) -> Optional[str]:
        if env_var in os.environ:
            return os.environ[env_var]
        return get_gha_variable(env_var)

    def resolve_baseline(self, file_path: Optional[str], env_var: str, fallback_value: int) -> int:
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return int(f.read().strip() or fallback_value)
        val = self.get_env_or_gha(env_var)
        if val is not None and str(val).strip() != "":
            return int(val)
        return fallback_value

    def detect_conflicts(self, target_pr_num: Optional[int] = None) -> Dict[Tuple[int, ...], List[str]]:
        """
        Detect file overlap between open PRs (shared touched paths).

        This is NOT merge-conflict detection — for mergeability use GitHub mergeStateStatus/mergeable.
        """
        repo_name = dev_tools.orchestrator.get_repo_name()
        if not repo_name:
            scope = f"PR #{target_pr_num}" if target_pr_num is not None else "all open PRs"
            raise CLIError(
                f"Could not determine repository name for detect-conflicts scan of {scope}: "
                "no GITHUB_REPOSITORY env var and no git origin remote found. "
                "Set GITHUB_REPOSITORY=owner/repo or run inside a git checkout."
            )
        repo = get_github_client().get_repo(repo_name)
        open_prs = list(repo.get_pulls(state="open"))
        file_to_prs = defaultdict(list)
        for pr in open_prs:
            for f in self.get_pr_files(pr):
                file_to_prs[f].append(pr.number)
        conflicts = defaultdict(list)
        for filename, prs in file_to_prs.items():
            if len(prs) > 1 and (target_pr_num is None or target_pr_num in prs):
                conflicts[tuple(sorted(prs))].append(filename)
        return conflicts

    def detect_semantic_overlaps(self, target_pr_num: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Detects both textual file overlaps and shared exported symbol modifications across open PRs.
        """
        conflicts = self.detect_conflicts(target_pr_num)
        results = []
        for pr_pair, files in conflicts.items():
            results.append({
                "prs": list(pr_pair),
                "files": files,
                "type": "file_overlap",
            })

        # Symbol export overlap detection
        open_prs = self.github.list_pull_requests(state="open")
        prs_in_conflicts = {num for pr_pair in conflicts.keys() for num in pr_pair}
        if target_pr_num is not None:
            prs_in_conflicts.add(target_pr_num)
            open_prs = [p for p in open_prs if p.get("number") in prs_in_conflicts]

        symbol_map: Dict[str, Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
        for pr in open_prs:
            pr_num = pr.get("number")
            if not pr_num:
                continue
            try:
                diff_text = self.github.fetch_pr_diff(pr_num)
                file_exports = self.extract_exports_from_diff(diff_text)
                for filepath, symbols in file_exports.items():
                    for sym in symbols:
                        symbol_map[filepath][sym].append(pr_num)
            except Exception as e:
                log_warn(f"Could not fetch diff for PR #{pr_num}: {e}")

        for filepath, sym_dict in symbol_map.items():
            for sym, prs in sym_dict.items():
                if len(prs) > 1 and (target_pr_num is None or target_pr_num in prs):
                    results.append({
                        "prs": sorted(prs),
                        "file": filepath,
                        "symbol": sym,
                        "type": "export_overlap",
                    })

        return results

    def _has_spec_section(self, section_name: str, text: str) -> bool:
        """Robustly checks for the presence of a markdown section or numbered list item."""
        # Matches markdown headers (# Section Name) or numbered items (1. SECTION NAME)
        header_pattern = rf"^\s*#+\s*{re.escape(section_name)}\b"
        list_pattern = rf"^\s*\d+\.\s*{re.escape(section_name)}\b"
        return bool(
            re.search(header_pattern, text, re.IGNORECASE | re.MULTILINE)
            or re.search(list_pattern, text, re.IGNORECASE | re.MULTILINE)
        )

    def _read_safe_file(self, file_path: str, max_size: int = 1024 * 1024) -> str:
        """
        Validates and reads a file from within the repository root.
        """
        # 1. Sanitize the path first
        clean_path = sanitize_path(file_path)
        if not clean_path:
            raise CLIError("Security Error: Invalid or empty file path.")

        abs_path = os.path.abspath(clean_path)
        repo_root = os.path.abspath(os.getcwd())
        try:
            if os.path.commonpath([repo_root, abs_path]) != repo_root:
                raise CLIError(f"Security Error: Path {file_path} is outside of repository root.")
        except ValueError:
            raise CLIError(f"Security Error: Path {file_path} is invalid or outside of repository root.")

        if not os.path.exists(abs_path):
            raise CLIError(f"File not found: {file_path}")

        if os.path.getsize(abs_path) > max_size:
            raise CLIError(f"File size exceeds limit of {max_size} bytes.")

        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def create_issue(self, title: str, body: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates a new GitHub issue.
        """
        res = self.github.create_issue(title, body, repo=repo)
        return {"status": "success", "issue": IssueSummary(**res).model_dump()}

    def create_pull_request(
        self, title: str, body: str, head: str, base: str = "main", draft: bool = False, repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new GitHub pull request.
        """
        return self.github.create_pull_request(title, body, head, base, draft=draft, repo=repo)

    def get_issue_details(self, issueNumber: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches details of a GitHub issue.
        """
        if repo:
            return self.github.fetch_issue_details(issueNumber, repo=repo)
        return self.github.fetch_issue_details(issueNumber)

    def update_issue(
        self,
        issueNumber: int,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        addLabels: Optional[List[str]] = None,
        removeLabels: Optional[List[str]] = None,
        state: Optional[str] = None,
        repo: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Updates an issue's body, labels, and/or state.
        """
        res: Any = None

        # Handle full label replacement first as it is mutually exclusive with incremental changes
        if labels is not None:
            if repo:
                res = self.github.update_issue(issueNumber, body=body, labels=labels, state=state, repo=repo)
            else:
                res = self.github.update_issue(issueNumber, body=body, labels=labels, state=state)
        else:
            # Handle incremental label changes (can happen together)
            if addLabels:
                if repo:
                    self.github.add_labels(issueNumber, addLabels, repo=repo)
                else:
                    self.github.add_labels(issueNumber, addLabels)
                res = {"status": "success", "message": f"Added labels {addLabels} to #{issueNumber}"}

            if removeLabels:
                for label in removeLabels:
                    if repo:
                        self.github.remove_label(issueNumber, label, repo=repo)
                    else:
                        self.github.remove_label(issueNumber, label)
                res = {"status": "success", "message": f"Removed labels {removeLabels} from #{issueNumber}"}

            # Handle body/state update if not already done via 'labels' PATCH
            if body is not None or state is not None:
                if repo:
                    res = self.github.update_issue(issueNumber, body=body, state=state, repo=repo)
                else:
                    res = self.github.update_issue(issueNumber, body=body, state=state)

        if res is None:
            raise CLIError("Nothing to update. Provide body, labels, or state.")

        if res.get("status") == "success":
            return res

        return {"status": "success", "issue": IssueSummary(**res).model_dump()}

    def post_comment(self, entity_number: int, body: Optional[str], repo: Optional[str] = None) -> Dict[str, Any]:
        """
        Posts a comment to a Pull Request or Issue.
        """
        if body is None or not body.strip():
            raise CLIError("Comment body cannot be empty.")
        if repo:
            return self.github.create_issue_comment(entity_number, body, repo=repo)
        return self.github.create_issue_comment(entity_number, body)

    def validate_content(self, title: str, body: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
        """
        Validates issue content against spec-driven headers and anti-patterns.
        """
        findings = []
        warnings = []

        if config is None:
            audit_base = self.get_audit_results(content="")
            config = audit_base.get("config", {})

        if not body.strip():
            findings.append("Issue body is empty.")

        for i, block in enumerate(self.extract_code_blocks(body)):
            res = self.get_audit_results(content=block)
            violations = res.get("violations", {}).get("stdin", [])
            for v in violations:
                val = v.get("value", "N/A")
                findings.append(f"Code block {i+1}: {v['message']} (value: {val})")
            for comp, path in config.get("existingComponents", {}).items():
                if re.search(rf"(create|build|make|add|new)\s+.*{comp}", block, re.IGNORECASE):
                    warnings.append(f"Code block {i+1}: Suggests `{comp}` (exists at `{path}`)")

        for comp, path in config.get("existingComponents", {}).items():
            if re.search(rf"(create|build|make|add\s+a\s+new)\s+.*{comp}\b", body, re.IGNORECASE):
                warnings.append(f"Issue suggests `{comp}` (exists at `{path}`)")

        if re.match(r"^Draft.*:", title) and "```markdown" in body:
            md_match = re.search(r"```markdown\n(.*?)\n```", body, re.DOTALL)
            if md_match:
                for field in config.get("requiredContentFields", []):
                    if not re.search(rf"^{field}:", md_match.group(1), re.MULTILINE):
                        findings.append(f"Missing frontmatter: `{field}`")

        is_exempt = (
            title.lower().startswith("fix(ci):")
            or "ci failure" in title.lower()
            or "ci-failure-branch:" in body
            or "[skip-spec-check]" in body
            or "[skip-spec-check]" in title
        )

        if not is_exempt and not re.search(r"(acceptance criteria|definition of done|## done|verify|test)",
            body,
            re.IGNORECASE):
            warnings.append("No acceptance criteria.")

        if re.search(r"tailwind|className.*flex|className.*grid", body, re.IGNORECASE) and not re.search(
            r"<Box|<Stack|<Grid|primitives|design.tokens", body, re.IGNORECASE
        ):
            warnings.append("Mentions Tailwind but not layout primitives.")

        # Spec-Driven Issue Validation
        if not is_exempt:
            missing_spec_sections = [s for s in dev_tools.orchestrator.get_config().spec_sections if not self._has_spec_section(s, body)]
            if missing_spec_sections:
                findings.append(f"Missing spec-driven sections: {', '.join(f'`{s}`' for s in missing_spec_sections)}")

        return {"findings": findings, "warnings": warnings}

    def validate_issue(
        self,
        issueNumber: Optional[int] = None,
        all_open: bool = False,
        post_comments: bool = False,
        dry_run: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if "issue_number" in kwargs and kwargs["issue_number"] is not None and issueNumber is None:
            issueNumber = int(kwargs["issue_number"])
        repo = get_github_client().get_repo(dev_tools.orchestrator.get_repo_name() or "")
        issues: List[Any] = []
        if all_open:
            issues = list(repo.get_issues(state="open"))
        elif issueNumber:
            issues = [repo.get_issue(issueNumber)]
        else:
            raise CLIError("Provide --issue-number or --all-open")

        results = []
        total_findings = 0

        audit_base = self.get_audit_results(content="")
        config = audit_base.get("config", {})

        for issue in issues:
            body = issue.body or ""
            title = issue.title or ""

            validation = self.validate_content(title, body, config=config)
            findings = validation["findings"]
            warnings = validation["warnings"]

            issue_result = {
                "number": issue.number,
                "title": title,
                "findings": findings,
                "warnings": warnings,
            }
            results.append(issue_result)
            total_findings += len(findings)
            if post_comments and (findings or warnings):
                comment = "## 🤖 Issue Quality Review\n\n"
                if findings:
                    comment += "### ❌ Violations\n" + "\n".join(f"- {f}" for f in findings) + "\n\n"
                if warnings:
                    comment += "### ⚠️ Warnings\n" + "\n".join(f"- {w}" for w in warnings) + "\n"
                if not dry_run:
                    issue.create_comment((
                        f"{comment}\n---\n*Generated "
                        f"by `{dev_tools.orchestrator.get_config().cli_alias} "
                        f"validate-issue`*"
                    ))

        return {
            "status": "success" if total_findings == 0 else "error",
            "issues": results,
            "total_findings": total_findings,
        }

    def handle_detect_conflicts(self, pr_num: Optional[int] = None, all_prs: bool = False) -> List[Dict[str, Any]]:
        """
        Handle detect-conflicts request, returning PR-vs-PR file overlap groups.

        Each group is explicitly typed with "type": "file_overlap" so consumers
        do not mistake touched-path overlap for git merge unmergeability.
        """
        if pr_num is not None and all_prs:
            raise CLIError("Provide either pr_num or all_prs, not both")
        target_pr = pr_num if not all_prs else None
        conflicts = self.detect_conflicts(target_pr)
        formatted = []
        for pr_pair, files in conflicts.items():
            formatted.append({
                "prs": list(pr_pair),
                "files": files,
                "type": "file_overlap",
            })
        return formatted

    def handle_status_board(self, limit: int = 10) -> List[Dict[str, Any]]:
        # Use our custom GitHubClient which implements disk caching
        prs = self.github.list_pull_requests(state="open", limit=limit)
        prs_data = []
        for pr in prs:
            branch = pr.get("headRefName") or ""
            m = re.search(r"issue-(\d+)", branch)
            issue = f"#{m.group(1)}" if m else "—"
            status = "Draft" if pr.get("isDraft") else "Open"
            prs_data.append({"branch": branch, "issue": issue, "status": status, "number": pr.get("number")})
        return prs_data
