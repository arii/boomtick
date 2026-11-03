"""Managed worktree operations under <repo>/.worktrees (td parity).

Mirrors ``mcp/src/tools/worktree.*.ts`` + ``createSessionWorktree`` so td
and the MCP tools manage the same worktree set: ``.worktrees/<id>``
checkouts on derived branches, with identical create/list/remove
semantics (id charset, dirty-worktree refusal, prune on remove).
"""

import os
import re
import secrets
import subprocess
import time

WORKTREES_DIR = ".worktrees"
ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class WorktreeError(ValueError):
    """Raised for invalid ids, missing worktrees, or git failures."""


def _git(args, cwd):
    try:
        res = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            check=False,
        )
    except OSError as exc:
        raise WorktreeError(f"git failed: {exc}")
    return res


def sanitize_name(name):
    """Branch slug for a worktree name (mirrors TS sanitizeBranchName)."""
    slug = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
    return slug


def worktrees_dir(root):
    """Absolute path of the sessions directory for a repo root."""
    return os.path.join(os.path.abspath(root), WORKTREES_DIR)


def _branch_of(path):
    res = _git(["branch", "--show-current"], path)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return ""


def _changed_count(path):
    res = _git(["status", "--porcelain"], path)
    if res.returncode != 0:
        return 0
    return sum(1 for line in res.stdout.splitlines() if line.strip())


def _dir_size(path):
    total = 0
    for base, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return total


def create(root, name=None, base_branch="main"):
    """Create a managed worktree; returns (id, path, branch).

    Layout mirrors createSessionWorktree: ``.worktrees/wt-<hex>`` on a
    new branch derived from ``name`` (or the id when unnamed).
    """
    root = os.path.abspath(root)
    worktree_id = "wt-" + secrets.token_hex(4)
    branch = sanitize_name(name) if name else ""
    if not branch:
        branch = worktree_id
    path = os.path.join(worktrees_dir(root), worktree_id)
    if os.path.exists(path):
        raise WorktreeError(f"Worktree already exists: {path}")
    os.makedirs(worktrees_dir(root), exist_ok=True)
    res = _git(["worktree", "add", path, "-b", branch, base_branch], root)
    if res.returncode != 0:
        raise WorktreeError(
            f"git worktree add failed: {(res.stderr or '').strip()}")
    return worktree_id, path, branch


def list_worktrees(root):
    """List managed worktrees with branch, age, dirtiness, disk use."""
    base = worktrees_dir(root)
    if not os.path.isdir(base):
        return []
    items = []
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        if not os.path.isdir(path):
            continue
        try:
            age = max(0, int(time.time() - os.path.getmtime(path)))
        except OSError:
            age = 0
        try:
            size = _dir_size(path)
        except OSError:
            size = 0
        items.append({
            "worktreeId": entry,
            "path": path,
            "branch": _branch_of(path),
            "ageSeconds": age,
            "changedFilesCount": _changed_count(path),
            "diskUsageBytes": size,
        })
    return items


def remove(root, worktree_id, force=False):
    """Remove a managed worktree; returns freed bytes (best effort).

    Refuses dirty worktrees unless ``force`` (mirrors the MCP tool),
    then unregisters via git and prunes stale metadata.
    """
    if not ID_RE.match(worktree_id or ""):
        raise WorktreeError(f"Invalid worktree id: {worktree_id}")
    root = os.path.abspath(root)
    path = os.path.join(worktrees_dir(root), worktree_id)
    if not os.path.exists(path):
        raise WorktreeError(f"Worktree not found: {worktree_id}")
    if not force and _changed_count(path) > 0:
        raise WorktreeError(
            f"Worktree {worktree_id} has uncommitted changes; "
            "pass --force to remove anyway")
    try:
        freed = _dir_size(path)
    except OSError:
        freed = None
    res = _git(["worktree", "remove", "--force", path], root)
    if res.returncode != 0:
        raise WorktreeError(
            f"git worktree remove failed: {(res.stderr or '').strip()}")
    _git(["worktree", "prune"], root)
    return freed
