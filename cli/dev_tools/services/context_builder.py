"""
context_builder.py - Generic Context Builder Module for Agentic Workflow Orchestration.

This module ingests PR diffs, file trees, and linked issues to dynamically format
prompt contexts based on graph node execution steps.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Set
from dev_tools.services.github import GitHubClient
from dev_tools.config import get_config

PROJECT_CONFIG = get_config()


class ContextBuilder:
    """
    Builds structured, step-specific agent contexts by ingesting various repository
    artifacts and formatting them into highly readable prompt structures.
    """

    # Configurable list of directories to ignore during tree traversal
    IGNORED_DIRS: Set[str] = {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "target",
        "collected-logs",
        "runs",
        ".git",
        ".venv",
    }

    def __init__(self, github_client: Optional[GitHubClient] = None) -> None:
        self._github = github_client
        self.pr_details: Dict[str, Any] = {}
        self.pr_diff: str = ""
        self.file_tree: Dict[str, Any] = {}
        self.linked_issues: List[Dict[str, Any]] = []
        self.extra_context: Dict[str, Any] = {}
        self.scratch_pad: List[Dict[str, Any]] = []

    def add_scratch_note(self, role: str, note: str) -> "ContextBuilder":
        """Adds a persistent observation note to the single-agent's shared scratch pad."""
        self.scratch_pad.append({"role": role, "note": note})
        return self

    def clear_scratch_pad(self) -> "ContextBuilder":
        """Clears the scratch pad notes."""
        self.scratch_pad = []
        return self

    @property
    def github(self) -> GitHubClient:
        """Lazy-loaded or explicitly passed GitHub client."""
        if self._github is None:
            self._github = GitHubClient()
        return self._github

    def ingest_pr(self, pr_number: int) -> "ContextBuilder":
        """Ingests PR details and the associated diff."""
        try:
            self.pr_details = self.github.fetch_pr_details(pr_number)
            self.pr_diff = self.github.fetch_pr_diff(pr_number)
        except Exception as e:
            self.pr_details = {"number": pr_number, "error": str(e)}
            self.pr_diff = f"Error fetching diff for PR #{pr_number}: {e}"
        return self

    def ingest_linked_issue(self, issue_number: int) -> "ContextBuilder":
        """Ingests linked issue details."""
        try:
            raw_issue = self.github.fetch_issue_details(issue_number)
            self.linked_issues.append(self.github.normalize_issue(raw_issue))
        except Exception as e:
            self.linked_issues.append({"number": issue_number, "error": str(e)})
        return self

    def ingest_file_tree(self, root_dir: str = ".", max_depth: int = 2) -> "ContextBuilder":
        """Generates and ingests a clean, structured directory layout of the repository."""
        # Performance optimization: Attempt to load from pre-warmed context index if available
        context_file = os.path.join(root_dir, ".agent-context.json")
        if os.path.exists(context_file):
            try:
                with open(context_file, "r", encoding="utf-8") as f:
                    context_data = json.load(f)
                    if isinstance(context_data, dict) and "file_tree" in context_data:
                        self.file_tree = context_data["file_tree"]
                        return self
            except Exception:
                pass

        self.file_tree = self._get_dir_structure(root_dir, max_depth, root_dir_abs=os.path.realpath(root_dir))
        return self

    def add_extra_context(self, key: str, value: Any) -> "ContextBuilder":
        """Injects any custom key-value pairs needed for a specific graph execution step."""
        self.extra_context[key] = value
        return self

    def _get_dir_structure(
        self,
        path_str: str,
        max_depth: int,
        current_depth: int = 0,
        root_dir_abs: Optional[str] = None,
    ) -> Dict[str, Any]:
        # pylint: disable=too-many-branches
        """Recursively gathers a directory structure representation, ignoring common build and cache directories."""
        if current_depth >= max_depth:
            return {}

        structure: Dict[str, Any] = {}
        try:
            path = os.path.realpath(path_str)
            if root_dir_abs is None:
                root_dir_abs = path

            # Security: Path Traversal Validation
            if os.path.commonpath([root_dir_abs, path]) != root_dir_abs:
                return structure

            if not os.path.exists(path):
                return structure

            for item_name in sorted(os.listdir(path)):
                # Ignore hidden files, temporary files, and ignored directories
                if (
                    item_name.startswith(".")
                    or item_name in self.IGNORED_DIRS
                    or item_name.endswith(".tmp")
                ):
                    continue

                full_path = os.path.join(path, item_name)
                if os.path.isdir(full_path):
                    structure[item_name + "/"] = self._get_dir_structure(
                        full_path,
                        max_depth,
                        current_depth + 1,
                        root_dir_abs=root_dir_abs,
                    )
                else:
                    structure[item_name] = None
        except Exception as e:
            structure["_error"] = str(e)

        return structure

    def _format_file_tree_as_markdown(self, tree: Dict[str, Any], indent: int = 0) -> str:
        """Helper to format a directory tree dict into a clean Markdown list."""
        lines: List[str] = []
        for name, contents in tree.items():
            if name == "_error":
                continue
            spacing = "  " * indent
            if name.endswith("/"):
                lines.append(f"{spacing}- 📁 {name}")
                if isinstance(contents, dict):
                    subtree_str = self._format_file_tree_as_markdown(contents, indent + 1)
                    if subtree_str:
                        lines.append(subtree_str)
            else:
                lines.append(f"{spacing}- 📄 {name}")
        return "\n".join(lines)

    def build_structured_context(self, step_name: str) -> Dict[str, Any]:
        """
        Builds a comprehensive structured dictionary of the context.
        Perfect for programmatic consumption or passing directly to JSON-based prompts.
        """
        # Determine changed files from pr_diff defensively using secure regex
        changed_files: Set[str] = set()
        if self.pr_diff:
            for line in self.pr_diff.splitlines():
                if line.startswith("+++ "):
                    # Safe regex-based parsing to support standard and custom prefixes
                    match = re.match(r"^\+\+\+\s+(?:b/)?(.*)", line)
                    if match:
                        path = match.group(1).split("\t")[0].strip()
                        if path.startswith("./"):
                            path = path[2:]
                        if path and path != "/dev/null":
                            changed_files.add(path)

        context = {
            "step": step_name,
            "project_repo": PROJECT_CONFIG.github_repo,
            "pr": {
                "number": self.pr_details.get("number"),
                "title": self.pr_details.get("title", ""),
                "description": self.pr_details.get("body", ""),
                "state": self.pr_details.get("state", ""),
                "changed_files": sorted(list(changed_files)),
                "diff": self.pr_diff,
            },
            "linked_issues": self.linked_issues,
            "file_tree": self.file_tree,
            "extra": self.extra_context,
            "scratch_pad": self.scratch_pad,
        }
        return context

    def build_markdown_context(self, step_name: str) -> str:
        # pylint: disable=too-many-branches
        """
        Formats the context as a highly structured, readable Markdown prompt context.
        Designed to be injected directly into LLM prompts.
        """
        data = self.build_structured_context(step_name)
        step = step_name.lower().strip()

        markdown_lines = [
            f"# Agent Task Execution Context — Step: {step_name.upper()}",
            f"**Repository:** `{data['project_repo']}`",
            "",
        ]

        # 1. Step Specific Instruction Header
        markdown_lines.append("## Step Instructions & Focus Areas")
        if step == "review":
            markdown_lines.extend(
                [
                    "Focus: Perform a strict code review of the PR modifications.",
                    "- Assure design token compliance (no raw Tailwind layout primitives or inline styles).",
                    "- Identify dead abstractions, responsibility creep, or unnecessary indirection.",
                    "- Review ONLY changes in the diff. Assume unmodified code is working.",
                ]
            )
        elif step == "audit":
            markdown_lines.extend(
                [
                    "Focus: Perform a whole-repository compliance and integrity audit.",
                    "- Analyze directory structure and check file necessity.",
                    "- Enforce repository rules and avoid temporary or stray artifacts in commits.",
                    "- Check overall compliance against design guidelines and issue specifications.",
                ]
            )
        elif step == "repair":
            markdown_lines.extend(
                [
                    "Focus: Resolve merge conflicts, bugs, or CI failures.",
                    "- Analyze error log trails, linked issue problem statements, and target files.",
                    "- Perform minimalist repairs avoiding scope creep or unnecessary refactors.",
                    "- Verify correctness of proposed fixes.",
                ]
            )
        else:
            markdown_lines.extend(
                [
                    "Focus: General agentic graph task execution.",
                    "- Review the ingested PR, linked issues, and file tree for comprehensive execution context.",
                ]
            )
        markdown_lines.append("")

        # 2. PR Information
        pr_data = data["pr"]
        if pr_data.get("number"):
            markdown_lines.extend(
                [
                    f"## Pull Request #{pr_data['number']}: {pr_data['title']}",
                    f"**State:** `{pr_data['state']}`",
                    "",
                    "### Description",
                    str(pr_data.get("description") or "_No description provided._"),
                    "",
                    "### Changed Files",
                ]
            )
            for f in pr_data["changed_files"]:
                markdown_lines.append(f"- `{f}`")
            markdown_lines.extend(["", "### Diff Content", "```diff", str(pr_data.get("diff") or ""), "```", ""])

        # 3. Linked Issues
        if data["linked_issues"]:
            markdown_lines.append("## Linked Issues")
            for issue in data["linked_issues"]:
                markdown_lines.extend(
                    [
                        f"### Issue #{issue.get('number')}: {issue.get('title')}",
                        f"**State:** `{issue.get('state')}`",
                        "",
                        "**Body:**",
                        str(issue.get("body") or "_No description provided._"),
                        "",
                    ]
                )

        # 4. File Tree Layout
        if data["file_tree"]:
            markdown_lines.extend(
                [
                    "## Repository File Layout Structure",
                    self._format_file_tree_as_markdown(data["file_tree"]),
                    "",
                ]
            )

        # 5. Agent Scratch Pad / Shared Thinking State
        if data["scratch_pad"]:
            markdown_lines.append("## Agent Scratch Pad (Shared Multi-Role Thinking State)")
            markdown_lines.append("These are intermediate thoughts and findings recorded sequentially by this agent:")
            for entry in data["scratch_pad"]:
                markdown_lines.extend(
                    [
                        f"### Note by Role: {entry.get('role', 'unknown').upper()}",
                        str(entry.get("note") or ""),
                        "",
                    ]
                )
            markdown_lines.append("")

        # 6. Extra context / logs
        if data["extra"]:
            markdown_lines.append("## Supplemental Execution Evidence")
            for key, val in data["extra"].items():
                markdown_lines.append(f"### {key}")
                if isinstance(val, (dict, list)):
                    markdown_lines.extend(["```json", json.dumps(val, indent=2), "```", ""])
                else:
                    markdown_lines.extend(["```text", str(val), "```", ""])

        return "\n".join(markdown_lines)
