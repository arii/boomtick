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
    out = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
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
    created = runner.invoke(
        cli, ["worktree", "create", "cli-demo", "--path", str(repo)]
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["branch"] == "cli-demo"
    wid = payload["worktreeId"]
    listed = runner.invoke(cli, ["worktree", "list", "--path", str(repo)])
    assert json.loads(listed.output)["worktrees"][0]["worktreeId"] == wid
    removed = runner.invoke(cli, ["worktree", "remove", wid, "--path", str(repo)])
    assert json.loads(removed.output)["status"] == "removed"
    listed = runner.invoke(cli, ["worktree", "list", "--path", str(repo)])
    assert json.loads(listed.output)["worktrees"] == []


@pytest.fixture()
def origin_repo(tmp_path):
    root = tmp_path / "origin-repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "README.md").write_text("hi\n")
    _git(["add", "."], root)
    _git(["commit", "-qm", "init"], root)
    _git(["remote", "add", "origin", str(root)], root)
    _git(["fetch", "-q", "origin"], root)
    return root


def test_create_for_issue_provisions_branch(origin_repo):
    status = wt.create_for_issue(str(origin_repo), 42)
    assert status["worktreeId"] == "issue-42"
    assert status["branch"] == "agent/issue-42"
    assert status["path"] == str(origin_repo / ".worktrees" / "issue-42")
    out = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=status["path"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "agent/issue-42"
    assert status["base_sha"]
    assert "linked_deps" in status


def test_create_for_issue_rejects_bad_id(origin_repo):
    with pytest.raises(wt.WorktreeError, match="Invalid issue id"):
        wt.create_for_issue(str(origin_repo), "nope")
    with pytest.raises(wt.WorktreeError, match="already exists"):
        wt.create_for_issue(str(origin_repo), 7)
        wt.create_for_issue(str(origin_repo), 7)


def test_link_warm_deps_symlinks_missing_only(tmp_path):
    import os

    root = tmp_path / "root"
    wt_dir = tmp_path / "wt"
    root.mkdir()
    wt_dir.mkdir()
    (root / "node_modules").mkdir()
    (wt_dir / ".venv").mkdir()
    linked = wt.link_warm_deps(str(root), str(wt_dir))
    assert linked == ["node_modules"]
    assert os.path.islink(str(wt_dir / "node_modules"))
    # Second run links nothing new (already exists).
    assert wt.link_warm_deps(str(root), str(wt_dir)) == []


def test_remove_abandons_bound_sessions(repo):
    # #1139 item 3: removal abandons bound sessions via local_sessions
    # (single owner) before unregistering the worktree.
    from unittest.mock import patch
    from dev_tools.services import local_sessions as ls

    wid, path, _branch = wt.create(str(repo), "demo")
    with patch.object(
        ls, "abandon_sessions_in_worktree", return_value=["sess_x"]
    ) as abandon:
        wt.remove(str(repo), wid)
    abandon.assert_called_once_with(str(repo), path)


def test_fetch_main_reports_state(origin_repo):
    _updated, _sha, note = wt.fetch_main(str(origin_repo))
    assert isinstance(note, str) and note


def _clone_to(tmp_path, origin_repo, name):
    work = tmp_path / name
    subprocess.run(
        ["git", "clone", "-q", str(origin_repo), str(work)],
        cwd=str(tmp_path),
        capture_output=True,
        check=True,
    )
    _git(["config", "user.email", "t@t"], work)
    _git(["config", "user.name", "t"], work)
    return work


def _rev(root, ref):
    out = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _advance_origin(origin_repo):
    (origin_repo / "bump.txt").write_text("bump\n")
    _git(["add", "."], origin_repo)
    _git(["commit", "-qm", "bump"], origin_repo)


def test_fast_forward_main_ref_without_checkout(tmp_path, origin_repo):
    # #1139 item 6: local main advances through the checked-worktree guard while a feature
    # branch (not main) is checked out; the feature branch is untouched.
    work = _clone_to(tmp_path, origin_repo, "work")
    stale_main = _rev(work, "refs/heads/main")
    _git(["checkout", "-qb", "feature"], work)
    _advance_origin(origin_repo)
    updated, note = wt.fast_forward_main_ref(str(work))
    assert updated is True
    assert _rev(work, "refs/heads/main") == _rev(origin_repo, "HEAD") != stale_main
    assert _rev(work, "HEAD") != _rev(work, "refs/heads/main")
    assert "main ref" in note


def test_fast_forward_main_ref_refuses_diverged(tmp_path, origin_repo):
    work = _clone_to(tmp_path, origin_repo, "work2")
    _git(["checkout", "-qb", "feature"], work)
    _advance_origin(origin_repo)
    (work / "local.txt").write_text("local\n")
    _git(["checkout", "-q", "main"], work)
    _git(["add", "."], work)
    _git(["commit", "-qm", "local-diverged"], work)
    _git(["checkout", "-q", "feature"], work)
    updated, note = wt.fast_forward_main_ref(str(work))
    assert updated is False
    assert "diverged" in note


def test_cli_create_issue(origin_repo):
    runner = CliRunner()
    created = runner.invoke(
        cli,
        [
            "worktree",
            "create",
            "--issue",
            "99",
            "--repo-root",
            str(origin_repo),
            "--json",
        ],
    )
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["worktreeId"] == "issue-99"
    assert payload["status"] == "ready"


@pytest.mark.parametrize("dirty", [False, True])
def test_fast_forward_main_ref_preserves_main_in_another_worktree(
    tmp_path, origin_repo, dirty
):
    work = _clone_to(tmp_path, origin_repo, "main-work")
    feature = tmp_path / "feature-work"
    _git(["worktree", "add", "-q", "-b", "feature", str(feature)], work)
    if dirty:
        (work / "README.md").write_text("owner edits\n")
    old_head = _rev(work, "HEAD")
    before_status = subprocess.check_output(["git", "status", "--porcelain"], cwd=work)
    before_files = {p.name: p.read_bytes() for p in work.iterdir() if p.is_file()}
    _advance_origin(origin_repo)
    updated, note = wt.fast_forward_main_ref(str(feature))
    assert updated is False
    assert "checked out in another worktree" in note
    assert _rev(work, "HEAD") == old_head
    assert (
        subprocess.check_output(["git", "status", "--porcelain"], cwd=work)
        == before_status
    )
    assert {
        p.name: p.read_bytes() for p in work.iterdir() if p.is_file()
    } == before_files


def test_fast_forward_main_ref_fails_closed_on_worktree_check(
    tmp_path, origin_repo, monkeypatch
):
    work = _clone_to(tmp_path, origin_repo, "fail-work")
    _git(["checkout", "-qb", "feature"], work)
    old_main = _rev(work, "refs/heads/main")
    _advance_origin(origin_repo)
    real_git = wt._git

    def checked_git(args, root):
        if args[:2] == ["worktree", "list"]:
            return subprocess.CompletedProcess(args, 1, "", "cannot enumerate")
        return real_git(args, root)

    monkeypatch.setattr(wt, "_git", checked_git)
    updated, note = wt.fast_forward_main_ref(str(work))
    assert updated is False
    assert "could not verify" in note
    assert _rev(work, "refs/heads/main") == old_main


def test_fast_forward_main_ref_updates_current_clean_main(tmp_path, origin_repo):
    work = _clone_to(tmp_path, origin_repo, "current-main")
    _advance_origin(origin_repo)
    updated, _note = wt.fast_forward_main_ref(str(work))
    assert updated is True
    assert _rev(work, "HEAD") == _rev(origin_repo, "HEAD")
    assert (work / "bump.txt").read_text() == "bump\n"
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=work) == b""


def test_remove_refuses_unknown_status_before_effects(repo, monkeypatch):
    wid, path, _branch = wt.create(str(repo), "status-failure")
    dirty = __import__("pathlib").Path(path) / "owner.txt"
    dirty.write_text("unsaved edits\n")
    real_git = wt._git
    calls = []

    def failed_status(args, root):
        calls.append(args)
        if args[:2] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 1, "", "status unavailable")
        return real_git(args, root)

    def no_abandon(*_args):
        pytest.fail("sessions must not be abandoned on unknown dirtiness")

    monkeypatch.setattr(wt, "_git", failed_status)
    monkeypatch.setattr(wt.local_sessions, "abandon_sessions_in_worktree", no_abandon)
    with pytest.raises(wt.WorktreeError, match="Cannot verify"):
        wt.remove(str(repo), wid)
    assert dirty.read_text() == "unsaved edits\n"
    assert calls == [["status", "--porcelain"]]


def test_remove_rechecks_dirtiness_in_git(repo, monkeypatch):
    wid, path, _branch = wt.create(str(repo), "dirty-race")
    dirty = __import__("pathlib").Path(path) / "owner.txt"
    real_git = wt._git

    def concurrent_edit(args, root):
        if args[:2] == ["worktree", "remove"]:
            assert "--force" not in args
            dirty.write_text("new edits after precheck\n")
        return real_git(args, root)

    def no_abandon(*_args):
        pytest.fail("sessions must remain active when Git refuses removal")

    monkeypatch.setattr(wt.local_sessions, "abandon_sessions_in_worktree", no_abandon)
    monkeypatch.setattr(wt, "_git", concurrent_edit)
    with pytest.raises(wt.WorktreeError, match="git worktree remove failed"):
        wt.remove(str(repo), wid)
    assert dirty.read_text() == "new edits after precheck\n"
