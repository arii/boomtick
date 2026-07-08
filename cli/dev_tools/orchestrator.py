import hashlib
import os
import re
import json
import sys
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import quote, urlparse
from collections import defaultdict
from dev_tools.ux_report import generate_report
import tempfile

from dev_tools.services.github import GitHubClient
from dev_tools.services.jules import JulesClient
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from dev_tools.services.ai_service import AIClient
    from dev_tools.services.repair_service import RepairService
    from dev_tools.services.vision_service import VisionService
from dev_tools.utils import verify_ci_metrics
from dev_tools.utils import log_error, log_warn, get_or_create_log_dir, CLIError
from dev_tools.handlers.command_handler import CommandHandler
from dev_tools.models import IssueSummary, PRSummary
from dev_tools.utils import (
    get_github_token,
    get_github_client,
    get_repo_name,
    get_gha_variable,
    set_gha_variable,
    run_command,
    is_ai_available,
    extract_failing_info,
    clean_gha_logs,
    walk_tsx,
    find_patterns_in_file,
    get_bundle_size,
    get_any_count,
    verify_pr_scope
)
from dev_tools.config import get_config



PROJECT_CONFIG = get_config()
AUDIT_CHECK_DIRS = PROJECT_CONFIG.audit_check_dirs
SPEC_SECTIONS = PROJECT_CONFIG.spec_sections

# Pre-compute UI indicators for heuristic checks
UI_INDICATORS = PROJECT_CONFIG.ui_indicators

class Orchestrator:
    # Command detection patterns with word boundaries to avoid false positives
    _CMD_PATTERNS = {
        "conflict_resolve": r"(?<!\w)@conflict-resolve\b",
        "update_snapshots": r"(?<!\w)@update-snapshots\b",
        "ai_fix": r"(?<!\w)/ai-fix\b",
        "ai_review": r"(?<!\w)/ai-review\b",
        "jules_fix_ci": r"(?<!\w)@jules-fix-ci\b",
    }

    def _extract_diff_hunks(self, diff_text: str) -> Dict[str, List[Tuple[int, int]]]:
        """Extracts modified line ranges (hunks) from a git diff string."""
        hunks = defaultdict(list)
        current_file = None
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:]
            elif line.startswith("@@") and current_file:
                m = re.search(r"\+(\d+),?(\d*)", line)
                if m:
                    start = int(m.group(1))
                    count = int(m.group(2)) if m.group(2) else 1
                    hunks[current_file].append((start, start + count - 1))
        return hunks

    def __init__(self, no_cache: bool = False) -> None:
        self._github: Optional[GitHubClient] = None
        self._ai: Optional[AIClient] = None
        self._jules: Optional[JulesClient] = None
        self.no_cache = no_cache

    @property
    def github(self) -> GitHubClient:
        if self._github is None:
            self._github = GitHubClient(no_cache=self.no_cache)
        return self._github

    @property
    def ai(self) -> 'AIClient':
        if self._ai is None:
            from dev_tools.services.ai_service import AIClient
            self._ai = AIClient()
        return self._ai

    @property
    def jules(self) -> JulesClient:
        if self._jules is None:
            self._jules = JulesClient()
        return self._jules

    def initialize_jules(self, client: JulesClient) -> None:
        self._jules = client

    @property
    def vision(self) -> 'VisionService':
        from dev_tools.services.vision_service import VisionService
        return VisionService()

    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _cleanup_worktree(self, worktree_path: str) -> None:
        """Robustly cleans up a git worktree and its directory."""
        # Unregister and attempt to remove the worktree via git
        run_command(["git", "worktree", "remove", "-f", worktree_path], check=False, log_on_error=False)

        # Forcefully delete the directory if it still exists
        if os.path.exists(worktree_path):
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Prune stale worktree metadata
        run_command(["git", "worktree", "prune"], check=False, log_on_error=False)

        # Final safety check
        if os.path.exists(worktree_path):
            raise CLIError(f"Failed to clean up worktree directory: {worktree_path}")

    def evaluate_pr_heuristics(self, pr: Dict[str, Any], diff: str, checks: Dict[str, Any]) -> str:
        """Applies heuristic rules to a PR diff and checks, returning specific feedback."""
        # Pre-process diff to get unique files for faster heuristic matching
        files_in_diff = set()
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                files_in_diff.add(line[6:])

        is_ui = any(any(ind in f for ind in UI_INDICATORS) for f in files_in_diff)
        is_python = any(f.endswith(".py") for f in files_in_diff)
        is_infra = any(any(ind in f for ind in PROJECT_CONFIG.infra_file_paths) for f in files_in_diff)

        fails = [c['name'] for c in checks.get('check_runs', []) if c.get('conclusion') == 'failure']

        feedback = f"### Specific Review for PR #{pr['number']}\n\n"

        # What's working
        feedback += "**What is working well:**\n"
        feedback += f"- The scope is clearly defined in branch `{pr.get('head', {}).get('ref', 'unknown')}`.\n"
        if not fails:
            feedback += "- All CI checks appear to be passing.\n"

        feedback += "\n**Specific Issues & Actionable Fixes:**\n"

        if fails:
            feedback += f"- **CI Failure:** The following checks are failing: {', '.join(fails)}. Please investigate the logs for these jobs.\n"
            if "Build & E2E" in fails:
                feedback += "  - *Fix:* Ensure `pnpm run build` passes locally and all `playwright` tests succeed via `pnpm test:e2e`.\n"
            elif "deploy" in fails:
                feedback += "  - *Fix:* Verify that the `dist` directory compiles correctly without TypeScript or Vite errors.\n"

        if is_ui:
            tailwind_indicators = PROJECT_CONFIG.tailwind_indicators
            if any(ind in diff for ind in tailwind_indicators):
                feedback += "- **Design System Anti-patterns:** The diff contains raw Tailwind classes (e.g. padding/margin utility classes, arbitrary values).\n"
                feedback += "  - *Fix:* Replace raw Tailwind layout classes with `Stack`, `Box`, or `Grid` primitives using design tokens (e.g., `gap={4}`, `paddingY={{ base: 4, md: 1.5 }}`). Verify by running `node scripts/detect-antipatterns.mjs`.\n"

            feedback += "- **Mobile UX Verification:** For any UI additions, ensure horizontal layout does not overflow a 390px viewport.\n"
            feedback += "  - *Fix:* If adding interactive elements, wrap them to enforce a minimum 48x48px touch target for accessibility.\n"

        if is_python:
            feedback += "- **Python Scripting:** Python changes detected.\n"
            feedback += "  - *Fix:* Ensure `python3 -m pytest tests/` passes. Update `test_td-cli` or equivalent test files if extending `dev-tools`.\n"

        if is_infra:
            feedback += PROJECT_CONFIG.infra_feedback

        if pr.get('mergeable') is False:
            base_branch_name = PROJECT_CONFIG.base_branch_name
            feedback += f"- **Merge Conflicts:** This PR has conflicts with the `{base_branch_name}` base branch.\n"
            feedback += f"  - *Fix:* Pull `{base_branch_name}` into your branch, resolve the conflicts (e.g., via `{PROJECT_CONFIG.cli_alias} gh conflicts`), and force push.\n"

        if "overlap" in pr.get('title', '').lower() or "cli" in pr.get('title', '').lower():
            feedback += "- **Overlap / Interdependency:** This PR touches dev-tools or overlap logic.\n"
            feedback += f"  - *Fix:* Ensure this is rebased against recent changes in the `{PROJECT_CONFIG.base_branch_name}` branch to avoid overlapping functionality.\n"

        # Default if no specific issues caught by heuristics
        if feedback.endswith("**Specific Issues & Actionable Fixes:**\n"):
            feedback += "- Review the diff against `audit` guidelines. Ensure no console errors exist in the target components.\n"

        return feedback



    def review_pr(self, pr_number: int) -> Dict[str, Any]:
        """
        Fetches a PR, its diff, and generates a code review using LocalAI/Gemini.
        """
        pr_details = self.github.fetch_pr_details(pr_number)
        sha = pr_details.get('head', {}).get('sha')
        check_runs = self.github.fetch_check_runs(sha)
        pr_details['checkResults'] = check_runs

        # Fetch logs for failing checks
        failing_logs = {}
        structured_failures = []
        for run in check_runs:
            if run.get('conclusion') == 'failure':
                logs = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))
                failing_logs[run.get('name')] = logs[-5000:]  # Keep last 5k chars
                findings = extract_failing_info(logs)
                for f in findings:
                    structured_failures.append({
                        "check": run.get('name'),
                        "file": f['file'],
                        "line": f['line'],
                        "message": f['message'],
                        "type": f['type']
                    })

        pr_details['failingLogs'] = failing_logs
        pr_details['structuredFailures'] = structured_failures

        pr_diff = self.github.fetch_pr_diff(pr_number)
        diff_hash = self._hash_content(pr_diff)
        # Store cache in local logs directory to avoid /tmp Security Error
        review_dir = get_or_create_log_dir("reviews")
        cache_file = os.path.join(review_dir, f"review_cache_{pr_number}_{diff_hash}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f: return json.load(f)
        review_result = self.ai.generate_code_review(pr_details, pr_diff)
        with open(cache_file, 'w') as f: json.dump(review_result, f)
        return review_result

    def resolve_conflict(self, file_path: str) -> bool:
        """
        Detects merge conflicts via GitHubClient (implicit local git), analyzes logic with AI.
        """
        return self.ai.resolve_file_conflicts(file_path)

    def analyze_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise CLIError(f"File not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        prompt = f"Analyze this file for bugs, style issues, and potential improvements:\n\n{content[:20000]}"
        return self.ai.generate(prompt)

    def find_conflict_files(self) -> List[str]:
        """
        Robustly finds files with git conflict markers, ignoring build artifacts and dependencies.
        """
        res = run_command([
            "grep", "-lrE", "^<<<<<<<|^=======|^>>>>>>>", ".",
            "--exclude-dir=boomtick-pkg",
            "--exclude-dir=node_modules",
            "--exclude-dir=dist",
            "--exclude-dir=.git",
            "--exclude-dir=build",
            "--exclude-dir=target",
            "--exclude-dir=.venv"
        ], check=False, log_on_error=False)
        if res.returncode == 0 and res.stdout:
            return [f.strip() for f in res.stdout.splitlines() if f.strip()]
        return []

    def dispatch_jules_review(self, branch: str, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Automates the creation of Jules sessions.
        """
        if not self.github.branch_exists(branch):
            raise CLIError(f"Branch '{branch}' does not exist in the repository.")

        # Prevent dispatching Jules for consolidation/aggregation tasks
        if re.search(r"\b(consolidate|aggregate)\s+pr(s)?\b", prompt.lower()):
            raise CLIError("PR consolidation and aggregation tasks should be performed directly using the 'gh aggregate' command instead of dispatching a Jules session.")

        source_id = self.jules.discover_source_id(self.github.repo)
        if not source_id:
            raise CLIError(f"Could not find a Jules source mapping for repository: {self.github.repo}")

        session = self.jules.create_session_from_source(source_id, branch, prompt)
        return session

    # --- Helper methods ported from td-cli ---

    def get_env_or_gha(self, env_var: str) -> Optional[str]:
        if env_var in os.environ: return os.environ[env_var]
        return get_gha_variable(env_var)

    def resolve_baseline(self, file_path: Optional[str], env_var: str, fallback_value: int) -> int:
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r') as f: return int(f.read().strip() or fallback_value)
        val = self.get_env_or_gha(env_var)
        if val is not None and str(val).strip() != "": return int(val)
        return fallback_value

    def get_audit_results(self, content: Optional[str] = None, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        cmd = ["node", "scripts/detect-antipatterns.mjs", "--json"]
        if targets:
            cmd.extend(targets)
        elif content is not None:
            cmd.append("-")
        res = run_command(cmd, check=False, input_str=content)
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            return {"violations": {}, "config": {}}

    def extract_code_blocks(self, text: str) -> List[str]:
        return re.findall(r'```(?:tsx?|jsx?|html)?\n(.*?)```', text, re.DOTALL)

    def get_pr_files(self, pr: Any) -> set[str]:
        return {f.filename for f in pr.get_files()}

    def detect_conflicts(self, target_pr_num: Optional[int] = None) -> Dict[Tuple[int, ...], List[str]]:
        repo = get_github_client().get_repo(get_repo_name())
        open_prs = list(repo.get_pulls(state='open'))
        file_to_prs = defaultdict(list)
        for pr in open_prs:
            for f in self.get_pr_files(pr):
                file_to_prs[f].append(pr.number)
        conflicts = defaultdict(list)
        for filename, prs in file_to_prs.items():
            if len(prs) > 1 and (target_pr_num is None or target_pr_num in prs):
                conflicts[tuple(sorted(prs))].append(filename)
        return conflicts

    def _has_spec_section(self, section_name: str, text: str) -> bool:
        """Robustly checks for the presence of a markdown section or numbered list item."""
        # Matches markdown headers (# Section Name) or numbered items (1. SECTION NAME)
        header_pattern = rf"^\s*#+\s*{re.escape(section_name)}\b"
        list_pattern = rf"^\s*\d+\.\s*{re.escape(section_name)}\b"
        return bool(re.search(header_pattern, text, re.IGNORECASE | re.MULTILINE) or
                    re.search(list_pattern, text, re.IGNORECASE | re.MULTILINE))

    def _read_safe_file(self, file_path: str, max_size: int = 1024 * 1024) -> str:
        """
        Validates and reads a file from within the repository root.
        """
        abs_path = os.path.abspath(file_path)
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

        with open(abs_path, 'r', encoding='utf-8') as f:
            return f.read()

    def create_issue(self, title: str, body: str) -> Dict[str, Any]:
        """
        Creates a new GitHub issue.
        """
        res = self.github.create_issue(title, body)
        return {
            "status": "success",
            "issue": IssueSummary(**res).model_dump()
        }

    def get_issue_details(self, issue_number: int) -> Dict[str, Any]:
        """
        Fetches details of a GitHub issue.
        """
        return self.github.fetch_issue_details(issue_number)

    def update_issue(self, issue_number: int, body: Optional[str] = None, labels: Optional[List[str]] = None, add_labels: Optional[List[str]] = None, remove_labels: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Updates an issue's body and/or labels.
        """
        res = None
        # Handle full label replacement first as it is mutually exclusive with incremental changes
        if labels is not None:
            res = self.github.update_issue(issue_number, body=body, labels=labels)
        else:
            # Handle incremental label changes (can happen together)
            if add_labels:
                res = self.github.add_labels(issue_number, add_labels)

            if remove_labels:
                for label in remove_labels:
                    self.github.remove_label(issue_number, label)
                # If we haven't updated yet (no add_labels or body), fetch current state
                if res is None and body is None:
                    res = self.github.fetch_issue_details(issue_number)

            # Handle body update if not already done via 'labels' PATCH
            if body is not None:
                res = self.github.update_issue(issue_number, body=body)

        if res is None:
            raise CLIError("Nothing to update. Provide body or labels.")

        return {
            "status": "success",
            "issue": IssueSummary(**res).model_dump()
        }

    def post_comment(self, entity_number: int, body: Optional[str]) -> Dict[str, Any]:
        """
        Posts a comment to a Pull Request or Issue.
        """
        if body is None or not body.strip():
            raise CLIError("Comment body cannot be empty.")
        return self.github.create_issue_comment(entity_number, body)

    def validate_issue(self, issue_number: Optional[int] = None, all_open: bool = False, post_comments: bool = False, dry_run: bool = True) -> Dict[str, Any]:
        repo = get_github_client().get_repo(get_repo_name())
        issues = []
        if all_open:
            issues = list(repo.get_issues(state='open'))
        elif issue_number:
            issues = [repo.get_issue(issue_number)]
        else:
            raise CLIError("Provide --issue-number or --all-open")

        results = []
        total_findings = 0
        audit_base = self.get_audit_results(content="")
        config = audit_base.get("config", {})

        for issue in issues:
            findings = []
            warnings = []
            body = issue.body or ''
            title = issue.title or ''

            if not body.strip():
                findings.append("Issue body is empty.")

            for i, block in enumerate(self.extract_code_blocks(body)):
                res = self.get_audit_results(content=block)
                violations = res.get("violations", {}).get("stdin", [])
                for v in violations:
                    val = v.get('value', 'N/A')
                    findings.append(f"Code block {i+1}: {v['message']} (value: {val})")
                for comp, path in config.get('existingComponents', {}).items():
                    if re.search(rf'(create|build|make|add|new)\s+.*{comp}', block, re.IGNORECASE):
                        warnings.append(f"Code block {i+1}: Suggests `{comp}` (exists at `{path}`)")
            for comp, path in config.get('existingComponents', {}).items():
                if re.search(rf'(create|build|make|add\s+a\s+new)\s+.*{comp}\b', body, re.IGNORECASE):
                    warnings.append(f"Issue suggests `{comp}` (exists at `{path}`)")
            if re.match(r'^Draft.*:', title) and '```markdown' in body:
                md_match = re.search(r'```markdown\n(.*?)\n```', body, re.DOTALL)
                if md_match:
                    for field in config.get('requiredContentFields', []):
                        if not re.search(rf'^{field}:', md_match.group(1), re.MULTILINE):
                            findings.append(f"Missing frontmatter: `{field}`")
            if not re.search(r'(acceptance criteria|definition of done|## done|verify|test)', body, re.IGNORECASE):
                warnings.append("No acceptance criteria.")
            if re.search(r'tailwind|className.*flex|className.*grid', body, re.IGNORECASE) and not re.search(r'<Box|<Stack|<Grid|primitives|design.tokens', body, re.IGNORECASE):
                warnings.append("Mentions Tailwind but not layout primitives.")

            # Spec-Driven Issue Validation
            missing_spec_sections = [s for s in SPEC_SECTIONS if not self._has_spec_section(s, body)]
            if missing_spec_sections:
                findings.append(f"Missing spec-driven sections: {', '.join(f'`{s}`' for s in missing_spec_sections)}")

            issue_result = {"number": issue.number, "title": title, "findings": findings, "warnings": warnings}
            results.append(issue_result)
            total_findings += len(findings)
            if post_comments and (findings or warnings):
                comment = "## 🤖 Issue Quality Review\n\n"
                if findings: comment += "### ❌ Violations\n" + "\n".join(f"- {f}" for f in findings) + "\n\n"
                if warnings: comment += "### ⚠️ Warnings\n" + "\n".join(f"- {w}" for w in warnings) + "\n"
                if not dry_run: issue.create_comment(f"{comment}\n---\n*Generated by `{PROJECT_CONFIG.cli_alias} validate-issue`*")

        return {"status": "success" if total_findings == 0 else "error", "issues": results, "total_findings": total_findings}

    def handle_detect_conflicts(self, pr_num: Optional[int] = None) -> List[Dict[str, Any]]:
        conflicts = self.detect_conflicts(pr_num)
        formatted = []
        for pr_pair, files in conflicts.items():
            formatted.append({"prs": list(pr_pair), "files": files})
        return formatted

    def handle_status_board(self, limit: int = 10) -> List[Dict[str, Any]]:
        # Use our custom GitHubClient which implements disk caching
        prs = self.github.list_pull_requests(state='open', limit=limit)
        prs_data = []
        for pr in prs:
            branch = pr.get("headRefName") or ""
            m = re.search(r'issue-(\d+)', branch)
            issue = f"#{m.group(1)}" if m else "—"
            status = "Draft" if pr.get("isDraft") else "Open"
            prs_data.append({
                "branch": branch,
                "issue": issue,
                "status": status,
                "number": pr.get("number")
            })
        return prs_data

    def ratchet_any(self, update: bool = False, baseline_file: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
        current = get_any_count()
        baseline = self.resolve_baseline(baseline_file, 'ANY_COUNT_BASELINE', 0)
        res = {"current": current, "baseline": baseline, "status": "success" if current <= baseline else "error"}
        if current > baseline: res["message"] = f"'any' count increased from {baseline} to {current}."
        if update:
            if not dry_run:
                if baseline_file:
                    with open(baseline_file, 'w') as f: f.write(str(current))
                else: set_gha_variable('ANY_COUNT_BASELINE', str(current))
            res["updated"] = not dry_run
        return res

    def check_bundle_size(self, update: bool = False, baseline_file: Optional[str] = None, threshold: int = 50, dry_run: bool = True) -> Dict[str, Any]:
        size = get_bundle_size()
        baseline = self.resolve_baseline(baseline_file, 'BUNDLE_BASELINE_KB', 3080)
        threshold_kb = baseline + threshold
        res = {"size_kb": size, "baseline_kb": baseline, "threshold_kb": threshold_kb, "status": "success" if size <= threshold_kb else "error"}
        if size > threshold_kb: res["message"] = f"Bundle size exceeds threshold ({size}KB > {threshold_kb}KB)."
        if update:
            if not dry_run:
                if baseline_file:
                    with open(baseline_file, 'w') as f: f.write(str(size))
                else: set_gha_variable('BUNDLE_BASELINE_KB', str(size))
            res["updated"] = not dry_run
        return res

    def migrate_tokens(self, find: Optional[str] = None, migrate: Optional[Tuple[str, str]] = None, dry_run: bool = True) -> List[Dict[str, Any]]:
        root_dir = 'src'; matches = []
        if find:
            for filepath in walk_tsx(root_dir):
                findings = find_patterns_in_file(filepath, [(re.escape(find), "Found")])
                for ln, _, content in findings:
                    matches.append({"file": filepath, "line": ln, "content": content.strip()})
        elif migrate:
            old, new = migrate
            for filepath in walk_tsx(root_dir):
                with open(filepath, 'r') as f: c = f.read()
                if old in c:
                    matches.append({"file": filepath})
                    if not dry_run:
                        with open(filepath, 'w') as f: f.write(c.replace(old, new))
        return matches

    def update_issues(self, dry_run: bool = True) -> List[Dict[str, Any]]:
        repo = get_github_client().get_repo(get_repo_name()); updates = []
        audit_base = self.get_audit_results(content=""); config = audit_base.get("config", {})
        deprecated = config.get("deprecated", {})
        for issue in repo.get_issues(state='open'):
            body = issue.body or ''; findings = []
            for old, new in deprecated.get('assets', {}).items():
                if old in body: findings.append(f"References deprecated name `{old}`. Use `{new}` instead.")
            for old, new in deprecated.get('paths', {}).items():
                if old in body: findings.append(f"References deprecated path `{old}`. New location: `{new}`")
            res = self.get_audit_results(content=body)
            violations = res.get("violations", {}).get("stdin", [])
            for v in violations: findings.append(f"Contains banned pattern: {v['message']} (value: {v.get('value', 'N/A')})")
            if findings:
                updates.append({"number": issue.number, "findings": findings})
                if not dry_run: issue.create_comment(f"## 🤖 Automated Issue Update\n\n{"\n".join(f"- {f}" for f in findings)}\n\n---\n*Generated by `{PROJECT_CONFIG.cli_alias} update-issues`*")
        return updates

    def audit_pr(self, pr_number: int, fetch: bool = False, audit: bool = False, submit: bool = False, cleanup: bool = False, dry_run: bool = True, event: Optional[str] = None) -> Dict[str, Any]:
        review_dir = get_or_create_log_dir("reviews")
        ctx_path = os.path.join(review_dir, f"pr-context-{pr_number}.md"); rev_path = os.path.join(review_dir, f"pr-review-{pr_number}.md")
        res = {"pr": pr_number, "files": {}}
        if fetch:
            repo = get_github_client().get_repo(get_repo_name()); pr = repo.get_pull(pr_number)
            title = pr.title; author = pr.user.login; desc = pr.body or '_No description provided._'
            context_lines = [f"# PR Context: #{pr.number} — {title}", f"**Author:** @{author}\n", f"## Description\n{desc}\n", "## CI Status"]

            check_runs = self.github.fetch_check_runs(pr.head.sha)
            failed_check_names = []
            detected_errors = []
            if check_runs:
                for run in check_runs:
                    status_icon = '✅' if run.get('conclusion') == 'success' else '❌' if run.get('conclusion') == 'failure' else '⏳'
                    context_lines.append(f"- {status_icon} **{run.get('name')}**: {run.get('status')} ({run.get('conclusion') or 'in_progress'})")
                    if run.get('conclusion') == 'failure':
                        failed_check_names.append(run.get('name'))
                        logs = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))

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
                        error_lines = [l for l in log_lines if any(x in l.lower() for x in ['error', 'fail', 'ts', 'vitest', 'playwright', '🔴'])]
                        snippet = "\n".join(error_lines[-20:] if error_lines else log_lines[-30:])
                        context_lines.append(f"  <details><summary>Failure Logs Snippet</summary>\n\n  ```\n  {snippet}\n  ```\n  </details>")
            else:
                context_lines.append("_No check runs found._")

            context_lines.extend(["\n## Files Changed"])
            for f in pr.get_files(): context_lines.append(f"- {'🟢' if f.status=='added' else '🔴' if f.status=='removed' else '🟡'} `{f.filename}`")
            context_lines.append("\n## Diffs")
            for f in pr.get_files():
                context_lines.append(f"\n### `{f.filename}` ({f.status})")
                patch = f.patch or '_No textual diff available._'; annotated = []; line_num = 0
                if patch != '_No textual diff available._':
                    for line in patch.splitlines():
                        if line.startswith('@@'):
                            m = re.search(r'\+(\d+)', line); line_num = int(m.group(1)) if m else line_num
                            annotated.append(line)
                        elif line.startswith('+'): annotated.append(f"{line_num:4d} |{line}"); line_num += 1
                        elif line.startswith('-'): annotated.append(f"     |{line}")
                        else: annotated.append(f"{line_num:4d} |{line}"); line_num += 1
                context_lines.append(f"```diff\n" + "\n".join(annotated) + "\n```")
            with open(ctx_path, "w") as f: f.write("\n".join(context_lines))
            template_path = os.path.join(os.path.dirname(__file__), "..", "review_template.md")

            failed_checks_str = "\n".join(f"- {name}" for name in failed_check_names) if failed_check_names else "_None_"
            errors_str = "\n".join(f"- {err}" for err in detected_errors) if detected_errors else "_None detected by parser._"

            if os.path.exists(template_path):
                with open(template_path) as f:
                    template = f.read().format(
                        pr_num=pr_number,
                        head_sha=pr.head.sha,
                        failed_checks=failed_checks_str,
                        detected_errors=errors_str
                    )
            else:
                template = f"# PR Review: #{pr_number}\n- SHA: {pr.head.sha}\n\n## CI Log Triage\n- **Failed Checks:**\n{failed_checks_str}\n- **Detected Errors:**\n{errors_str}\n"
            with open(rev_path, "w") as f: f.write(template)
            res["files"]["context"] = ctx_path; res["files"]["review"] = rev_path
        if audit:
            if not os.path.exists(ctx_path): raise CLIError(f"Context file missing: {ctx_path}")
            with open(ctx_path) as f: context = f.read()
            changed_files = re.findall(r'### `([^`]+)`', context); auto_findings = []
            scope_warning = verify_pr_scope(changed_files)
            if scope_warning: auto_findings.append({"path": "PR SCOPE", "issue": scope_warning, "severity": "major"})
            files_to_audit = [f for f in changed_files if (f.endswith('.tsx') or f.endswith('.ts')) and os.path.exists(f)]
            if files_to_audit:
                audit_res = run_command(["node", "scripts/detect-antipatterns.mjs", "--json"] + files_to_audit, check=False)
                output = audit_res.stdout
                if output and "{" in output:
                    json_start = output.find("{")
                    json_end = output.rfind("}") + 1
                    audit_data = json.loads(output[json_start:json_end])
                    for filepath, violations in audit_data.get("violations", {}).items():
                        for v in violations:
                            auto_findings.append({"path": filepath, "issue": f"{v['pattern']}: {v['message']} (value: {v.get('value', 'N/A')})", "severity": v.get('severity', 'minor')})
            res["auto_findings"] = auto_findings
        if submit:
            self.github.submit_pr_review(pr_number, rev_path, cleanup=cleanup, dry_run=dry_run, event_override=event)
        return res

    def handle_comment_command(self, pr_number: int, command: str, comment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Delegates command handling to the CommandHandler.
        """
        handler = CommandHandler(self)
        return handler.handle(pr_number, command, comment_id)

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
            "jules_fix_ci": results["jules_fix_ci"] and author_association in ['OWNER', 'MEMBER', 'COLLABORATOR']
        }

    def runtime_check(self) -> Dict[str, str]:
        """Ensures the runtime environment matches the contract."""
        run_command(["corepack", "enable"], check=False)
        run_command(["corepack", "prepare", "pnpm@10.28.2", "--activate"], check=False)

        # Mirror scripts/check-runtime.mjs logic in Python
        try:
            with open(".node-version", "r") as f:
                expected_node = f.read().strip().replace('v', '')
        except FileNotFoundError:
            try:
                with open(".nvmrc", "r") as f:
                    expected_node = f.read().strip().replace('v', '')
            except FileNotFoundError:
                expected_node = "24.16.0"

        actual_node = run_command(["node", "-v"]).strip().replace('v', '')
        is_ci = os.environ.get("CI") == "true"
        is_jules = "jules" in os.environ.get("USER", "").lower() or os.environ.get("JULES_API_KEY")

        expected_prefix = ".".join(expected_node.split(".")[:2]) + "."
        node_matches = (actual_node.startswith(expected_prefix) or is_jules) if is_ci else actual_node == expected_node

        if not node_matches and not is_jules:
            log_error(f"Node version mismatch\nExpected: {expected_node}\nActual:   {actual_node}")
            raise CLIError("Node version mismatch. Do not switch versions manually.")

        manifest_path = "package.json"
        if not os.path.exists(manifest_path) and os.path.exists("workspace.json"):
            manifest_path = "workspace.json"

        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                pkg = json.load(f)
            expected_pnpm = pkg.get("packageManager", "").replace("pnpm@", "") or "10.28.2"
        else:
            expected_pnpm = "10.28.2"

        actual_pnpm = run_command(["pnpm", "--version"]).strip()

        if not actual_pnpm or actual_pnpm != expected_pnpm:
            log_error(f"pnpm version mismatch\nExpected: {expected_pnpm}\nActual:   {actual_pnpm}")
            raise CLIError(f"Run: corepack enable && corepack prepare pnpm@{expected_pnpm} --activate")

        return {"node": actual_node, "pnpm": actual_pnpm}


    def generate_ci_summary_report(self):
        """Generates a markdown summary of CI metrics."""
        metrics_res = verify_ci_metrics()

        report = ["## 📊 CI Metrics Verification"]

        if metrics_res['status'] == 'error':
            report.append(f"❌ **FAILED**: {metrics_res['message']}")
        elif metrics_res['status'] == 'warning':
            report.append(f"⚠️  **WARNING**: {metrics_res['message']}")
        else:
            report.append("✅ **PASSED**: All metrics within limits.")

        if 'metrics' in metrics_res:
            m = metrics_res['metrics']
            report.append("\n### AI Token Usage")
            report.append(f"- **Input:** {m['inputTokens']} / {m['inputThreshold']}")
            report.append(f"- **Output:** {m['outputTokens']} / {m['outputThreshold']}")
            report.append(f"- **Total:** {m['totalTokens']} / {m['totalThreshold']}")

            report.append("\n<details><summary>Raw Metrics JSON</summary>\n")
            report.append("```json")
            report.append(json.dumps(metrics_res, indent=2))
            report.append("```\n</details>")

        return "\n".join(report)

    def pre_submit_checks(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {"steps": []}

        # 1. Runtime Check (Fail Fast)
        try:
            self.runtime_check()
            results["steps"].append({"name": "Runtime Check", "status": "success"})
        except CLIError as e:
            results["steps"].append({"name": "Runtime Check", "status": "failure", "error": str(e)})
            raise e

        def run_step(name: str, cmd: List[str]) -> None:
            try:
                run_command(cmd)
                results["steps"].append({"name": name, "status": "success"})
            except CLIError as e:
                results["steps"].append({"name": name, "status": "failure", "error": str(e)})
                raise e
        run_step("Anti-Pattern Audit", ["node", "scripts/detect-antipatterns.mjs"])
        run_step("Version Downgrade Check", [PROJECT_CONFIG.cli_alias, "gh", "verify-versions"])
        run_step("TypeScript", ["pnpm", "run", "type-check"])
        run_step("Lint", ["pnpm", "run", "lint"])
        missing_vars = [v for v in ["BUNDLE_BASELINE_KB", "ANY_COUNT_BASELINE"] if not (os.environ.get(v) or get_gha_variable(v))]
        if missing_vars: results["steps"].append({"name": "Baseline Check", "status": "warning", "message": f"Missing GHA variables: {', '.join(missing_vars)}"})
        else: results["steps"].append({"name": "Baseline Check", "status": "success"})
        scope_warning = verify_pr_scope()
        if scope_warning: results["steps"].append({"name": "PR Scope Check", "status": "warning", "message": scope_warning})
        conflicts = self.detect_conflicts()
        results["conflicts"] = [{"prs": list(p), "files": f} for p, f in conflicts.items()]
        return results

    def repair_local(self, logs_path: Optional[str] = None, stdin: bool = False, worktree: bool = False) -> Dict[str, Any]:
        logs_content = ""
        if stdin: logs_content = sys.stdin.read()
        elif logs_path:
            if os.path.exists(logs_path):
                with open(logs_path, 'r') as f: logs_content = f.read()
            else: raise CLIError(f"Log file not found: {logs_path}")
        else:
            res_lint = run_command(["pnpm", "run", "lint:ox"], check=False)
            res_tsc = run_command(["pnpm", "run", "type-check"], check=False)
            logs_content = res_lint.stdout + res_lint.stderr + "\n" + res_tsc.stdout + res_tsc.stderr
        if not logs_content.strip(): return {"status": "success", "message": "No errors found."}
        original_cwd = os.getcwd(); repair_script = os.path.abspath(os.path.join(original_cwd, "dev-tools", "repair.py"))
        worktree_path = None; branch_name = None
        try:
            branch_name = f"repair/local-{datetime.now().strftime('%H%M%S')}"
            prefix = PROJECT_CONFIG.worktree_prefix
            # Create temporary worktree within repo root to avoid Security Error
            worktree_path = os.path.join(original_cwd, f"{prefix}{datetime.now().strftime('%H%M%S')}")
            os.makedirs(worktree_path, exist_ok=True)
            run_command(["git", "worktree", "add", "-b", branch_name, worktree_path, "HEAD"])
            os.chdir(worktree_path)
            if os.path.exists(os.path.join(original_cwd, "node_modules")):
                os.symlink(os.path.join(original_cwd, "node_modules"), os.path.join(worktree_path, "node_modules"))
            # Create temporary log file within repo root logs/
            log_dir = get_or_create_log_dir("repair")
            with tempfile.NamedTemporaryFile(mode='w', suffix=".log", delete=False, dir=log_dir) as tmp_log:
                tmp_log.write(logs_content); tmp_log_path = tmp_log.name
            cmd = [sys.executable, repair_script, tmp_log_path]
            proc = run_command(cmd, check=False)
            os.unlink(tmp_log_path)
            if proc.returncode == 0: return {"status": "success", "message": "Repair completed.", "worktree": worktree_path, "branch": branch_name}
            else: return {"status": "error", "message": f"Repair failed with code {proc.returncode}"}
        finally: os.chdir(original_cwd)

    def handle_audit_gate(self) -> Dict[str, Any]:
        current_count = int(run_command(["node", "scripts/detect-antipatterns.mjs", "--count-only"]) or 0)
        baseline_count = self.resolve_baseline(None, 'AUDIT_BASELINE', -1)

        is_shallow = run_command(["git", "rev-parse", "--is-shallow-repository"], check=False).stdout.strip() == "true"

        if baseline_count == -1 or is_shallow:
            val = self.get_env_or_gha('AUDIT_BASELINE')
            if val: return {"current": current_count, "baseline": int(val), "status": "success" if current_count <= int(val) else "error"}

            if is_shallow:
                 # In a shallow clone, git ls-tree/show on base branch will fail or be incomplete.
                 log_warn("Shallow repository detected and no AUDIT_BASELINE variable found. Falling back to 0.")
                 return {"current": current_count, "baseline": 0, "status": "success" if current_count <= 0 else "error"}

            baseline_count = 0
            # Robust base branch discovery: try config, then origin/main, then main
            base_candidates = [PROJECT_CONFIG.base_branch, "origin/main", "main"]
            base_ref = None
            for cand in base_candidates:
                if cand and run_command(["git", "rev-parse", "--verify", cand], check=False, log_on_error=False).returncode == 0:
                    base_ref = cand
                    break

            if not base_ref:
                log_warn("Could not determine base branch for audit baseline. Falling back to 0.")
                return {"current": current_count, "baseline": 0, "status": "success" if current_count <= 0 else "error"}

            base_files = run_command(["git", "ls-tree", "-r", base_ref, "--name-only"]).splitlines()
            # Ensure AUDIT_CHECK_DIRS are handled as a list of prefixes
            relevant = [mf for mf in base_files if (mf.endswith('.tsx') or mf.endswith('.ts')) and any(mf == d or mf.startswith(d + '/') for d in AUDIT_CHECK_DIRS)]
            for mf in relevant:
                res_show = run_command(["git", "show", f"{base_ref}:{mf}"], check=False, log_on_error=False)
                if res_show.returncode == 0:
                    baseline_count += int(run_command(["node", "scripts/detect-antipatterns.mjs", "--count-only", "-"], input_str=res_show.stdout) or 0)
        return {"current": current_count, "baseline": baseline_count, "status": "success" if current_count <= baseline_count else "error"}

    def fix_ci(self, pr_number: Optional[int] = None, branch: Optional[str] = None, api_key: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
        repo_name = get_repo_name(); g = get_github_client(); repo = g.get_repo(repo_name)
        if pr_number:
            pr = repo.get_pull(int(pr_number))
            branch = pr.head.ref
        elif branch: pulls = list(repo.get_pulls(state='open', head=f"{repo.owner.login}:{branch}")); pr = pulls[0] if pulls else None
        else:
            branch = run_command(['git', 'branch', '--show-current']).strip()
            pulls = list(repo.get_pulls(state='open', head=f"{repo.owner.login}:{branch}")); pr = pulls[0] if pulls else None

        if not pr:
            raise CLIError(f"Could not find PR for branch {branch}")

        if api_key: self.jules.api_key = api_key

        # Analyze failing check runs
        check_runs = self.github.fetch_check_runs(pr.head.sha)
        failing_logs = []
        structured_failures = []
        for run in check_runs:
            if run.get('conclusion') == 'failure':
                logs = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))

                # Clean logs and take a smart snippet
                cleaned_logs = clean_gha_logs(logs)

                # Prioritize lines with error signatures
                important_lines = []
                for line in cleaned_logs.splitlines():
                    if any(x in line.lower() for x in ['error', 'fail', 'ts', 'vitest', 'playwright', '🔴']):
                        important_lines.append(line)

                if important_lines:
                    snippet = "\n".join(important_lines[-30:]) # Keep last 30 important lines
                else:
                    snippet = cleaned_logs[-2000:] # Fallback to tail of cleaned logs

                failing_logs.append(f"Check Run: {run.get('name')}\nLogs:\n{snippet}")

                findings = extract_failing_info(logs)
                for f in findings:
                    structured_failures.append(f"File: {f['file']}, Line: {f['line']}, Error: {f['message']} ({f['type']})")

        base_branch = PROJECT_CONFIG.base_branch
        base_branch_name = PROJECT_CONFIG.base_branch_name

        prompt = f"""# Agent Prompt: Self-Review, Fix, and Publish PR

You are a senior engineering agent reviewing your own branch before publishing.

Compare the current branch against `{base_branch_name}`, identify issues, fix them directly, validate the result, and open or update a pull request. Do not stop after giving recommendations.

## Rules

- Do not ask for confirmation before making fixes.
- Do not ask the user to run commands.
- Do not stop until you have opened or updated a PR.
- Do not make unrelated refactors.
- Do not publish with known failing checks unless the failure is clearly unrelated and documented.
- If local setup prevents a check from running, document the attempted command, the setup gap, and the follow-up needed.

## Steps

1. Check branch state with `git status`, `git branch --show-current`, `git remote -v`, and `git fetch origin {base_branch_name}`.
2. Review the full diff with `git diff {base_branch}...HEAD`, `git diff --stat {base_branch}...HEAD`, `git log --oneline {base_branch}..HEAD`, and `git diff --cached`.
3. Create a checklist covering correctness, edge cases, TypeScript/imports, dead code, UI/mobile behavior, accessibility, validation, repo hygiene, and PR description quality.
4. Fix the issues directly.
5. Validate using the repo scripts from `package.json`, such as lint, typecheck, test, and build.
   - For CI remediation, favor targeted testing (e.g., `pnpm run test:e2e:targeted -- <args>`) and represent failures using the structured schema described in `docs/agent/ci-remediation.md`.
6. If validation fails, fix the root cause and rerun the failing check. If the environment blocks a check, document the exact command and reason.
7. Final review with `git status`, `git diff {base_branch}...HEAD`, `git diff --stat {base_branch}...HEAD`, and a search for TODO/FIXME/debug leftovers.
8. Commit, push, and create or update the PR with a clear summary and validation notes.

## Final response

Respond only after the PR is created or updated:

- PR link
- Changes made
- Self-review fixes
- Validation results
- Notes or documented limitations"""

        if structured_failures:
            prompt += "\n\n## CI Failure Analysis\n\nStructured Failure Analysis:\n- " + "\n- ".join(structured_failures)

        if failing_logs:
            prompt += "\n\nDetailed Failing Logs (Snippets):\n" + "\n---\n".join(failing_logs)

        agent_name = "Jules"
        source_id = self.get_env_or_gha("JULES_SOURCE_ID") or self.jules.discover_source_id(repo_name)
        if not source_id: raise CLIError("JULES_SOURCE_ID missing and auto-discovery failed.")
        session_name = "dry-run-session"
        if not dry_run:
            res = self.jules.create_session_from_source(source_id, branch, prompt)
            if res: session_name = res.get("name")
            else: raise CLIError(f"{agent_name} API session creation failed")
        feedback = f"🤖 **{agent_name} is on it!**\n\nInitialized autonomous repair session (`{session_name}`) for branch `{branch}`."
        if pr and not dry_run: pr.create_issue_comment(feedback)
        return {"session": session_name, "branch": branch, "feedback": feedback, "agent_name": agent_name}

    def manage_reviews(self, check_responses: bool = False, cleanup_comments: bool = False, dry_run: bool = True, limit: int = 10) -> List[Dict[str, Any]]:
        g = get_github_client(); repo = g.get_repo(get_repo_name()); login = g.get_user().login; prs_data = []
        # PyGithub get_pulls handles per_page internally. Directly slice the paginated list.
        for pr in repo.get_pulls(state='open', sort='updated', direction='desc')[:limit]:
            last_review = next((r for r in pr.get_reviews().reversed if r.user.login == login), None)
            status = "ACTION: Needs Review" if not last_review else f"ACTION: Needs Re-Review" if last_review.commit_id != pr.head.sha else "STATE: Up-To-Date"
            item = {"number": pr.number, "title": pr.title, "status": status, "unaddressed": []}
            if check_responses:
                our_coms = [c for c in pr.get_review_comments() if c.user.login == login]
                after_coms = [c for c in pr.get_review_comments() if c.user.login != login and any(c.in_reply_to_id == oc.id for oc in our_coms)]
                if our_coms and not after_coms: item["unaddressed"] = [f"{c.path}:{c.position}" for c in our_coms]
            if cleanup_comments:
                for c in pr.get_issue_comments():
                    if c.user.login == login and "<!-- td-review-manager-comment -->" in c.body:
                        if not dry_run: c.delete()
            prs_data.append(item)
        return prs_data

    def track_review(self, pr_num: int, status: str, auditor: str, dry_run: bool = True) -> Dict[str, Any]:
        tracking_file = "REVIEW_TRACKING.md"; now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        content = open(tracking_file).read() if os.path.exists(tracking_file) else "# PR Review Tracking\n\n| PR | Status | Auditor | Last Updated |\n|----|--------|---------|--------------|\n"
        lines = content.splitlines(); new_lines = []; found = False
        for line in lines:
            if line.startswith("|") and f"| #{pr_num} |" in line:
                new_lines.append(f"| #{pr_num} | {status} | {auditor} | {now} |"); found = True
            else: new_lines.append(line)
        if not found: new_lines.append(f"| #{pr_num} | {status} | {auditor} | {now} |")
        if not dry_run:
            with open(tracking_file, "w") as f: f.write("\n".join(new_lines) + "\n")
        return {"pr": pr_num, "status": status, "updated": not dry_run}

    def resolve_conflicts_headless(self) -> List[str]:
        files = self.find_conflict_files(); resolved, failed = [], []
        for f in files:
            if self.resolve_conflict(f): resolved.append(f)
            else: failed.append(f)
        if failed: raise CLIError(f"Failed to resolve: {', '.join(failed)}")
        return resolved

    def repair_context(self, log: Optional[str] = None, log_file: Optional[str] = None, pr_number: Optional[int] = None) -> List[str]:
        from dev_tools.services.repair_service import RepairService
        pipeline = RepairService()
        prompts = []
        if log: prompts.append(pipeline.generate_prompt(log))
        elif log_file:
            with open(log_file) as f:
                for line in f:
                    p = pipeline.generate_prompt(line)
                    if p: prompts.append(p)
        elif pr_number:
            repo_name = get_repo_name()
            g = get_github_client()
            repo = g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            check_runs = self.github.fetch_check_runs(pr.head.sha)
            for run in check_runs:
                if run.get('conclusion') == 'failure':
                    logs = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))
                    for line in logs.splitlines():
                        p = pipeline.generate_prompt(line)
                        if p: prompts.append(p)
        return prompts

    def run_ux_audit(self, route: Optional[str] = None, all_routes: bool = False, desktop: bool = False, mobile: bool = False, screenshots_only: bool = False, images_only: bool = False, contrast_only: bool = False, overflow_only: bool = False) -> Dict[str, Any]:
        """
        Runs the UX audit suite using Playwright.
        """
        # Ensure routes are discovered
        run_command(["pnpm", "exec", "tsx", "scripts/ux-discover-routes.ts"])

        routes = ["/"]
        if all_routes:
            with open("artifacts/ux-audit/routes.json", "r") as f:
                routes = json.load(f)["routes"]
        elif route:
            routes = [route]

        viewports = []
        if desktop: viewports = ["desktop-1280", "desktop-1440"]
        elif mobile: viewports = ["mobile-375", "mobile-390", "mobile-430"]

        flags = []
        if images_only: flags.append("--images-only")
        if overflow_only: flags.append("--overflow-only")
        if contrast_only: flags.append("--contrast-only")

        results = []
        for r in routes:
            cmd = ["pnpm", "exec", "tsx", "scripts/ux-audit-runner.ts", r]
            if viewports:
                for vp in viewports:
                    res = run_command(cmd + [vp] + flags, check=False)
                    results.append({"route": r, "viewport": vp, "status": "success" if res.returncode == 0 else "error"})
            else:
                res = run_command(cmd + flags, check=False)
                results.append({"route": r, "status": "success" if res.returncode == 0 else "error"})

        return {"status": "success", "results": results}

    def run_lighthouse(self, route: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs Lighthouse audits.
        """
        # Ensure routes are discovered
        run_command(["pnpm", "exec", "tsx", "scripts/ux-discover-routes.ts"])

        cmd = ["pnpm", "exec", "tsx", "scripts/ux-lighthouse-runner.ts"]
        if route:
            # Note: Lighthouse runner might need updates to handle single route arg if desired,
            # but for now it uses routes.json.
            pass

        res = run_command(cmd, check=False)
        return {"status": "success" if res.returncode == 0 else "error", "output": res.stdout}

    def generate_ux_report(self) -> Dict[str, Any]:
        """
        Aggregates results into a Markdown report.
        """
        generate_report()
        return {"status": "success", "report": "artifacts/ux-audit/ux-audit-report.md"}

    def _scan_workflows(self) -> List[str]:
        """Lists all YAML files in .github/workflows/."""
        workflow_dir = ".github/workflows"
        if not os.path.exists(workflow_dir):
            return []
        files = []
        for f in os.listdir(workflow_dir):
            if f.endswith(".yml") or f.endswith(".yaml"):
                files.append(os.path.join(workflow_dir, f))
        return sorted(files)

    def _check_workflow_compliance(self, file_path: str) -> List[str]:
        """Parses a workflow file for compliance violations using a data-driven rule model."""
        violations = []

        # Rule definition model: dictionaries with regex, message, and optional validator.
        # Regexes are designed to be robust against varying whitespace and formatting.
        rules = [
            {
                "regex": r"node-version\s*:\s*['\"]?\d+",
                "message": "Hardcoded `node-version:`. Use `node-version-file: '.node-version'` instead."
            },
            {
                "regex": r"\bnpm\s+(?:install|ci|run)\b",
                "message": "`npm` usage detected. Use `pnpm` exclusively."
            },
            {
                "regex": r"actions/checkout\s*@\s*v(\d+)",
                "message": "Outdated `actions/checkout@v{ver}`. Use `@v4`.",
                "validator": lambda m: int(m.group(1)) < 4
            },
            {
                "regex": r"actions/setup-node\s*@\s*v(\d+)",
                "message": "Outdated `actions/setup-node@v{ver}`. Use `@v4`.",
                "validator": lambda m: int(m.group(1)) < 4
            }
        ]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            for rule in rules:
                # Use re.IGNORECASE for robustness against mixed casing in YAML
                pattern = re.compile(rule["regex"], re.IGNORECASE)
                for match in pattern.finditer(content):
                    validator = rule.get("validator")
                    if validator is None or validator(match):
                        # Support dynamic version reporting if the regex has a group
                        ver = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                        violations.append(rule["message"].format(ver=ver))

        except Exception as e:
            violations.append(f"Error parsing file: {e}")

        return violations

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

            if not workflow_path.startswith(".github/workflows" + os.sep) and workflow_path != os.path.join(".github", "workflows", os.path.basename(workflow_path)):
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
                "status_file": "workflow-audit-status.md"
            }

        # 1. Cache compliance checks to avoid redundant processing
        file_audit_results = {}
        for f_path in files:
            file_audit_results[f_path] = self._check_workflow_compliance(f_path)

        # 2. Summary Checklist Generation (workflow-audit-status.md)
        status_path = "workflow-audit-status.md"
        status_lines = [
            "# Workflow Audit Status",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "\n## Compliance Checklist\n"
        ]

        for f_path in files:
            name = os.path.basename(f_path)
            violations = file_audit_results[f_path]
            status = "✅" if not violations else "❌"
            status_lines.append(f"- [ ] {status} `{name}`: {len(violations)} violation(s)")

        with open(status_path, "w", encoding="utf-8") as f:
            f.write("\n".join(status_lines) + "\n")

        # 3. Individual Workflow Plan Generation
        plan_dir = get_or_create_log_dir("workflows")
        generated_plans = []

        for f_path in files:
            name = os.path.basename(f_path)
            plan_path = os.path.join(plan_dir, f"workflow-plan-{name}.md")
            violations = file_audit_results[f_path]

            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(f"""# Workflow Audit Plan: {name}

## File Path
`{f_path}`

## Compliance Status
{"✅ All rules followed." if not violations else "❌ Non-compliant patterns found."}

### Violations
{"" if not violations else "\n".join(f"- {v}" for v in violations)}

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
            "workflow_plans": generated_plans
        }

    def plan_issue_audit(self, issue_numbers: Optional[List[int]] = None, all_open: bool = False, limit: int = 100) -> Dict[str, Any]:
        """
        Builds a deterministic roadmap and status checklist for auditing open issues.
        """
        issues = []
        if all_open:
            issues = self.github.list_issues(state='open', limit=limit)
        elif issue_numbers:
            for num in issue_numbers:
                issue = self.github.fetch_issue_details(num)
                # Normalize format to match list_issues
                issues.append({
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "body": issue.get("body"),
                    "state": issue.get("state"),
                    "html_url": issue.get("html_url"),
                    "labels": [l.get('name') if isinstance(l, dict) else l for l in issue.get('labels', [])],
                    "updated_at": issue.get("updated_at")
                })
        else:
            raise CLIError("Provide --issue or --all-open")

        # 1. Summary Checklist Generation (issue-audit-status.md)
        status_path = "issue-audit-status.md"
        status_lines = [
            "# Issue Audit Status",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "\n## Open Issues Checklist\n"
        ]
        for issue in issues:
            status_lines.append(f"- [ ] #{issue['number']}: {issue['title']}")

        with open(status_path, "w") as f:
            f.write("\n".join(status_lines) + "\n")

        # 2. Individual Workflow Plan Generation
        plan_dir = get_or_create_log_dir("workflows")
        generated_plans = []

        for issue in issues:
            plan_path = os.path.join(plan_dir, f"workflow-plan-issue-{issue['number']}.md")

            with open(plan_path, "w") as f:
                f.write(f"""# Workflow Plan: Issue #{issue['number']}

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
            "workflow_plans": generated_plans
        }

    def run_playwright(self, grep: Optional[str] = None, worktree_path: Optional[str] = None) -> Dict[str, Any]:
        """Runs Playwright tests and parses the JSON report."""
        playwright_args = ["playwright", "test", "--reporter=json"]
        if grep:
            playwright_args.extend(["--grep", grep])

        res = run_command(["pnpm"] + playwright_args, cwd=worktree_path, check=False)

        failed_tests = []
        try:
            if "{" in res.stdout:
                json_data = res.stdout[res.stdout.find("{"):]
                try:
                    report = json.loads(json_data)
                    for suite in report.get("suites", []):
                        for spec in suite.get("specs", []):
                            if not spec.get("ok"):
                                error = "Unknown error"
                                if spec.get("tests") and spec["tests"][0].get("results") and spec["tests"][0]["results"][0].get("error"):
                                    error = spec["tests"][0]["results"][0]["error"].get("message", "Unknown error")

                                failed_tests.append({
                                    "title": spec.get("title"),
                                    "file": spec.get("file"),
                                    "error": error
                                })
                except json.JSONDecodeError as e:
                    log_error(f"Failed to parse Playwright JSON report: {e}\nRaw output: {res.stdout}")
        except Exception as e:
            log_error(f"Unexpected error parsing Playwright output: {e}")

        return {
            "success": res.returncode == 0,
            "command": " ".join(["pnpm"] + playwright_args),
            "failedTests": failed_tests
        }
    def get_ci_logs(self, pr_number: int, include_all: bool = False) -> Dict[str, Any]:
        """Fetches CI logs for failing (or all) check runs in a PR."""
        # Get PR head SHA
        pr_data = self.github.fetch_pr_details(pr_number)
        head_sha = pr_data.get("head", {}).get("sha")

        if not head_sha:
            raise CLIError(f"Could not determine head SHA for PR #{pr_number}")

        # Get check runs
        checks = self.github.fetch_check_runs(head_sha)
        failed_checks = [c for c in checks if c.get("conclusion") == "failure"]

        logs = {}
        # Get check suites to find workflow runs
        check_suites = self.github.fetch_check_suites(head_sha)

        for suite in check_suites:
            runs = self.github.fetch_check_runs_for_suite(suite['id'])
            for run in runs:
                if include_all or run.get("conclusion") == "failure":
                    log_content = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))
                    logs[run["name"]] = log_content[:10000]

        return {
            "checks": checks,
            "failedChecks": failed_checks,
            "logs": logs
        }

    def stream_ci_logs(self, pr_number: int, grep: Optional[str] = None) -> str:
        """Fetches and combines all CI logs for the latest workflow run of a PR."""
        # Get PR head SHA
        pr_data = self.github.fetch_pr_details(pr_number)
        head_sha = pr_data.get("head", {}).get("sha")

        if not head_sha:
            raise CLIError(f"Could not determine head SHA for PR #{pr_number}")

        # Get all check runs for this SHA
        check_runs = self.github.fetch_check_runs(head_sha)

        all_logs = []
        # Limit to latest 20 jobs to avoid extreme memory usage
        for run in check_runs[:20]:
            # Fetch logs via API to avoid terminal paging/buffering issues
            log_content = self.github.fetch_check_run_logs(run.get('id'), external_id=run.get('external_id'))
            header = f"--- LOGS FOR JOB: {run['name']} (ID: {run['id']}) ---"
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

    def get_merge_conflicts(self, pr_number: int, base_branch: str = None) -> Dict[str, Any]:
        """Detects merge conflicts for a PR against a base branch using a temporary worktree."""
        if base_branch is None:
            base_branch = PROJECT_CONFIG.base_branch_name
        # Get PR head ref
        pr_data = self.github.fetch_pr_details(pr_number)
        head_ref = pr_data.get("head", {}).get("ref")

        if not head_ref:
            raise CLIError(f"Could not determine head ref for PR #{pr_number}")

        # Ensure we have the latest
        run_command(["git", "fetch", "origin", head_ref])
        run_command(["git", "fetch", "origin", base_branch])

        worktree_path = os.path.join(os.getcwd(), f"worktree-conflict-{pr_number}.tmp")
        self._cleanup_worktree(worktree_path)

        run_command(["git", "worktree", "add", worktree_path, f"origin/{head_ref}"])

        conflict_files = []
        command_log = ""
        try:
            res = run_command(
                ["git", "merge", "--no-commit", "--no-ff", f"origin/{base_branch}"],
                cwd=worktree_path,
                check=False
            )
            command_log = res.stdout + res.stderr

            if res.returncode != 0:
                res_diff = run_command(
                    ["git", "diff", "--name-only", "--diff-filter=U"],
                    cwd=worktree_path,
                    check=False
                )
                conflict_files = [f.strip() for f in res_diff.stdout.splitlines() if f.strip()]
                run_command(["git", "merge", "--abort"], cwd=worktree_path, check=False)
        finally:
            run_command(["git", "worktree", "remove", "-f", worktree_path], check=False)
            if os.path.exists(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)

        return {
            "prNumber": pr_number,
            "baseBranch": base_branch,
            "headRef": head_ref,
            "conflictFiles": conflict_files,
            "commandLog": command_log
        }

    def get_pr_diff_shapen(self, pr_number: int) -> Dict[str, Any]:
        """Fetches PR diff, applies truncation and shapes file info."""
        # Get files list
        files = self.github.fetch_pr_files(pr_number)

        # Get diff text
        diff_text = self.github.fetch_pr_diff(pr_number)

        MAX_DIFF_SIZE = 50000
        truncated = False
        if len(diff_text) > MAX_DIFF_SIZE:
            diff_text = diff_text[:MAX_DIFF_SIZE] + "\n\n... [Diff truncated due to size] ..."
            truncated = True

        return {
            "prNumber": pr_number,
            "files": [
                {
                    "path": f.get("filename"),
                    "status": f.get("status") or "modified",
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions")
                } for f in files
            ],
            "diffText": diff_text,
            "truncated": truncated
        }

    def list_prs(self, state: str = "open", limit: int = 100, include_drafts: bool = True, labels: Optional[List[str]] = None) -> Dict[str, Any]:
        """Lists PRs with optional filtering."""
        prs = self.github.list_pull_requests(state=state, limit=limit, labels=labels)

        if not include_drafts:
            prs = [pr for pr in prs if not pr.get("isDraft")]

        return {
            "status": "success",
            "prs": [PRSummary(**pr).model_dump() for pr in prs]
        }

    def get_pr_comments(self, pr_number: int) -> Dict[str, Any]:
        """Fetches and aggregates standard issue comments and inline review comments for a PR."""
        pr = self.github.fetch_pr_details(pr_number)
        issue_comments = self.github.fetch_issue_comments(pr_number)
        review_comments = self.github.fetch_review_comments(pr_number)

        return {
            "pr": {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "html_url": pr.get("html_url")
            },
            "comments": [
                {
                    "user": c.get("user", {}).get("login"),
                    "body": c.get("body"),
                    "created_at": c.get("created_at")
                } for c in issue_comments
            ],
            "review_comments": [
                {
                    "user": c.get("user", {}).get("login"),
                    "path": c.get("path"),
                    "line": c.get("line"),
                    "body": c.get("body"),
                    "created_at": c.get("created_at")
                } for c in review_comments
            ]
        }

    def trigger_jules_feedback(self, session_id: str) -> Dict[str, Any]:
        """Ports logic from trigger-feedback.ts to provide CI feedback to Jules."""
        session = self.jules.get_session(session_id)
        if not session:
             raise CLIError(f"Session {session_id} not found.")

        pr_number = None
        # Try to find PR in session outputs
        if session.get("outputs") and isinstance(session["outputs"], list):
            for output in session["outputs"]:
                if output.get("pullRequest") and output["pullRequest"].get("url"):
                    match = re.search(r"/pull/(\d+)", output["pullRequest"]["url"])
                    if match:
                        pr_number = int(match.group(1))
                        break

        # Search via gh for PRs mentioning session ID if not found
        if not pr_number:
            prs = self.github.list_pull_requests(state='open')
            clean_id = session_id.replace("sessions/", "")
            for pr in prs:
                # Need full details for body
                full_pr = self.github.fetch_pr_details(pr['number'])
                if clean_id in (full_pr.get('title') or "") or clean_id in (full_pr.get('body') or ""):
                    pr_number = pr['number']
                    break

        if not pr_number:
            return {
                "status": "no_pr_found",
                "message": "Could not associate session with an open PR."
            }

        pr_details = self.github.fetch_pr_details(pr_number)
        sha = pr_details.get("head", {}).get("sha")
        check_runs = self.github.fetch_check_runs(sha)

        if not check_runs:
            return {"status": "no_checks", "message": "No CI checks found for this PR head."}

        failed_checks = [run for run in check_runs if run.get("status") == "completed" and run.get("conclusion") == "failure"]
        in_progress = any(run.get("status") != "completed" for run in check_runs)

        if in_progress:
            return {"status": "in_progress", "message": "CI checks are still in progress."}

        feedback = ""
        if failed_checks:
            feedback = "The CI pipeline reported failures. Here are the details:\n\n"
            for run in failed_checks:
                feedback += f"### Failed Check: {run['name']}\n"
                logs = self.github.fetch_check_run_logs(run['id'], external_id=run.get('external_id'))
                findings = extract_failing_info(logs)
                if findings:
                    for f in findings:
                        feedback += f"- File: `{f['file']}:{f['line']}` ({f['type']})\n  Message: {f['message']}\n"
                else:
                    # Clean logs and take a smart snippet as fallback
                    cleaned_logs = clean_gha_logs(logs)
                    feedback += f"```\n{cleaned_logs[-2000:]}\n```\n"
                feedback += "\n"
        else:
            feedback = "All checks passed successfully. You may proceed."

        self.jules.send_message(session_id, feedback)
        return {"status": "success", "feedback": feedback}

    def aggregate_prs(self, target_branch: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """
        Aggregates multiple PRs into a single target branch and creates a consolidated PR.
        """
        def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
            return run_command(cmd, check=check)

        base_branch = PROJECT_CONFIG.base_branch_name

        # 1. Isolation & Cleanliness
        run(["git", "checkout", base_branch])
        run(["git", "pull", "origin", base_branch])
        run(["git", "checkout", "-b", target_branch])

        aggregate_body = ""
        successfully_merged = []

        for pr_num in pr_numbers:
            # 2. Sequential Extraction & Deterministic Sequence
            pr_data = self.github.fetch_pr_details(pr_num)
            head_ref = pr_data.get('head', {}).get('ref')
            title = pr_data.get('title')
            body = pr_data.get('body') or ""

            if not head_ref:
                raise CLIError(f"Could not determine head ref for PR #{pr_num}")

            # 2.5 Handle forks by using git fetch
            # This ensures the branch is available locally and handles forks correctly
            run(["git", "fetch", "origin", f"pull/{pr_num}/head:{head_ref}"])

            # Switch back to the target branch
            run(["git", "checkout", target_branch])

            # 3. Safety First: Attempt automated integration merge
            # Use 'ort' strategy implicitly by standard merge if git version supports it,
            # or just standard merge.
            res = run_command(["git", "merge", head_ref, "-m", f"Merging PR #{pr_num}: {title}"], check=False)

            if res.returncode != 0:
                # Conflict encountered
                run(["git", "merge", "--abort"])
                raise CLIError(f"CRITICAL: Conflict in PR #{pr_num}. Restored stable state of {target_branch}.", code=res.returncode)

            # 4. Metadata Preservation
            successfully_merged.append(pr_num)
            aggregate_body += f"Closes #{pr_num}\n\n### Description from PR #{pr_num} ({title}):\n{body}\n\n---\n"

        # Push the compiled branch
        run(["git", "push", "-u", "origin", target_branch])

        # Create consolidated PR
        pr_title = f"Aggregated Feature: {target_branch}"
        pr_res = self.github.create_pull_request(pr_title, aggregate_body, target_branch, base_branch)
        pr_url = pr_res.get("html_url")

        return {
            "status": "success",
            "branch": target_branch,
            "merged_prs": successfully_merged,
            "pr_url": pr_url,
            "message": f"Successfully aggregated {len(successfully_merged)} PRs into {target_branch}"
        }

    def generate_review_workflow(self, pr_number: int, issue_number: Optional[int] = None) -> Dict[str, Any]:
        """Generates a deterministic review workflow plan for an agent."""
        # 1. Environment Validation
        env_res = self.runtime_check()
        env_output = f"Runtime OK: node {env_res['node']}, pnpm {env_res['pnpm']}"

        # 2. Issue Validation
        issue_output = "No issue number provided."
        if issue_number:
            res = self.validate_issue(issue_number=issue_number)
            issue_output = json.dumps(res, indent=2)

        # 3. Conflict Detection
        conflicts = self.handle_detect_conflicts(pr_num=pr_number)
        conflict_output = json.dumps(conflicts, indent=2)

        # 4. PR Context Generation
        audit_res = self.audit_pr(pr_number, fetch=True)
        pr_context_file = audit_res["files"]["context"]

        pr_summary = ""
        ci_status = ""
        failure_logs = ""

        if os.path.exists(pr_context_file):
            with open(pr_context_file, "r") as f:
                pr_context_content = f.read()

            summary_match = re.search(r'(# PR Context:.*?)(?=## CI Status|## Diff Stats)', pr_context_content, re.DOTALL)
            if summary_match: pr_summary = summary_match.group(1).strip()

            ci_status_match = re.search(r'(## CI Status.*?)(?=## Diff Stats|## Failing Tests)', pr_context_content, re.DOTALL)
            if ci_status_match: ci_status = ci_status_match.group(1).strip()

            failure_logs_match = re.search(r'(## Failing Tests.*?)(?=## Diff Stats|$)', pr_context_content, re.DOTALL)
            if failure_logs_match: failure_logs = failure_logs_match.group(1).strip()

            if not pr_summary: pr_summary = "See " + pr_context_file
            if not ci_status: ci_status = "See " + pr_context_file
            if not failure_logs: failure_logs = "See " + pr_context_file

        # 5. Impact Analysis
        impact_output = "Not available."
        if os.path.exists("scripts/impact-analysis.ts"):
            res = run_command(["npx", "tsx", "scripts/impact-analysis.ts"], check=False)
            impact_output = res.stdout + res.stderr

        # 6. Existing Review Data
        gemini_review = "None."
        if os.path.exists("artifacts/gemini-code-review.md"):
            with open("artifacts/gemini-code-review.md", "r") as f: gemini_review = f.read()

        github_models_review = "None."
        if os.path.exists("artifacts/github-models-code-review.md"):
            with open("artifacts/github-models-code-review.md", "r") as f: github_models_review = f.read()

        # Generate workflow plan
        plan_dir = get_or_create_log_dir("workflows")
        plan_path = os.path.join(plan_dir, f"workflow-plan-pr-{pr_number}.md")

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
td gh audit-pr {pr_number} --submit --cleanup --execute
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
        repo = get_github_client().get_repo(get_repo_name())
        pulls = list(repo.get_pulls(state='open'))[:50]

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
        for pr_set, files in sorted(overlap_groups.items(), key=lambda x: len(x[1]), reverse=True):
            pr_list = sorted(list(pr_set), key=int)
            report.append(f"PRs {', '.join(pr_list)} overlap on {len(files)} files:")
            for pr_num in pr_list:
                report.append(f"  [{pr_num}] {pr_titles.get(pr_num)}")

        prs_output = "\n".join(report)

        # Generate workflow plan
        plan_dir = get_or_create_log_dir("workflows")
        plan_path = os.path.join(plan_dir, "workflow-plan-aggregate-prs.md")

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

    def resolve_pr_conflicts(self, pr_number: int, allow_unrelated: bool = False, strategy: Optional[str] = None, push: bool = False) -> Dict[str, Any]:
        """
        Sets up a worktree for a specific PR and attempts to merge the base branch.
        """
        original_cwd = os.getcwd()
        # Use a path that is clearly temporary and matches existing patterns for ignored files
        worktree_path = os.path.join(original_cwd, f"worktree-pr-{pr_number}.tmp")
        changed_dir = False

        try:
            # 1. Fetch PR details early to fail fast
            pr_data = self.github.fetch_pr_details(pr_number)
            default_base = PROJECT_CONFIG.base_branch_name
            base_branch = pr_data.get('base', {}).get('ref', default_base)
            head_ref = pr_data.get('head', {}).get('ref')

            if not head_ref:
                raise CLIError(f"Could not determine head ref for PR #{pr_number}")

            # 2. Clean up existing worktree if present
            self._cleanup_worktree(worktree_path)

            # 3. Fetch PR branch and create worktree directly on it
            run_command(["git", "fetch", "origin", f"+pull/{pr_number}/head:{head_ref}"], check=True)
            run_command(["git", "worktree", "add", worktree_path, head_ref], check=True)

            # 4. Switch to worktree and perform git operations
            changed_dir = True
            os.chdir(worktree_path)

            # Ensure origin/base_branch is up-to-date
            run_command(["git", "fetch", "origin", base_branch], check=True)

            # Attempt merge from base branch.
            merge_cmd = ["git", "merge", f"origin/{base_branch}", "-m", f"Merge {base_branch} into PR #{pr_number}"]
            if allow_unrelated:
                merge_cmd.append("--allow-unrelated-histories")
            if strategy in ["ours", "theirs"]:
                merge_cmd.extend(["-X", strategy])

            res = run_command(merge_cmd, check=False)
            if not isinstance(res, subprocess.CompletedProcess):
                raise CLIError("Failed to execute git merge command")

            if res.returncode == 0:
                message = f"✅ PR #{pr_number} merged successfully with {base_branch}.\nPath: {worktree_path}"
                status = "success"
                if push:
                    head_branch = pr_data.get('head', {}).get('ref')
                    if not head_branch:
                        raise CLIError(f"Cannot push: head branch is missing for PR #{pr_number}")
                    try:
                        # Use authenticated URL if token is available to avoid terminal prompts
                        if self.github.token and self.github.repo:
                            auth_url = f"https://x-access-token:{self.github.token}@github.com/{self.github.repo}.git"
                            run_command(["git", "push", auth_url, f"HEAD:{head_branch}"], check=True)
                        else:
                            run_command(["git", "push", "origin", head_branch], check=True)
                        message += f"\n🚀 Successfully pushed resolution to {head_branch}"
                    except Exception as push_err:
                        message += f"\n⚠️  Merge successful but push failed: {str(push_err)}"
                        status = "partial_success"
            else:
                message = f"⚠️  Conflicts detected in PR #{pr_number} when merging {base_branch}.\nAction Required: Resolve them manually in the worktree.\nCommand: cd {worktree_path}"
                status = "conflict"

            return {
                "status": status,
                "message": message,
                "worktree_path": worktree_path,
                "pr_number": pr_number,
                "base_branch": base_branch,
                "head_branch": head_ref
            }
        except CLIError:
            raise
        finally:
            if changed_dir:
                os.chdir(original_cwd)

    def generate_aggregation_workflow(self, pr_numbers: List[int], target_branch: str) -> Dict[str, Any]:
        """Generates a deterministic aggregation workflow plan for an agent."""
        # 1. Environment Validation
        env_res = self.runtime_check()
        env_output = f"Runtime OK: node {env_res['node']}, pnpm {env_res['pnpm']}"

        # 2. Fetch PR Metadata and Overlaps
        pr_details = {}
        file_to_prs: Dict[str, set[int]] = defaultdict(set)
        pr_hunks = {}

        for pr_num in pr_numbers:
            details = self.github.fetch_pr_details(pr_num)
            pr_details[pr_num] = details
            files = self.github.fetch_pr_files(pr_num)
            diff = self.github.fetch_pr_diff(pr_num)
            pr_hunks[pr_num] = self._extract_diff_hunks(diff)

            # Explicitly cast to str to satisfy type checkers
            pr_files = {str(f.get("filename")) for f in files if f.get("filename")}
            for filename_str in pr_files:
                file_to_prs[filename_str].add(pr_num)

        overlapping_files: Dict[str, List[int]] = {f: sorted(list(prs)) for f, prs in file_to_prs.items() if len(prs) > 1}

        # 3. Detect Structural Conflicts (Line-level overlaps)
        conflicts: List[Dict[str, Any]] = []
        for filename, prs in overlapping_files.items():
            for i in range(len(prs)):
                for j in range(i + 1, len(prs)):
                    hunks1 = pr_hunks[prs[i]].get(filename, [])
                    hunks2 = pr_hunks[prs[j]].get(filename, [])
                    for s1, e1 in hunks1:
                        for s2, e2 in hunks2:
                            if max(s1, s2) <= min(e1, e2):
                                conflicts.append({
                                    "file": filename,
                                    "prs": [prs[i], prs[j]],
                                    "range": [max(s1, s2), min(e1, e2)]
                                })

        # 4. Generate Markdown Files
        # Strict sanitization: allow only alphanumeric, underscores, and hyphens
        sanitized_target = re.sub(r'[^a-zA-Z0-9_\-]', '-', target_branch)
        workflow_plan_path = os.path.join(get_or_create_log_dir("workflows"), f"workflow-plan-aggregation-{sanitized_target}.md")
        context_details_path = os.path.join(get_or_create_log_dir("reviews"), f"aggregation-context-{sanitized_target}.md")
        plan_skeleton_path = os.path.join(get_or_create_log_dir("reviews"), f"aggregation-plan-{sanitized_target}.md")

        # --- Helper for escaping markdown special characters ---
        def _escape_md(text):
            return str(text).replace("[", "\\[").replace("]", "\\]").replace("(", "\\(").replace(")", "\\)")

        # --- Workflow Plan Template ---
        with open(workflow_plan_path, "w") as f:
            f.write(f"""# Reviewing Aggregation Planning Guide: {_escape_md(target_branch)}

## Agent Instructions
- setup complete
- validation complete
- context collected
- overlaps identified

Agent must not repeat these steps.

---

## Workflow State
[x] Environment Validation
[x] PR Context Collection
[x] Overlap Identification
[ ] Conflict Resolution
[ ] Integration Verification
[ ] Final Aggregation

---

## Collected Context
### Validation Output
```text
{env_output}
```

### Overlap Summary
Found {len(overlapping_files)} overlapping files and {len(conflicts)} structural conflicts across {len(pr_numbers)} PRs.

---

## Remaining Tasks
### Step 1: Review Overlaps
Examine the files listed in `aggregation-context-{sanitized_target}.md`.

### Step 2: Resolve Conflicts
Perform the merge and resolve any structural or semantic conflicts.

### Step 3: Verify
Run the validation suite to ensure the aggregated branch is stable.
""")

        # --- Context Details Template ---
        with open(context_details_path, "w") as f:
            f.write(f"# Aggregation Context Details: {_escape_md(target_branch)}\n\n")
            f.write("## Targeted PRs\n")
            for pr_num in pr_numbers:
                details = pr_details.get(pr_num, {})
                title = _escape_md(details.get('title', ''))
                login = _escape_md(details.get('user', {}).get('login', ''))
                f.write(f"- **PR #{pr_num}**: {title} (@{login})\n")

            f.write("\n## Overlapping Files\n")
            if not overlapping_files:
                f.write("No overlapping files detected.\n")
            else:
                for filename, prs in sorted(overlapping_files.items()):
                    f.write(f"- `{filename}`: Changed in PRs {', '.join(f'#{p}' for p in prs)}\n")

            f.write("\n## Structural Conflicts (Line Overlaps)\n")
            if not conflicts:
                f.write("No direct line-level conflicts detected.\n")
            else:
                for c in conflicts:
                    c_file = str(c.get('file', 'unknown'))
                    c_prs = c.get('prs', [])
                    c_range = c.get('range', [0, 0])
                    if len(c_prs) >= 2 and len(c_range) >= 2:
                        f.write(f"- `{c_file}`: PR #{c_prs[0]} and PR #{c_prs[1]} overlap at lines {c_range[0]}-{c_range[1]}\n")

        # --- Plan Skeleton Template ---
        with open(plan_skeleton_path, "w") as f:
            f.write(f"""# Aggregation Plan Skeleton: {_escape_md(target_branch)}

## Integration Steps
1. **Prepare Base**: Checkout the latest base branch.
2. **Sequential Merge**: Merge each PR branch into the target branch.
3. **Manual Resolution**: For each overlapping file, ensure logical consistency.
4. **Validation**: Run `pnpm run ci:local` or equivalent.

## Completion Criteria
- All PRs successfully integrated.
- No merge markers remain in the codebase.
- All tests pass in the aggregated branch.
""")

        return {
            "status": "success",
            "plan_path": workflow_plan_path,
            "context_path": context_details_path,
            "skeleton_path": plan_skeleton_path
        }
