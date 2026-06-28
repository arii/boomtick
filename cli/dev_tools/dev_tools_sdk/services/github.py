from __future__ import annotations

import json
from dataclasses import dataclass

import os
import requests
from ..utils.auth import get_github_token


@dataclass
class PullRequestSummary:
    number: int
    title: str
    author: str
    state: str


class GitHubService:
    def __init__(self, repo: str | None = None):
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO")
        self.token = get_github_token()
        self.base_url = "https://api.github.com"

    def _request(self, method: str, path: str, accept: str = "application/vnd.github.v3+json") -> dict:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
        }
        response = requests.request(method, url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def view_pr(self, number: int) -> PullRequestSummary:
        payload = self._request("GET", f"/repos/{self.repo}/pulls/{number}")
        return PullRequestSummary(
            number=payload["number"],
            title=payload["title"],
            author=payload["user"]["login"],
            state=payload["state"],
        )

    def list_changed_files(self, number: int) -> list[str]:
        payload = self._request("GET", f"/repos/{self.repo}/pulls/{number}/files")
        return [f["filename"] for f in payload]

    def diff_stats(self, number: int) -> dict[str, int]:
        payload = self._request("GET", f"/repos/{self.repo}/pulls/{number}")
        return {
            "additions": int(payload.get("additions", 0)),
            "deletions": int(payload.get("deletions", 0)),
            "changed_files": int(payload.get("changed_files", 0)),
        }

    def resolve_conflicts(self, number: int, dry_run: bool = True) -> str:
        mode = "dry-run" if dry_run else "execute"
        return f"resolve_conflicts(pr={number}, mode={mode}) not yet automated"
