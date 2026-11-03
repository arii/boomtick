# pylint: disable=missing-docstring,line-too-long
"""Tests for scope-gated td agent submit-pr (mocked push/gh, real git)."""
import json
import os
import subprocess
from unittest.mock import patch

import pytest

from dev_tools.services import submit_pr as sp

ISSUE = "# Fix login redirect\n\nTouches mcp/login.ts and its tests.\n"


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


@pytest.fixture()
def worktree(tmp_path):
    root = tmp_path / "wt"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "mcp").mkdir()
    (root / "mcp" / "login.ts").write_text("v1\n")
    _git(["add", "."], root)
    _git(["commit", "-qm", "init"], root)
    _git(["checkout", "-qb", "fix-login"], root)
    (root / "mcp" / "login.ts").write_text("v2\n")
    _git(["commit", "-qam", "fix"], root)
    return root


def _router(mapping):
    def run(args, cwd):
        key = tuple(args[:2])
        if key not in mapping:
            raise AssertionError(f"unexpected command: {args}")
        code, out, err = mapping[key]
        return subprocess.CompletedProcess(args, code, out, err)
    return run


def _ok_push_pr(url="https://github.com/o/r/pull/7\n"):
    return {
        ("git", "push"): (0, "", ""),
        ("gh", "pr"): (0, url, ""),
    }


def test_happy_path_in_scope(worktree):
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            return _router(_ok_push_pr())(args, cwd)
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        res = sp.submit(str(worktree), "Fix login", "body", "main",
                        True, "o/r", ISSUE)
    assert res["status"] == "submitted"
    assert res["url"] == "https://github.com/o/r/pull/7"
    assert res["branch"] == "fix-login"
    assert res["scope"]["checked"] is True
    assert res["scope"]["disallowed"] == []
    assert res["files"] == ["mcp/login.ts"]


def test_scope_violation_refuses(worktree):
    (worktree / "billing").mkdir()
    (worktree / "billing" / "unrelated.ts").write_text("x\n")
    _git(["add", "."], worktree)
    _git(["commit", "-qm", "scope creep"], worktree)
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            raise AssertionError("must not push when out of scope")
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        with pytest.raises(sp.SubmitError, match="Out-of-scope"):
            sp.submit(str(worktree), "T", "", "main", True, None, ISSUE)


def test_skip_scope_check_bypasses(worktree):
    (worktree / "billing").mkdir()
    (worktree / "billing" / "unrelated.ts").write_text("x\n")
    _git(["add", "."], worktree)
    _git(["commit", "-qm", "scope creep"], worktree)
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            return _router(_ok_push_pr())(args, cwd)
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        res = sp.submit(str(worktree), "T", "", "main", True, None,
                        ISSUE, skip_scope=True)
    assert res["scope"]["skipped"] is True
    assert res["status"] == "submitted"


def test_no_changes_refuses(worktree):
    _git(["checkout", "-q", "main"], worktree)
    with pytest.raises(sp.SubmitError, match="No changes"):
        sp.submit(str(worktree), "T")


def test_dirty_work_committed_with_agent_message(worktree):
    (worktree / "mcp" / "login.ts").write_text("v3-uncommitted\n")
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            return _router(_ok_push_pr())(args, cwd)
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        res = sp.submit(str(worktree), "Fix login", "", "main", True,
                        None, ISSUE, issue=271)
    assert res["status"] == "submitted"
    assert res["commit"]
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=worktree,
                         capture_output=True, text=True, check=True)
    assert log.stdout.strip() == "feat(agent): Fix login (#271)"
    # Nothing left uncommitted (supervisor state aside).
    status = subprocess.run(["git", "status", "--porcelain"], cwd=worktree,
                            capture_output=True, text=True, check=True)
    assert status.stdout.strip() == ""


def test_push_failure_surfaces(worktree):
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(args, 1, "", "denied")
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        with pytest.raises(sp.SubmitError, match="Failed to push"):
            sp.submit(str(worktree), "T")


def test_session_json_stamped(worktree):
    session = {"sessionId": "sess_1"}
    with open(worktree / "session.json", "w", encoding="utf-8") as handle:
        json.dump(session, handle)
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            return _router(_ok_push_pr())(args, cwd)
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        sp.submit(str(worktree), "T")
    with open(worktree / "session.json", encoding="utf-8") as handle:
        assert json.load(handle)["pullRequestUrl"] == \
            "https://github.com/o/r/pull/7"


def test_not_a_checkout_refuses(tmp_path):
    with pytest.raises(sp.SubmitError, match="Not a git checkout"):
        sp.submit(str(tmp_path), "T")


def test_root_session_json_excluded_from_scope(worktree):
    # Supervisor state is always dirty in session worktrees; it must
    # not trip the scope gate (regression from the #271 loop proof).
    (worktree / "session.json").write_text('{"sessionId": "sess_1"}')
    real_run = sp._run

    def router(args, cwd):
        if args[:2] == ["git", "push"] or args[0] == "gh":
            return _router(_ok_push_pr())(args, cwd)
        return real_run(args, cwd)

    with patch.object(sp, "_run", side_effect=router):
        res = sp.submit(str(worktree), "T", "", "main", True, None,
                        ISSUE)
    assert res["status"] == "submitted"
    assert "session.json" not in res["files"]
