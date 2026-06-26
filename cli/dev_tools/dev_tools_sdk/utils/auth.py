from __future__ import annotations

import os
import subprocess
from typing import Sequence


class AuthError(RuntimeError):
    pass


def get_github_token(env_vars: Sequence[str] = ("GITHUB_TOKEN",)) -> str:
    for var in env_vars:
        value = os.getenv(var)
        if value:
            return value
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    raise AuthError("Missing GITHUB_TOKEN.")


def run_authenticated_gh(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    token = get_github_token()
    env["GITHUB_TOKEN"] = token
    env["GH_TOKEN"] = token
    return subprocess.run(["gh", *args], env=env, capture_output=True, text=True, check=False)
