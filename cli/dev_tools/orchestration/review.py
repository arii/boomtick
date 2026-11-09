"""PR review heuristics and finding collection."""

import json
import os
import re
import subprocess
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from dev_tools.utils import log_warn
from dev_tools.orchestration.base import OrchestratorBase
import dev_tools.orchestrator


class ReviewMixin(OrchestratorBase):
    """PR review heuristics and finding collection."""

    # class="..." / className="..." attribute matcher (#1113). A bare
    # `flex` in a stylesheet (`display: flex`) is not Tailwind usage;
    # a `flex` token inside a class attribute is.
    _CLASS_ATTR_RE = re.compile(r"\bclass(?:Name)?\s*=\s*[\"'{`]([^\"'`}]*)")

    def _tailwind_evidence(self, diff: str) -> List[Tuple[str, str]]:
        """Grounded Tailwind usage evidence (#1113).

        Returns (file, added_line) pairs, limited to added (`+`) diff lines:
        a class attribute carrying a utility token, or a Tailwind
        config/dependency signal. Empty when the diff shows no real
        Tailwind usage, so plain-CSS repos never get the advisory.
        """
        cfg = dev_tools.orchestrator.get_config()
        evidence: List[Tuple[str, str]] = []
        path = ""
        for line in (diff or "").splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            added = line[1:]
            if any(
                sig in path or sig in added for sig in cfg.tailwind_config_indicators
            ):
                evidence.append((path, added.strip()))
                continue
            for classes in self._CLASS_ATTR_RE.findall(added):
                for token in classes.split():
                    if self._is_tailwind_token(token, cfg.tailwind_indicators):
                        evidence.append((path, added.strip()))
                        break
                else:
                    continue
                break
        return evidence

    @staticmethod
    def _is_tailwind_token(token: str, indicators: List[str]) -> bool:
        for ind in indicators:
            # Prefix/arbitrary-value indicators match inside a token
            # (`px-4`, `text-[12px]`); bare words match whole tokens only
            # so `flex` never matches inside an unrelated word.
            if ind.endswith("-") or "[" in ind:
                if ind in token:
                    return True
            elif token == ind:
                return True
        return False

    # Fixed-width signals that risk 390px-viewport overflow (#1116).
    _OVERFLOW_RE = re.compile(r"w-\[\d+(?:\.\d+)?px\]|min-w-\[|whitespace-nowrap")

    # Fixed sub-48px dimensions on a button line: below the minimum
    # touch target (#1116).
    _SMALL_PX_RE = re.compile(
        r"(?:h|w|min-h|min-w)-\[(\d+(?:\.\d+)?)px\]|"
        r"(?:height|width)\s*:\s*(\d+(?:\.\d+)?)px"
    )

    _BUTTON_RE = re.compile(r"<button\b|role=[\"']button[\"']")

    def _overflow_evidence(self, diff: str) -> List[Tuple[str, str]]:
        """(file, added_line) pairs with fixed-width overflow signals."""
        evidence: List[Tuple[str, str]] = []
        path = ""
        for line in (diff or "").splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            added = line[1:]
            if self._OVERFLOW_RE.search(added):
                evidence.append((path, added.strip()))
        return evidence

    def _touch_evidence(self, diff: str) -> List[Tuple[str, str]]:
        """(file, added_line) pairs with sub-48px button dimensions."""
        evidence: List[Tuple[str, str]] = []
        path = ""
        for line in (diff or "").splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            added = line[1:]
            if not self._BUTTON_RE.search(added):
                continue
            small = any(
                float(n) < 48
                for pair in self._SMALL_PX_RE.findall(added)
                for n in pair
                if n
            )
            if small:
                evidence.append((path, added.strip()))
        return evidence

    def collect_pr_findings(
        self, pr: Dict[str, Any], diff: str, checks: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Structured hunk-cited findings for a PR (#1113).

        Each finding names the rule, the file, and the added diff lines
        that triggered it — no fact without a cited hunk.
        """
        findings: List[Dict[str, Any]] = []
        for path, added in self._tailwind_evidence(diff or ""):
            existing = next(
                (
                    f
                    for f in findings
                    if f["rule"] == "tailwind-primitives" and f["file"] == path
                ),
                None,
            )
            if existing is None:
                existing = {
                    "rule": "tailwind-primitives",
                    "severity": "warning",
                    "file": path,
                    "evidence": [],
                    "message": "Raw Tailwind classes; prefer Stack/Box/Grid primitives with design tokens.",
                }
                findings.append(existing)
            if added not in existing["evidence"] and len(existing["evidence"]) < 5:
                existing["evidence"].append(added)
        fails = [
            c["name"]
            for c in (checks or {}).get("check_runs", [])
            if c.get("conclusion") == "failure"
        ]
        if fails:
            findings.append(
                {
                    "rule": "ci-failure",
                    "severity": "error",
                    "file": "",
                    "evidence": sorted(fails),
                    "message": f"Failing checks: {', '.join(sorted(fails))}.",
                }
            )
        for path, added in self._overflow_evidence(diff or ""):
            existing = next(
                (
                    f
                    for f in findings
                    if f["rule"] == "mobile-overflow" and f["file"] == path
                ),
                None,
            )
            if existing is None:
                existing = {
                    "rule": "mobile-overflow",
                    "severity": "warning",
                    "file": path,
                    "evidence": [],
                    "message": (
                        "Fixed-width "
                        "content risks "
                        "overflowing a "
                        "390px viewport; "
                        "prefer fluid "
                        "widths with "
                        "wrapping."
                    ),
                }
                findings.append(existing)
            if added not in existing["evidence"] and len(existing["evidence"]) < 5:
                existing["evidence"].append(added)
        for path, added in self._touch_evidence(diff or ""):
            existing = next(
                (
                    f
                    for f in findings
                    if f["rule"] == "touch-target" and f["file"] == path
                ),
                None,
            )
            if existing is None:
                existing = {
                    "rule": "touch-target",
                    "severity": "warning",
                    "file": path,
                    "evidence": [],
                    "message": "Interactive element below the 48x48px minimum touch target; enforce min-h/min-w 48px.",
                }
                findings.append(existing)
            if added not in existing["evidence"] and len(existing["evidence"]) < 5:
                existing["evidence"].append(added)
        if pr.get("mergeable") is False:
            findings.append(
                {
                    "rule": "merge-conflict",
                    "severity": "error",
                    "file": "",
                    "evidence": [dev_tools.orchestrator.get_config().base_branch_name],
                    "message": f"PR conflicts with the {dev_tools.orchestrator.get_config().base_branch_name} base branch.",
                }
            )
        return findings

    def evaluate_pr_heuristics(
        self, pr: Dict[str, Any], diff: str, checks: Dict[str, Any]
    ) -> str:
        """Applies heuristic rules to a PR diff and checks, returning specific feedback."""
        # Pre-process diff to get unique files for faster heuristic matching
        files_in_diff = set()
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                files_in_diff.add(line[6:])

        is_ui = any(
            any(ind in f for ind in dev_tools.orchestrator.get_config().ui_indicators)
            for f in files_in_diff
        )
        is_python = any(f.endswith(".py") for f in files_in_diff)
        is_infra = any(
            any(
                ind in f for ind in dev_tools.orchestrator.get_config().infra_file_paths
            )
            for f in files_in_diff
        )

        # File Necessity Check (Temporary Files)
        temp_files = []
        for f in files_in_diff:
            if any(
                re.search(pattern, f)
                for pattern in dev_tools.orchestrator.get_config().temp_file_patterns
            ):
                temp_files.append(f)

        fails = [
            c["name"]
            for c in checks.get("check_runs", [])
            if c.get("conclusion") == "failure"
        ]

        feedback = f"### Specific Review for PR #{pr['number']}\n\n"

        # What's working
        feedback += "**What is working well:**\n"
        feedback += f"- The scope is clearly defined in branch `{pr.get('head', {}).get('ref', 'unknown')}`.\n"
        if not fails:
            feedback += "- All CI checks appear to be passing.\n"

        feedback += "\n**Specific Issues & Actionable Fixes:**\n"

        if fails:
            feedback += (
                f"- "
                f"**CI Failure:** "
                f"The following "
                f"checks are "
                f"failing: {', '.join(fails)}. "
                f"Please investigate "
                f"the logs "
                f"for these "
                f"jobs.\n"
            )
            if "Build & E2E" in fails:
                feedback += (
                    "  "
                    "- *Fix:* "
                    "Ensure `pnpm "
                    "run build` "
                    "passes locally "
                    "and all "
                    "`playwright` tests "
                    "succeed via "
                    "`pnpm test:e2e`.\n"
                )
            elif "deploy" in fails:
                feedback += (
                    "  "
                    "- *Fix:* "
                    "Verify that "
                    "the `dist` "
                    "directory compiles "
                    "correctly without "
                    "TypeScript or "
                    "Vite errors.\n"
                )

        if is_ui:
            tw_evidence = self._tailwind_evidence(diff)
            if tw_evidence:
                feedback += (
                    "- "
                    "**Design System "
                    "Anti-patterns:** The "
                    "diff adds "
                    "raw Tailwind "
                    "classes (e.g. "
                    "padding/margin utility "
                    "classes, arbitrary "
                    "values).\n"
                )
                for path, added in tw_evidence[:3]:
                    feedback += f"  - `{path}`: `+{added[:120]}`\n"
                feedback += (
                    "  "
                    "- *Fix:* "
                    "Replace raw "
                    "Tailwind layout "
                    "classes with "
                    "`Stack`, `Box`, "
                    "or `Grid` "
                    "primitives using "
                    "design tokens "
                    "(e.g., `gap={4}`, "
                    "`paddingY={{ base: "
                    "4, md: "
                    "1.5 }}`). "
                    "Verify by "
                    "running `td "
                    "gh audit-gate`.\n"
                )

            feedback += (
                "- "
                "**Mobile UX "
                "Verification:** For "
                "any UI "
                "additions, ensure "
                "horizontal layout "
                "does not "
                "overflow a "
                "390px viewport.\n"
            )
            feedback += (
                "  "
                "- *Fix:* "
                "If adding "
                "interactive elements, "
                "wrap them "
                "to enforce "
                "a minimum "
                "48x48px touch "
                "target for "
                "accessibility.\n"
            )

        if is_python:
            feedback += "- **Python Scripting:** Python changes detected.\n"
            feedback += (
                "  "
                "- *Fix:* "
                "Ensure `python3 "
                "-m pytest "
                "tests/` passes. "
                "Update `test_td` "
                "or equivalent "
                "test files "
                "if extending "
                "`dev-tools`.\n"
            )

        if is_infra:
            feedback += dev_tools.orchestrator.get_config().infra_feedback

        if temp_files:
            feedback += dev_tools.orchestrator.get_config().temp_file_feedback
            for tf in sorted(temp_files):
                feedback += f"  - `{tf}`\n"

        if pr.get("mergeable") is False:
            base_branch_name = dev_tools.orchestrator.get_config().base_branch_name
            feedback += f"- **Merge Conflicts:** This PR has conflicts with the `{base_branch_name}` base branch.\n"
            feedback += (
                f"  "
                f"- *Fix:* "
                f"Pull `{base_branch_name}` "
                f"into your "
                f"branch, resolve "
                f"the conflicts "
                f"(e.g., via "
                f"`{dev_tools.orchestrator.get_config().cli_alias} gh "
                f"resolve-conflicts --pr "
                f"{pr.get('number', '')}`), and "
                f"force push.\n"
            )

        if (
            "overlap" in pr.get("title", "").lower()
            or "cli" in pr.get("title", "").lower()
        ):
            feedback += "- **Overlap / Interdependency:** This PR touches dev-tools or overlap logic.\n"
            feedback += (
                f"  "
                f"- *Fix:* "
                f"Ensure this "
                f"is rebased "
                f"against recent "
                f"changes in "
                f"the `{dev_tools.orchestrator.get_config().base_branch_name}` "
                f"branch to "
                f"avoid overlapping "
                f"functionality.\n"
            )

        # Default if no specific issues caught by heuristics
        if feedback.endswith("**Specific Issues & Actionable Fixes:**\n"):
            feedback += (
                "- "
                "Review the "
                "diff against "
                "`audit` guidelines. "
                "Ensure no "
                "console errors "
                "exist in "
                "the target "
                "components.\n"
            )

        return feedback

    def review_pr(self, prNumber: int, **kwargs) -> Dict[str, Any]:
        """Review a pull request and post findings."""
        if "pr_number" in kwargs:
            prNumber = kwargs["pr_number"]
        """
        Fetches a PR and evaluates AST and heuristic compliance rules locally.
        """
        pr_details = self.github.fetch_pr_details(prNumber)
        sha = pr_details.get("head", {}).get("sha")
        check_runs = self.github.fetch_check_runs(sha)
        pr_diff = self.github.fetch_pr_diff(prNumber)

        feedback = self.evaluate_pr_heuristics(
            pr_details, pr_diff, {"check_runs": check_runs}
        )
        fails = [c["name"] for c in check_runs if c.get("conclusion") == "failure"]
        verdict = "Not Approved" if fails else "Approved"

        return {
            "prNumber": prNumber,
            "recommendation": verdict,
            "reviewComment": feedback,
            "findings": self.collect_pr_findings(
                pr_details, pr_diff, {"check_runs": check_runs}
            ),
        }

    def get_audit_results(
        self, content: Optional[str] = None, targets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Collect audit tool results for targets."""
        script_path = self._resolve_antipatterns_script()
        if script_path and os.path.exists(script_path):
            cmd = ["node", script_path, "--json"]
            if targets:
                cmd.extend(targets)
            elif content is not None:
                cmd.append("-")
            res = dev_tools.orchestrator.run_command(
                cmd, check=False, input_str=content
            )
            try:
                stdout = (
                    res.stdout
                    if isinstance(res, subprocess.CompletedProcess)
                    else str(res)
                )
                node_results = json.loads(stdout)
            except json.JSONDecodeError:
                node_results = {"violations": {}, "config": {}}
        else:
            node_results = {
                "violations": {},
                "config": {},
                "status": "skipped",
                "reason": "detect-antipatterns.mjs not found",
            }

        # Integrate Python ASTAuditor deterministic checks
        from dev_tools.services.ast_audit import ASTAuditor

        ast_auditor = ASTAuditor()

        ast_violations = node_results.get("violations", {})
        if targets:
            for target_path in targets:
                if os.path.isfile(target_path):
                    try:
                        with open(target_path, "r", encoding="utf-8") as target_file:
                            code = target_file.read()
                        findings = ast_auditor.audit_file(target_path, code)
                        if findings:
                            if target_path not in ast_violations:
                                ast_violations[target_path] = []
                            for finding in findings:
                                ast_violations[target_path].append(
                                    {
                                        "pattern": finding["rule"],
                                        "message": finding["message"],
                                        "value": finding["value"],
                                        "severity": finding["severity"],
                                        "line": finding["line"],
                                    }
                                )
                    except Exception as e:
                        log_warn(
                            f"orchestrator: AST audit failed for {target_path}: {e}"
                        )
                elif os.path.isdir(target_path):
                    try:
                        dir_findings = ast_auditor.audit_directory(target_path)
                        for filepath, findings in dir_findings.items():
                            rel_path = (
                                os.path.relpath(filepath)
                                if os.path.isabs(filepath)
                                else filepath
                            )
                            if rel_path not in ast_violations:
                                ast_violations[rel_path] = []
                            for finding in findings:
                                ast_violations[rel_path].append(
                                    {
                                        "pattern": finding["rule"],
                                        "message": finding["message"],
                                        "value": finding["value"],
                                        "severity": finding["severity"],
                                        "line": finding["line"],
                                    }
                                )
                    except Exception as e:
                        log_warn(f"orchestrator: AST audit failed for {rel_path}: {e}")
        elif content is not None:
            findings = ast_auditor.audit_file("stdin.tsx", content)
            if findings:
                if "stdin" not in ast_violations:
                    ast_violations["stdin"] = []
                for finding in findings:
                    ast_violations["stdin"].append(
                        {
                            "pattern": finding["rule"],
                            "message": finding["message"],
                            "value": finding["value"],
                            "severity": finding["severity"],
                            "line": finding["line"],
                        }
                    )

        node_results["violations"] = ast_violations
        return node_results

    def extract_code_blocks(self, text: str) -> List[str]:
        """Extract fenced code blocks from text."""
        return re.findall(r"```(?:tsx?|jsx?|html)?\n(.*?)```", text, re.DOTALL)

    def get_pr_files(self, pr: Any) -> set[str]:
        """List files touched by a pull request."""
        return {f.filename for f in pr.get_files()}

    def extract_exports_from_diff(self, diff_text: str) -> Dict[str, set[str]]:
        """
        Extracts exported symbols added or modified in a PR diff per file.
        Supports TypeScript/JavaScript (export function/const/class/type/interface)
        and Python (def/class additions).
        """
        file_exports = defaultdict(set)
        current_file = None
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:]
            elif line.startswith("+") and not line.startswith("+++") and current_file:
                added = line[1:].strip()
                # TS/JS exports
                ts_match = re.search(
                    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|const|class|type|"
                    r"interface|enum|let|var)\s+([A-Za-z0-9_]+)",
                    added,
                )
                if ts_match:
                    file_exports[current_file].add(ts_match.group(1))
                else:
                    # Python top-level class or function definition
                    py_match = re.search(r"^(?:def|class)\s+([A-Za-z0-9_]+)", added)
                    if py_match:
                        file_exports[current_file].add(py_match.group(1))
        return file_exports
