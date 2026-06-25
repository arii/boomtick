from __future__ import annotations
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class ProjectConfig:
    github_repo: str | None = None
    github_token_env: str = "GITHUB_TOKEN"
    gemini_api_key_env: str = "GEMINI_API_KEY"
    jules_api_url: str | None = None

def load_project_config(path: str | Path = "dev-tools/project_config.json") -> ProjectConfig:
    p = Path(path)

    if not p.exists():
        return ProjectConfig()

    raw = json.loads(p.read_text(encoding="utf-8"))
    return ProjectConfig(
        github_repo=raw.get("github_repo") or raw.get("repo_name"),
        github_token_env=raw.get("github_token_env", "GITHUB_TOKEN"),
        gemini_api_key_env=raw.get("gemini_api_key_env", "GEMINI_API_KEY"),
        jules_api_url=raw.get("jules_api_url"),
    )
