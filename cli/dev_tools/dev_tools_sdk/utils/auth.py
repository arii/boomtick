from __future__ import annotations

import os
import subprocess
from typing import Sequence


class AuthError(RuntimeError):
    pass


def get_github_token(env_vars: Sequence[str] = ("GITHUB_TOKEN", "GH_TOKEN")) -> str:
    for var in env_vars:
        value = os.getenv(var)
        if value:
            return value
    # No longer attempting 'gh auth token' as gh binary is not available.
    raise AuthError("Missing GITHUB_TOKEN.")


def run_authenticated_gh(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # This method is deprecated as 'gh' CLI is not available.
    # We raise an error to prevent silent failures if it's still called.
    raise RuntimeError("run_authenticated_gh is disabled: 'gh' CLI is not available. Use GitHub REST API instead.")
