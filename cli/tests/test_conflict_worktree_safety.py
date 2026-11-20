"""Conflict checks must not delete paths they did not create."""

import subprocess
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from dev_tools.orchestrator import Orchestrator
from dev_tools.utils import CLIError


@pytest.mark.parametrize("resolve", [False, True])
@pytest.mark.parametrize("kind", ["directory", "symlink", "dirty-worktree"])
def test_conflict_setup_preserves_existing_path(tmp_path, monkeypatch, resolve, kind):
    monkeypatch.chdir(tmp_path)
    prefix = "worktree-pr" if resolve else "worktree-conflict"
    target = tmp_path / f"{prefix}-123.tmp"
    if kind == "symlink":
        owner = tmp_path / "owner"
        owner.mkdir()
        target.symlink_to(owner, target_is_directory=True)
    elif kind == "dirty-worktree":
        subprocess.run(["git", "init", "-q", "-b", "main"], check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-qm",
                "base",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "worktree", "add", "-qb", "feature", str(target)], check=True
        )
    else:
        target.mkdir()
    payload = target / "owner.txt"
    payload.write_text("unsaved work\n")
    monkeypatch.setattr(
        "dev_tools.orchestrator.get_config",
        lambda: SimpleNamespace(base_branch_name="main"),
    )
    orch = Orchestrator()
    orch._github = Mock()
    orch._github.fetch_pr_details.return_value = {
        "head": {"ref": "feature"},
        "base": {"ref": "main"},
    }
    calls = []

    def offline_command(args, **_kwargs):
        calls.append(args)
        assert args[:2] == ["git", "fetch"]
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("dev_tools.orchestrator.run_command", offline_command)
    with pytest.raises(CLIError, match="Refusing to overwrite"):
        if resolve:
            orch.resolve_pr_conflicts(123)
        else:
            orch.get_merge_conflicts(123, base_branch="main")
    assert payload.read_text() == "unsaved work\n"
    assert all(args[:2] == ["git", "fetch"] for args in calls)
