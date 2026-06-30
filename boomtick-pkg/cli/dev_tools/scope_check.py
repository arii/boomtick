import os
import sys
from typing import List, Optional, Set

try:
    from tdw_services.utils import log_info
except ImportError:
    def log_info(msg): print(msg, file=sys.stderr)

from dev_tools_sdk.config import load_project_config

# Import run_command from utils
from utils import run_command

def get_changed_files():
    """Returns the list of files changed in the current branch."""
    config = load_project_config()
    base = config.base_branch
    # Use check=False to manually handle fallback
    res = run_command(["git", "diff", "--name-only", base], check=False, log_on_error=False)
    if res.returncode == 0:
        return res.stdout.strip().splitlines()

    res = run_command(["git", "diff", "--name-only", "HEAD"], check=False, log_on_error=False)
    if res.returncode == 0:
        return res.stdout.strip().splitlines()

    return []

def verify_pr_scope(file_list=None):
    """Checks if a PR touches too many core layout/component files or mixes content scopes."""
    if file_list is None:
        file_list = get_changed_files()

    config = load_project_config()
    core_dirs = config.core_dirs
    threshold = config.monolithic_pr_threshold

    core_files = [f for f in file_list if any(f.startswith(d) for d in core_dirs)]
    if len(core_files) > threshold:
        return f"PR scope warning: Touching {len(core_files)} core files in {core_dirs}. Consider splitting this monolithic PR to avoid merge conflicts (AGENTS.md §23)."

    # Content Scope Check
    content_scopes = config.content_scopes

    active_scopes: Set[str] = set()
    for f in file_list:
        for scope_name, prefix in content_scopes.items():
            if f.startswith(prefix):
                active_scopes.add(scope_name)

    if len(active_scopes) > 1:
        scope_names = ", ".join(sorted(content_scopes.keys()))
        return f"Content scope warning: Mixed content domains detected ({', '.join(active_scopes)}). PRs should be split by scope: {scope_names} (AGENTS.md §21)."

    # Mixed Content and Code Check
    has_content = len(active_scopes) > 0
    code_files = [f for f in file_list if f.startswith("src/") and not any(f.startswith(d) for d in core_dirs)]

    if has_content and len(code_files) > 2:
        return "PR scope warning: Mixing significant code changes with content updates. Consider splitting content corrections from feature development."

    return None

if __name__ == "__main__":
    # If run as a script, it expects file names as arguments or via stdin
    # If no arguments/stdin, it auto-detects changed files in the repo
    files = sys.argv[1:]
    if not files and not sys.stdin.isatty():
        files = sys.stdin.read().splitlines()

    if not files:
        warning = verify_pr_scope()
    else:
        warning = verify_pr_scope(files)

    if warning:
        log_info(warning)
        sys.exit(1)
    sys.exit(0)
