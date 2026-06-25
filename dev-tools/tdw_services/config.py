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
    gh_token_env: str = "GH_TOKEN"
    use_gemini_fallback: bool = True
    jules_api_url: str | None = None

def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

def load_project_config(path: str | Path = "dev-tools/project_config.json") -> ProjectConfig:
    p = Path(path)
    env_fallback = os.environ.get("USE_GEMINI_FALLBACK")
    fallback_val = _coerce_bool(env_fallback, True) if env_fallback is not None else None

    if not p.exists():
        return ProjectConfig(use_gemini_fallback=fallback_val if fallback_val is not None else True)

    raw = json.loads(p.read_text(encoding="utf-8"))
    return ProjectConfig(
        github_repo=raw.get("github_repo") or raw.get("repo_name"),
        github_token_env=raw.get("github_token_env", "GITHUB_TOKEN"),
        gh_token_env=raw.get("gh_token_env", "GH_TOKEN"),
        use_gemini_fallback=fallback_val if fallback_val is not None else _coerce_bool(raw.get("use_gemini_fallback"), True),
        jules_api_url=raw.get("jules_api_url"),
    )
