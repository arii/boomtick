"""Local worktree session bookkeeping, mirroring the MCP session tools.

File layout mirrors ``mcp/src/lib/session_manager.ts`` and
``mcp/src/lib/skills.ts`` so ``td`` and the MCP tools read and write the
same state:

- ``<repo>/.worktrees/<name>/session.json`` (AgentSession schema)
- ``<repo>/.agents/skills/<name>/SKILL.md``

Executor behaviour mirrors ``runSessionProcess``: same environment knobs
(``BOOMTICK_SESSION_EXEC``, ``BOOMTICK_EXECUTOR_CLI``,
``BOOMTICK_EXECUTOR_MODEL``), same checkpoints, same 2000-line log cap.
One deliberate difference: the system prompt carries the worktree agent
contract plus the brief, but not the MCP-server-local repair prompt
asset (``mcp/src/agents/repair-agent.prompt.md``), which is not part of
the CLI distribution.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

SESSION_FILE = "session.json"
WORKTREES_DIR = ".worktrees"
SKILLS_DIR = os.path.join(".agents", "skills")
MAX_SESSION_LOG_LINES = 2000


class SessionNotFound(ValueError):
    """Raised when a session id matches no session.json on disk."""


class SkillNotFound(ValueError):
    """Raised when a skill name has no SKILL.md on disk."""


def _git(args, cwd):
    try:
        res = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True,
            check=False,
        )
    except OSError:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def repo_root_for(path=None):
    """Return the repo root holding ``.worktrees`` for ``path`` (or cwd).

    Inside a linked worktree, ``git rev-parse --show-toplevel`` returns
    the worktree itself, so the main root is derived from
    ``--git-common-dir`` and preferred when it holds ``.worktrees``.
    """
    start = os.path.abspath(path or os.getcwd())
    top = _git(["rev-parse", "--show-toplevel"], start) or start
    common = _git(["rev-parse", "--git-common-dir"], start)
    if common:
        if not os.path.isabs(common):
            common = os.path.join(top, common)
        main_root = os.path.dirname(os.path.abspath(common))
        if os.path.isdir(os.path.join(main_root, WORKTREES_DIR)):
            return main_root
    return top


def worktrees_dir(root):
    """Absolute path of the sessions directory for a repo root."""
    return os.path.join(os.path.abspath(root), WORKTREES_DIR)


def skills_dir(root):
    """Absolute path of the skills directory for a repo root."""
    return os.path.join(os.path.abspath(root), SKILLS_DIR)


def scan_sessions(root):
    """Load every readable session.json under .worktrees (corrupt ignored)."""
    found = []
    base = worktrees_dir(root)
    if not os.path.isdir(base):
        return found
    for entry in sorted(os.listdir(base)):
        candidate = os.path.join(base, entry, SESSION_FILE)
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("sessionId"):
            found.append(data)
    return found


def load_session(root, session_id):
    """Return the session dict for ``session_id`` or raise SessionNotFound."""
    for session in scan_sessions(root):
        if session.get("sessionId") == session_id:
            return session
    raise SessionNotFound(f"Session {session_id} not found")


def save_session(session):
    """Persist a session dict to its worktree session.json (never raises)."""
    try:
        worktree = session.get("worktreePath")
        if not worktree or not os.path.isdir(worktree):
            return
        with open(os.path.join(worktree, SESSION_FILE), "w",
                  encoding="utf-8") as handle:
            json.dump(session, handle, indent=2)
    except (OSError, ValueError, TypeError):
        pass


def _detect_branch(worktree_path):
    branch = _git(["branch", "--show-current"], worktree_path)
    if branch:
        return branch
    return "agent/" + os.path.basename(os.path.abspath(worktree_path))


def new_session(worktree_path, brief, model=None, repo=None, worktree_id=None):
    """Build (not persist) a session dict with the AgentSession schema."""
    worktree_path = os.path.abspath(worktree_path)
    session_id = "sess_" + secrets.token_hex(6)
    now = int(time.time() * 1000)
    return {
        "sessionId": session_id,
        "worktreeId": worktree_id or os.path.basename(worktree_path),
        "worktreePath": worktree_path,
        "branch": _detect_branch(worktree_path),
        "baseBranch": "main",
        "repo": repo,
        "brief": brief,
        "model": model,
        "state": "running",
        "status": "running",
        "startedAt": now,
        "createdAt": now,
        "updatedAt": now,
        "lastCheckpoint": "worktree_setup",
        "changedFiles": [],
        "retries": 0,
        "maxRetries": 3,
        "transcript": [f"[System]: Dispatch initiated with model "
                       f"{model or 'default'}"],
        "logs": [f"[{time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())}] "
                 f"Session {session_id} initialized in worktree "
                 f"{worktree_path}"],
        "lastVerification": None,
    }


def update_checkpoint(session, checkpoint, state):
    """Set checkpoint + state, refresh updatedAt, persist."""
    session["lastCheckpoint"] = checkpoint
    session["state"] = state
    session["updatedAt"] = int(time.time() * 1000)
    save_session(session)


def append_lines(session, lines):
    """Append streamed lines with the shared 2000-line cap, persist."""
    logs = session.setdefault("logs", [])
    for line in lines:
        if len(logs) >= MAX_SESSION_LOG_LINES:
            logs.append("[exec] log truncated: line cap reached")
            break
        logs.append(line)
    session["updatedAt"] = int(time.time() * 1000)
    save_session(session)


def append_log(session, line):
    """Append one log line (see append_lines)."""
    append_lines(session, [line])


def changed_files(worktree_path):
    """Parse git status --porcelain into file paths (mirrors getStatus)."""
    out = _git(["status", "--porcelain"], worktree_path)
    if out is None:
        return []
    files = []
    for raw in out.splitlines():
        line = raw[:-1] if raw.endswith("\r") else raw
        if not line.strip():
            continue
        match = re.match(r"^..\s+(.*)$", line)
        name = match.group(1).strip() if match else line[3:].strip()
        if " -> " in name:
            name = name.split(" -> ")[-1].strip()
        if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        if name:
            files.append(name)
    return files


def status_summary(session):
    """Agent-status-shaped summary with refreshed changed files."""
    worktree = session.get("worktreePath")
    if worktree and os.path.isdir(worktree):
        session["changedFiles"] = changed_files(worktree)
        save_session(session)
    return {
        "sessionId": session.get("sessionId"),
        "worktreeId": session.get("worktreeId"),
        "state": session.get("state"),
        "lastCheckpoint": session.get("lastCheckpoint"),
        "changedFiles": session.get("changedFiles", []),
        "lastVerification": session.get("lastVerification"),
    }


def tail_logs(session, tail=100):
    """Return (lines, total) for the session logs (tail<=0 yields [])."""
    logs = session.get("logs", [])
    total = len(logs)
    if tail is None or tail <= 0:
        return [], total
    return logs[-tail:], total


def build_system_prompt(worktree_path, brief):
    """Contract + brief system prompt (mirrors loadAgentContext minus the
    MCP-server-local repair prompt asset)."""
    sections = []
    contract = os.path.join(worktree_path, ".agents", "AGENT_CONTRACT.md")
    if os.path.isfile(contract):
        try:
            with open(contract, encoding="utf-8") as handle:
                sections.append("# Worktree Agent Contract\n\n" +
                                handle.read())
        except OSError:
            pass
    sections.append("# Task Brief\n\n" + brief)
    return "\n\n---\n\n".join(sections)


def executor_command(session):
    """Return (cli, args) for the session executor (mirrors TS spawn)."""
    cli = os.environ.get("BOOMTICK_EXECUTOR_CLI", "pi")
    model = session.get("model") or os.environ.get("BOOMTICK_EXECUTOR_MODEL")
    args = ["-p", "--system-prompt",
            build_system_prompt(session["worktreePath"], session["brief"])]
    if model:
        args += ["--model", model]
    args.append(session["brief"])
    return cli, args


def exec_disabled():
    """True when BOOMTICK_SESSION_EXEC=0 (bookkeeping only)."""
    return os.environ.get("BOOMTICK_SESSION_EXEC") == "0"


def run_executor(root, session, stream=None):
    """Run the executor in the foreground, streaming into session logs.

    ``stream`` is an optional callable receiving each output line (for
    live terminal display). Returns the exit code, or None when
    execution is disabled. Final checkpoint mirrors the MCP tool:
    execution_done/done on 0, execution_failed/failed otherwise.
    """
    if exec_disabled():
        return None
    update_checkpoint(session, "executing", "running")
    cli, args = executor_command(session)
    try:
        child = subprocess.Popen(
            [cli] + args, cwd=session["worktreePath"], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except OSError as exc:
        append_log(session, f"[exec] spawn failed: {exc}")
        update_checkpoint(session, "execution_failed", "failed")
        return 127
    assert child.stdout is not None
    for raw in child.stdout:
        line = raw.rstrip("\n")
        append_lines(session, [line])
        if stream is not None:
            stream(line)
    code = child.wait()
    if code == 0:
        update_checkpoint(session, "execution_done", "done")
    else:
        update_checkpoint(session, "execution_failed", "failed")
    return code


def spawn_detached(root, session_id):
    """Re-invoke this CLI detached to supervise the session executor."""
    td_binary = shutil.which("td") or sys.argv[0]
    child = subprocess.Popen(
        [td_binary, "session", "supervise", session_id,
         "--path", os.path.abspath(root)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    return child.pid


def list_skills(root):
    """Skill names having a SKILL.md (mirrors skills.ts list)."""
    base = skills_dir(root)
    if not os.path.isdir(base):
        return []
    names = []
    for entry in sorted(os.listdir(base)):
        if os.path.isfile(os.path.join(base, entry, "SKILL.md")):
            names.append(entry)
    return names


def read_skill(root, name):
    """Return SKILL.md content; rejects traversal + missing (mirrors read)."""
    base = os.path.abspath(skills_dir(root))
    candidate = os.path.abspath(os.path.join(base, name, "SKILL.md"))
    if not candidate.startswith(base + os.sep):
        raise SkillNotFound(f"Skill {name} not found")
    if not os.path.isfile(candidate):
        raise SkillNotFound(f"Skill {name} not found")
    with open(candidate, encoding="utf-8") as handle:
        return handle.read()
