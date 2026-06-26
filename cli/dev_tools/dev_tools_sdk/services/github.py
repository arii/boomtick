from __future__ import annotations

import json
from dataclasses import dataclass

from ..utils.auth import run_authenticated_gh


@dataclass
class PullRequestSummary:
    number: int
    title: str
    author: str
    state: str


class GitHubService:
    def __init__(self, repo: str | None = None):
        self.repo = repo

    def _repo_args(self) -> list[str]:
        return ["-R", self.repo] if self.repo else []

    def _gh_json(self, args: list[str], err: str) -> dict:
        res = run_authenticated_gh([*args, *self._repo_args()])
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or err)
        return json.loads(res.stdout)

    def view_pr(self, number: int) -> PullRequestSummary:
        payload = self._gh_json(
            ["pr", "view", str(number), "--json", "number,title,author,state"],
            "Failed to view pull request.",
        )
        return PullRequestSummary(
            number=payload["number"],
            title=payload["title"],
            author=payload["author"]["login"],
            state=payload["state"],
        )

    def list_changed_files(self, number: int) -> list[str]:
        payload = self._gh_json(["pr", "view", str(number), "--json", "files"], "Failed to read PR files.")
        return [f["path"] for f in payload.get("files", [])]

    def diff_stats(self, number: int) -> dict[str, int]:
        payload = self._gh_json(["pr", "view", str(number), "--json", "additions,deletions,changedFiles"], "Failed to read PR stats.")
        return {
            "additions": int(payload.get("additions", 0)),
            "deletions": int(payload.get("deletions", 0)),
            "changed_files": int(payload.get("changedFiles", 0)),
        }

    def resolve_conflicts(self, number: int, dry_run: bool = True) -> str:
        mode = "dry-run" if dry_run else "execute"
        return f"resolve_conflicts(pr={number}, mode={mode}) not yet automated"
