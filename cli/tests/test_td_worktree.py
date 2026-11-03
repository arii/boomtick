# pylint: disable=missing-docstring,line-too-long
"""Tests for td worktree create/list/remove (real git, tmp repos)."""
import json
import subprocess

import pytest
from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.services import worktrees as wt


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "README.md").write_text("hi\n")
    _git(["add", "."], root)
    _git(["commit", "-qm", "init"], root)
    return root


def test_create_named_branch_and_layout(repo):
    wid, path, branch = wt.create(str(repo), "Fix Login Flow")
    assert wid.startswith("wt-")
    assert branch == "fix-login-flow"
    assert path == str(repo / ".worktrees" / wid)
    out = subprocess.run(["git", "branch", "--show-current"], cwd=path,
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "fix-login-flow"


def test_create_unnamed_uses_id_as_branch(repo):
    wid, _path, branch = wt.create(str(repo))
    assert branch == wid


def test_create_bad_base_raises(repo):
    with pytest.raises(wt.WorktreeError):
        wt.create(str(repo), "x", base_branch="nope-branch")


def test_list_and_remove_round_trip(repo):
    wid, path, _branch = wt.create(str(repo), "demo")
    items = wt.list_worktrees(str(repo))
    assert [i["worktreeId"] for i in items] == [wid]
    assert items[0]["branch"] == "demo"
    assert items[0]["changedFilesCount"] == 0
    assert items[0]["diskUsageBytes"] > 0
    freed = wt.remove(str(repo), wid)
    assert freed and freed > 0
    assert wt.list_worktrees(str(repo)) == []
    assert not __import__("os").path.exists(path)


def test_remove_refuses_dirty_without_force(repo):
    wid, path, _branch = wt.create(str(repo), "demo")
    with open(f"{path}/dirty.txt", "w", encoding="utf-8") as handle:
        handle.write("x")
    with pytest.raises(wt.WorktreeError, match="uncommitted"):
        wt.remove(str(repo), wid)
    wt.remove(str(repo), wid, force=True)
    assert wt.list_worktrees(str(repo)) == []


def test_remove_rejects_bad_id_and_missing(repo):
    with pytest.raises(wt.WorktreeError, match="Invalid worktree id"):
        wt.remove(str(repo), "../escape")
    with pytest.raises(wt.WorktreeError, match="not found"):
        wt.remove(str(repo), "wt-deadbeef")


def test_sanitize_name():
    assert wt.sanitize_name("Fix Login_Flow!") == "fix-login-flow"
    assert wt.sanitize_name("---") == ""


def test_cli_create_list_remove(repo):
    runner = CliRunner()
    created = runner.invoke(cli, ["worktree", "create", "cli-demo",
                                  "--path", str(repo)])
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["branch"] == "cli-demo"
    wid = payload["worktreeId"]
    listed = runner.invoke(cli, ["worktree", "list", "--path", str(repo)])
    assert json.loads(listed.output)["worktrees"][0]["worktreeId"] == wid
    removed = runner.invoke(cli, ["worktree", "remove", wid,
                                  "--path", str(repo)])
    assert json.loads(removed.output)["status"] == "removed"
    listed = runner.invoke(cli, ["worktree", "list", "--path", str(repo)])
    assert json.loads(listed.output)["worktrees"] == []
