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

from dev_tools.services import local_sessions

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


LOCKFILE_NAMES = (
    "pnpm-lock.yaml",
    "package-lock.json",
    "poetry.lock",
    "requirements.txt",
)

WARM_LINK_DIRS = ("node_modules", ".venv", "venv")


def lockfile_hash(root):
    """SHA256 over repo lockfiles, or '' when none exist."""
    import hashlib
    digest = hashlib.sha256()
    found = False
    for name in LOCKFILE_NAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                with open(path, "rb") as handle:
                    digest.update(name.encode("utf-8"))
                    digest.update(handle.read())
                found = True
            except OSError:
                continue
    return digest.hexdigest() if found else ""


def fast_forward_main_ref(root):
    """Fetch origin/main and advance the local main ref without checkout.

    Uses ``git update-ref refs/heads/main origin/main`` so the local main
    is current before branching, even when another branch (or another
    worktree) is checked out (#1139 item 6). Refuses to move a diverged
    main; falls back to ``merge --ff-only`` when main itself is checked
    out here. Returns (updated: bool, note: str).
    """
    res = _git(["fetch", "origin", "main"], root)
    if res.returncode != 0:
        return False, "fetch failed"
    current = _git(["branch", "--show-current"], root)
    if current.returncode == 0 and current.stdout.strip() == "main":
        status = _git(["status", "--porcelain"], root)
        if status.returncode == 0 and status.stdout.strip():
            return False, "worktree dirty; not fast-forwarding"
        merged = _git(["merge", "--ff-only", "origin/main"], root)
        return (merged.returncode == 0,
                "fast-forwarded" if merged.returncode == 0
                else "main diverged; not fast-forwarding")
    ancestor = _git(
        ["merge-base", "--is-ancestor", "refs/heads/main", "origin/main"],
        root)
    local_missing = _git(["rev-parse", "--verify", "refs/heads/main"], root)
    if ancestor.returncode == 0 or local_missing.returncode != 0:
        moved = _git(["update-ref", "refs/heads/main", "origin/main"], root)
        return (moved.returncode == 0,
                "fast-forwarded main ref" if moved.returncode == 0
                else "update-ref failed")
    return False, "main diverged; not fast-forwarding"


def fetch_main(root):
    """Fetch origin and fast-forward local main when clean.

    Returns (updated: bool, head_sha: str, note: str).
    """
    updated, note = fast_forward_main_ref(root)
    return updated, _head_sha(root), note


def _head_sha(root):
    res = _git(["rev-parse", "HEAD"], root)
    return res.stdout.strip() if res.returncode == 0 else ""


def warm_dependencies(root):
    """Install/sync deps by lockfile hash; returns (synced: bool, note).

    Runs the repo's own installers (pnpm frozen lockfile, pip) when
    the corresponding lockfile exists. Best effort: failures are
    reported, never raised.
    """
    notes = []
    synced = True
    pnpm_lock = os.path.join(root, "pnpm-lock.yaml")
    pkg_lock = os.path.join(root, "package-lock.json")
    requirements = os.path.join(root, "requirements.txt")
    if os.path.isfile(pnpm_lock):
        import subprocess as _sp
        proc = _sp.run(["pnpm", "install", "--frozen-lockfile"],
                       cwd=root, capture_output=True, text=True,
                       check=False)
        if proc.returncode == 0:
            notes.append("pnpm install ok")
        else:
            synced = False
            notes.append("pnpm install failed")
    elif os.path.isfile(pkg_lock):
        import subprocess as _sp
        proc = _sp.run(["npm", "ci"], cwd=root, capture_output=True,
                       text=True, check=False)
        if proc.returncode == 0:
            notes.append("npm ci ok")
        else:
            synced = False
            notes.append("npm ci failed")
    if os.path.isfile(requirements):
        import subprocess as _sp
        proc = _sp.run(["pip", "install", "-r", "requirements.txt"],
                       cwd=root, capture_output=True, text=True,
                       check=False)
        if proc.returncode == 0:
            notes.append("pip install ok")
        else:
            synced = False
            notes.append("pip install failed")
    if not notes:
        notes.append("no lockfiles; nothing to sync")
    return synced, "; ".join(notes)


def link_warm_deps(root, worktree_path):
    """Symlink warm dependency dirs from root into the worktree.

    Returns the list of linked dir names. Skips names that already
    exist in the worktree.
    """
    linked = []
    for name in WARM_LINK_DIRS:
        src = os.path.join(root, name)
        dst = os.path.join(worktree_path, name)
        if not os.path.isdir(src) or os.path.lexists(dst):
            continue
        try:
            os.symlink(src, dst)
            linked.append(name)
        except OSError:
            continue
    return linked


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
    if base_branch == "main":
        # Best-effort: local main current before branching (#1139 item 6).
        # Offline or diverged mains must not break creation.
        try:
            fast_forward_main_ref(root)
        except WorktreeError:
            pass
    path = os.path.join(worktrees_dir(root), worktree_id)
    if os.path.exists(path):
        raise WorktreeError(f"Worktree already exists: {path}")
    os.makedirs(worktrees_dir(root), exist_ok=True)
    res = _git(["worktree", "add", path, "-b", branch, base_branch], root)
    if res.returncode != 0:
        raise WorktreeError(
            f"git worktree add failed: {(res.stderr or '').strip()}")
    return worktree_id, path, branch


def create_for_issue(root, issue_id):
    """Provision a warm, dependency-linked worktree for an issue.

    Ensures main is warm (fetch fast-forward + dependency sync),
    then creates ``.worktrees/issue-<id>`` on branch
    ``agent/issue-<id>`` from ``origin/main`` with the root's
    dependency dirs symlinked in. Returns a status dict.
    """
    root = os.path.abspath(root)
    try:
        issue_num = int(str(issue_id))
    except (TypeError, ValueError):
        raise WorktreeError(f"Invalid issue id: {issue_id!r}")
    _updated, head_sha, main_note = fetch_main(root)
    synced, deps_note = warm_dependencies(root)
    branch = f"agent/issue-{issue_num}"
    path = os.path.join(worktrees_dir(root), f"issue-{issue_num}")
    if os.path.exists(path):
        raise WorktreeError(f"Worktree already exists: {path}")
    os.makedirs(worktrees_dir(root), exist_ok=True)
    res = _git(["fetch", "origin", "main"], root)
    if res.returncode != 0:
        raise WorktreeError(
            f"git fetch origin/main failed: "
            f"{(res.stderr or '').strip()}")
    res = _git(["worktree", "add", path, "-b", branch, "origin/main"],
               root)
    if res.returncode != 0:
        raise WorktreeError(
            f"git worktree add failed: {(res.stderr or '').strip()}")
    linked = link_warm_deps(root, path)
    return {
        "worktreeId": f"issue-{issue_num}",
        "path": path,
        "branch": branch,
        "base_sha": _head_sha(path) or head_sha,
        "deps_synced": synced,
        "deps_note": deps_note,
        "main_note": main_note,
        "linked_deps": linked,
    }


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

    Abandons sessions bound to the worktree first (single owner: td via
    local_sessions, #1139 item 3), refuses dirty worktrees unless
    ``force``, then unregisters via git and prunes stale metadata.
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
        local_sessions.abandon_sessions_in_worktree(root, path)
    except (OSError, ValueError):
        pass
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
