from __future__ import annotations

import json
from dataclasses import dataclass

from tdw_services.services.github import GitHubClient


@dataclass
class PullRequestSummary:
    number: int
    title: str
    author: str
    state: str


class GitHubService:
    def __init__(self, repo: str | None = None):
        self.repo = repo
        self._client = GitHubClient(repo=repo)

    def view_pr(self, number: int) -> PullRequestSummary:
        payload = self._client.fetch_pr_details(number)
        return PullRequestSummary(
            number=payload["number"],
            title=payload["title"],
            author=payload["user"]["login"],
            state=payload["state"],
        )

    def list_changed_files(self, number: int) -> list[str]:
        payload = self._client.fetch_pr_files(number)
        return [f["filename"] for f in payload]

    def diff_stats(self, number: int) -> dict[str, int]:
        payload = self._client.fetch_pr_details(number)
        return {
            "additions": int(payload.get("additions", 0)),
            "deletions": int(payload.get("deletions", 0)),
            "changed_files": int(payload.get("changed_files", 0)),
        }

    def resolve_conflicts(self, number: int, dry_run: bool = True) -> str:
        mode = "dry-run" if dry_run else "execute"
        return f"resolve_conflicts(pr={number}, mode={mode}) not yet automated"
