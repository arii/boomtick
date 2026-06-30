from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectConfig
from .services.gemini import GeminiService
from .services.github import GitHubService
from .services.jules import JulesService
from .services.review import ReviewService


@dataclass
class ReviewResult:
    engine: str
    output: str


class Orchestrator:
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.github = GitHubService(repo=config.github_repo)
        self.gemini = GeminiService()
        self.jules = JulesService(api_url=config.jules_api_url)
        self.reviews = ReviewService()

    def review_pr(self, pr_number: int) -> ReviewResult:
        files = self.github.list_changed_files(pr_number)
        prompt = self.reviews.build_prompt("\n".join(files))
        # Defaulting to Gemini as the primary engine now
        return ReviewResult(engine="gemini", output=self.gemini.review(prompt))

    def audit_pr(self, pr_number: int) -> dict:
        pr = self.view_pr(pr_number)
        files = self.github.list_changed_files(pr_number)
        return {"pr": pr, "changed_files": files, "summary": f"Audit prepared for {len(files)} files"}

    def analyze_file(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"file_not_found: {path}"
        prompt = self.reviews.build_prompt(p.read_text(encoding='utf-8')[:8000])
        return self.gemini.review(prompt)

    def view_pr(self, pr_number: int) -> dict:
        pr = self.github.view_pr(pr_number)
        stats = self.github.diff_stats(pr_number)
        return {"number": pr.number, "title": pr.title, "author": pr.author, "state": pr.state, **stats}

    def resolve_pr(self, pr_number: int, dry_run: bool = True) -> str:
        return self.github.resolve_conflicts(pr_number, dry_run=dry_run)

    def dispatch_jules_review(self, pr_number: int) -> str:
        pr = self.github.view_pr(pr_number)
        session = self.jules.dispatch_session(task=f"Review PR #{pr.number}: {pr.title}")
        return session.status

    def sync_jules(self) -> dict:
        return {"status": "ok", "active_sessions": []}

    def repair_local_state(self) -> str:
        return "repair workflow delegated to dev-tools/repair.py"

    def env_verify(self) -> dict[str, bool]:
        return {
            "jules_configured": bool(self.config.jules_api_url),
            "repo_configured": bool(self.config.github_repo),
        }
