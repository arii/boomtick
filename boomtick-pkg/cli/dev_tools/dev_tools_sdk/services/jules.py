from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JulesSession:
    task: str
    status: str


class JulesService:
    def __init__(self, api_url: str | None = None):
        self.api_url = api_url

    def dispatch_session(self, task: str) -> JulesSession:
        # Network integration can be attached here while preserving interface.
        return JulesSession(task=task, status="dispatched")

    def sync_sessions(self) -> list[JulesSession]:
        return []
