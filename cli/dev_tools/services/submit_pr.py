"""Scope-gated PR submission for agent worktrees (td half of the loop).

``submit()`` pushes a worktree branch and opens a PR, refusing when the
changed files fall outside the linked issue's scope (same matching
rules as CI's scope gate via scope_gate.py). No LLM involved:
worktree create -> agent run -> submit-pr is fully deterministic.
"""

import json
import os
import subprocess

from dev_tools.services import local_sessions as ls
from dev_tools.services import scope_gate


class SubmitError(ValueError):
    """Raised for scope violations, empty diffs, or push/PR failures."""


def _run(args, cwd):
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise SubmitError(f"exec failed: {exc}")


def _branch(worktree):
    res = _run(["git", "branch", "--show-current"], worktree)
    return res.stdout.strip() if res.returncode == 0 else ""


def changed_vs_base(worktree, base):
    """Committed files on this branch since base (merge-base diff)."""
    res = _run(["git", "diff", "--name-only", f"{base}...HEAD"], worktree)
    if res.returncode != 0:
        return []
    return [l for l in (res.stdout or "").splitlines() if l.strip()]


def submit(worktree_path, title, body="", base="main", draft=True,
           repo=None, issue_text=None, skip_scope=False):
    """Push the worktree branch and open a PR. Returns a result dict.

    Scope: when ``issue_text`` is given, committed-since-base plus
    uncommitted files must all match the issue (CI rules); violations
    refuse unless ``skip_scope`` (mirrors CI's [skip-scope-check]).
    Records the PR url into session.json when one is present.
    """
    worktree = os.path.abspath(worktree_path)
    if not os.path.isdir(os.path.join(worktree, ".git")) \
            and not os.path.isfile(os.path.join(worktree, ".git")):
        # Worktrees carry .git as a file; plain dirs are not checkouts.
        if not os.path.exists(os.path.join(worktree, ".git")):
            raise SubmitError(f"Not a git checkout: {worktree_path}")
    branch = _branch(worktree)
    if not branch:
        raise SubmitError("Worktree has no current branch (detached?)")
    committed = changed_vs_base(worktree, base)
    dirty = ls.changed_files(worktree)
    scope_files = sorted(set(committed) | set(dirty))
    if not scope_files:
        raise SubmitError("No changes to submit (branch matches base)")
    scope = {"checked": False, "allowed": [], "disallowed": [],
             "skipped": False}
    if issue_text and not skip_scope and not scope_gate.check_override():
        ok, allowed, disallowed = scope_gate.check_scope(
            scope_files, issue_text, root=worktree)
        scope.update(checked=True,
                     allowed=[f for f, _ in allowed],
                     disallowed=list(disallowed))
        if not ok:
            raise SubmitError(
                "Out-of-scope files for this issue: "
                + ", ".join(disallowed))
    elif issue_text:
        scope.update(checked=False, skipped=True)
    push = _run(["git", "push", "origin", branch], worktree)
    if push.returncode != 0:
        raise SubmitError(
            f"Failed to push {branch}: "
            f"{(push.stderr or push.stdout or '').strip()[:300]}")
    args = ["pr", "create", "--base", base, "--head", branch,
            "--title", title, "--body", body or ""]
    if draft:
        args.append("--draft")
    if repo:
        args += ["--repo", repo]
    pr = _run(["gh"] + args, worktree)
    if pr.returncode != 0:
        raise SubmitError(
            f"Failed to open PR: "
            f"{(pr.stderr or pr.stdout or '').strip()[:300]}")
    url = (pr.stdout or "").strip().splitlines()
    url = url[-1].strip() if url else ""
    _record_pr_url(worktree, url)
    return {"status": "submitted", "url": url, "branch": branch,
            "base": base, "draft": draft, "scope": scope,
            "files": scope_files}


def _record_pr_url(worktree, url):
    """Best-effort pullRequestUrl stamp on a co-located session.json."""
    path = os.path.join(worktree, "session.json")
    if not url or not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            session = json.load(handle)
        if not isinstance(session, dict):
            return
        session["pullRequestUrl"] = url
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(session, handle, indent=2)
    except (OSError, ValueError):
        pass
