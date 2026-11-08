"""Orchestrator base: init, client access, and small utilities."""
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from dev_tools.services.github import GitHubClient
from dev_tools.utils import CLIError
import dev_tools.orchestrator



class OrchestratorBase:
    """Orchestrator base: init, client access, and small utilities."""

    # Command detection patterns with word boundaries to avoid false positives
    _CMD_PATTERNS = {
        "conflict_resolve": r"(?<!\w)@conflict-resolve\b",
        "update_snapshots": r"(?<!\w)@update-snapshots\b",
        "ai_fix": r"(?<!\w)/ai-fix\b",
        "ai_review": r"(?<!\w)/ai-review\b",
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
        self.no_cache = no_cache

    @property
    def github(self) -> GitHubClient:
        if self._github is None:
            self._github = dev_tools.orchestrator.GitHubClient(repo=dev_tools.orchestrator.get_config().github_repo, no_cache=self.no_cache)
        return self._github

    def _resolve_antipatterns_script(self) -> Optional[str]:
        """Resolves the path to detect-antipatterns.mjs or returns None if missing."""
        # 1. Try standard root location
        script_path = "scripts/detect-antipatterns.mjs"
        if os.path.exists(script_path):
            return script_path

        # 2. Fallback to absolute path relative to this file (robust for package-style execution)
        # Location: cli/dev_tools/orchestrator.py -> ../../scripts/detect-antipatterns.mjs
        abs_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "detect-antipatterns.mjs")
        )
        if os.path.exists(abs_path):
            return abs_path

        return None

    def _pnpm_has_script(self, script_name: str, cwd: Optional[str] = None) -> bool:
        """Checks if package.json in cwd defines script_name."""
        target_dir = cwd or os.getcwd()
        pkg_path = os.path.join(target_dir, "package.json")
        if not os.path.exists(pkg_path):
            return False
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
            return script_name in pkg_data.get("scripts", {})
        except Exception:
            return False

    def _hash_content(self, content: str) -> str:
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _cleanup_worktree(self, worktree_path: str) -> None:
        """Robustly cleans up a git worktree and its directory."""
        # Unregister and attempt to remove the worktree via git
        dev_tools.orchestrator.run_command(["git", "worktree", "remove", "-f", worktree_path], check=False, log_on_error=False)

        # Forcefully delete the directory if it still exists
        if os.path.exists(worktree_path):
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Prune stale worktree metadata
        dev_tools.orchestrator.run_command(["git", "worktree", "prune"], check=False, log_on_error=False)

        # Final safety check
        if os.path.exists(worktree_path):
            raise CLIError(f"Failed to clean up worktree directory: {worktree_path}")
