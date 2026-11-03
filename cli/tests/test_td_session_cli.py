# pylint: disable=missing-docstring,line-too-long
"""CliRunner tests for td agent run / session / skill (local, no Jules)."""
import json
import os
import subprocess
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dev_tools.cli import cli


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "README.md").write_text("hi\n")
    _git(["add", "."], root)
    _git(["commit", "-qm", "init"], root)
    wt = root / ".worktrees" / "wt1"
    wt.mkdir(parents=True)
    _git(["init", "-q"], wt)
    skills = root / ".agents" / "skills" / "eco"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# eco\n")
    return root


def _payload(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_agent_run_bookkeeping_only(repo, monkeypatch):
    monkeypatch.setenv("BOOMTICK_SESSION_EXEC", "0")
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "run",
                                 "--worktree", str(repo / ".worktrees" / "wt1"),
                                 "--brief", "do it",
                                 "--path", str(repo)])
    payload = _payload(result)
    assert payload["status"] == "success"
    assert payload["executed"] is False
    assert payload["session"]["lastCheckpoint"] == "worktree_setup"
    assert payload["session"]["state"] == "running"


def test_agent_run_missing_worktree(repo):
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "run",
                                 "--worktree", str(repo / "nope"),
                                 "--brief", "do it",
                                 "--path", str(repo)])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_agent_run_foreground_fake_executor(repo, monkeypatch):
    monkeypatch.setenv("BOOMTICK_EXECUTOR_CLI", "echo")
    monkeypatch.delenv("BOOMTICK_SESSION_EXEC", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "run",
                                 "--worktree", str(repo / ".worktrees" / "wt1"),
                                 "--brief", "hello agent",
                                 "--path", str(repo)])
    payload = _payload(result)
    assert payload["exit_code"] == 0
    assert payload["session"]["state"] == "done"


def test_agent_run_detach_spawns_supervisor(repo, monkeypatch):
    monkeypatch.delenv("BOOMTICK_SESSION_EXEC", raising=False)
    runner = CliRunner()
    with patch("dev_tools.services.local_sessions.spawn_detached",
               return_value=4242) as spawn:
        result = runner.invoke(cli, ["agent", "run",
                                     "--worktree",
                                     str(repo / ".worktrees" / "wt1"),
                                     "--brief", "later",
                                     "--detach",
                                     "--path", str(repo)])
    payload = _payload(result)
    assert payload["supervisor_pid"] == 4242
    assert payload["session"]["state"] == "running"
    spawn.assert_called_once()


def _run_session(repo, monkeypatch, brief="work"):
    monkeypatch.setenv("BOOMTICK_SESSION_EXEC", "0")
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "run",
                                 "--worktree", str(repo / ".worktrees" / "wt1"),
                                 "--brief", brief,
                                 "--path", str(repo)])
    return _payload(result)["session"]["sessionId"]


def test_session_status_and_logs_round_trip(repo, monkeypatch):
    sid = _run_session(repo, monkeypatch)
    runner = CliRunner()
    status = runner.invoke(cli, ["session", "status", sid,
                                 "--path", str(repo)])
    payload = _payload(status)
    assert payload["session"]["sessionId"] == sid
    assert payload["session"]["state"] == "running"
    logs = runner.invoke(cli, ["session", "logs", sid, "--tail", "5",
                               "--path", str(repo)])
    payload = _payload(logs)
    assert payload["sessionId"] == sid
    assert payload["totalLines"] >= 1
    assert len(payload["logs"]) <= 5


def test_session_status_missing(repo):
    runner = CliRunner()
    result = runner.invoke(cli, ["session", "status", "sess_nope",
                                 "--path", str(repo)])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_skill_list_and_read(repo):
    runner = CliRunner()
    listed = runner.invoke(cli, ["skill", "list", "--path", str(repo)])
    assert _payload(listed)["skills"] == ["eco"]
    read = runner.invoke(cli, ["skill", "read", "eco",
                               "--path", str(repo)])
    payload = _payload(read)
    assert payload["skill"] == "eco"
    assert payload["content"] == "# eco\n"


def test_skill_read_missing(repo):
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "read", "nope",
                                 "--path", str(repo)])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_no_jules_key_needed(repo, monkeypatch):
    """Draft 4 acceptance: local run works with the Jules key unset."""
    monkeypatch.delenv("JULES_API_KEY", raising=False)
    monkeypatch.setenv("BOOMTICK_SESSION_EXEC", "0")
    for var in [k for k in os.environ if "JULES" in k]:
        monkeypatch.delenv(var, raising=False)
    sid = _run_session(repo, monkeypatch)
    assert sid.startswith("sess_")
