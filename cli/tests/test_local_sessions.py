# pylint: disable=missing-docstring,line-too-long
"""Unit tests for local worktree session + skill parity (no Jules, no network)."""
import json
import os
import subprocess

import pytest

from dev_tools.services import local_sessions as ls


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
    return root


@pytest.fixture()
def worktree(repo):
    wt = repo / ".worktrees" / "wt1"
    wt.mkdir(parents=True)
    _git(["init", "-q"], wt)
    return wt


def _session_in(worktree, **over):
    session = ls.new_session(str(worktree), "do the thing", **over)
    ls.save_session(session)
    return session


def test_new_session_schema_matches_mcp(repo, worktree):
    session = ls.new_session(str(worktree), "brief text", model="m1",
                             repo="o/r")
    assert session["sessionId"].startswith("sess_")
    assert session["state"] == "running"
    assert session["status"] == "running"
    assert session["lastCheckpoint"] == "worktree_setup"
    assert session["brief"] == "brief text"
    assert session["model"] == "m1"
    assert session["repo"] == "o/r"
    assert session["retries"] == 0 and session["maxRetries"] == 3
    assert session["transcript"] and session["logs"]
    assert session["lastVerification"] is None
    assert session["worktreePath"] == str(worktree)


def test_save_load_round_trip(repo, worktree):
    session = _session_in(worktree)
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["brief"] == "do the thing"
    assert loaded["worktreePath"] == str(worktree)


def test_load_missing_raises(repo):
    with pytest.raises(ls.SessionNotFound):
        ls.load_session(str(repo), "sess_deadbeefcafe")


def test_scan_ignores_corrupt_and_non_dirs(repo, worktree):
    good = _session_in(worktree)
    bad_dir = repo / ".worktrees" / "bad"
    bad_dir.mkdir()
    (bad_dir / "session.json").write_text("{not json")
    (repo / ".worktrees" / "stray.json").write_text("{}")
    found = ls.scan_sessions(str(repo))
    assert [s["sessionId"] for s in found] == [good["sessionId"]]


def test_update_checkpoint_persists(repo, worktree):
    session = _session_in(worktree)
    ls.update_checkpoint(session, "executing", "running")
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["lastCheckpoint"] == "executing"
    assert loaded["state"] == "running"


def test_append_lines_caps_at_2000(repo, worktree):
    session = _session_in(worktree)
    session["logs"] = []
    ls.append_lines(session, [f"l{i}" for i in range(2005)])
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert len(loaded["logs"]) == 2001
    assert loaded["logs"][-1] == "[exec] log truncated: line cap reached"


def test_tail_logs(repo, worktree):
    session = _session_in(worktree)
    session["logs"] = [f"l{i}" for i in range(10)]
    lines, total = ls.tail_logs(session, 3)
    assert (lines, total) == (["l7", "l8", "l9"], 10)
    lines, total = ls.tail_logs(session, 0)
    assert (lines, total) == ([], 10)


def test_changed_files_parses_porcelain(repo, worktree):
    (worktree / "new.txt").write_text("x")
    (worktree / "README.md").write_text("changed")
    _git(["add", "."], worktree)
    names = ls.changed_files(str(worktree))
    assert sorted(names) == ["README.md", "new.txt"]


def test_changed_files_keeps_first_line_xy_space(repo, worktree):
    # Unstaged-only change: first porcelain line is " M ..." and the
    # leading XY space must survive (regression: strip() ate it and
    # the fallback slice truncated the path).
    (worktree / "README.md").write_text("changed-unstaged")
    names = ls.changed_files(str(worktree))
    assert "README.md" in names
    assert not any(n == "EADME.md" for n in names)


def test_status_summary_shape(repo, worktree):
    session = _session_in(worktree)
    summary = ls.status_summary(session)
    assert summary["sessionId"] == session["sessionId"]
    assert summary["state"] == "running"
    assert summary["lastCheckpoint"] == "worktree_setup"
    assert summary["changedFiles"] == ["session.json"]
    assert summary["lastVerification"] is None


def test_exec_disabled_skips_spawn(repo, worktree, monkeypatch):
    monkeypatch.setenv("BOOMTICK_SESSION_EXEC", "0")
    session = _session_in(worktree)
    assert ls.run_executor(str(repo), session) is None
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["lastCheckpoint"] == "worktree_setup"


def test_run_executor_success_and_logs(repo, worktree, monkeypatch):
    monkeypatch.setenv("BOOMTICK_EXECUTOR_CLI", "echo")
    monkeypatch.delenv("BOOMTICK_SESSION_EXEC", raising=False)
    session = _session_in(worktree)
    seen = []
    code = ls.run_executor(str(repo), session, stream=seen.append)
    assert code == 0
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["state"] == "done"
    assert loaded["lastCheckpoint"] == "execution_done"
    assert any("do the thing" in line for line in loaded["logs"])
    assert seen, "stream callback receives live lines"


def test_run_executor_failure_checkpoint(repo, worktree, monkeypatch):
    monkeypatch.setenv("BOOMTICK_EXECUTOR_CLI", "false")
    monkeypatch.delenv("BOOMTICK_SESSION_EXEC", raising=False)
    session = _session_in(worktree)
    code = ls.run_executor(str(repo), session)
    assert code != 0
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["state"] == "failed"
    assert loaded["lastCheckpoint"] == "execution_failed"


def test_run_executor_spawn_failure(repo, worktree, monkeypatch):
    monkeypatch.setenv("BOOMTICK_EXECUTOR_CLI", "/nonexistent-cli-xyz")
    monkeypatch.delenv("BOOMTICK_SESSION_EXEC", raising=False)
    session = _session_in(worktree)
    code = ls.run_executor(str(repo), session)
    assert code == 127
    loaded = ls.load_session(str(repo), session["sessionId"])
    assert loaded["state"] == "failed"


def test_executor_command_env_knobs(repo, worktree, monkeypatch):
    monkeypatch.setenv("BOOMTICK_EXECUTOR_CLI", "mycli")
    monkeypatch.setenv("BOOMTICK_EXECUTOR_MODEL", "m9")
    session = ls.new_session(str(worktree), "b")
    cli, args = ls.executor_command(session)
    assert cli == "mycli"
    assert args[:2] == ["-p", "--system-prompt"]
    assert "--model" in args and "m9" in args
    assert args[-1] == "b"


def test_executor_defaults_to_s5_coder(repo, worktree, monkeypatch):
    monkeypatch.delenv("BOOMTICK_EXECUTOR_CLI", raising=False)
    monkeypatch.delenv("BOOMTICK_EXECUTOR_MODEL", raising=False)
    session = ls.new_session(str(worktree), "b")
    cli, args = ls.executor_command(session)
    assert cli == "s5-coder"
    assert args[:2] == ["-p", "--system-prompt"]
    assert args[-1] == "b"


def test_system_prompt_carries_contract_and_brief(repo, worktree):
    agents = worktree / ".agents"
    agents.mkdir()
    (agents / "AGENT_CONTRACT.md").write_text("CONTRACT\n")
    prompt = ls.build_system_prompt(str(worktree), "the brief")
    assert "CONTRACT" in prompt and "the brief" in prompt


def test_list_skills_only_with_skill_md(repo):
    base = repo / ".agents" / "skills"
    (base / "eco").mkdir(parents=True)
    (base / "eco" / "SKILL.md").write_text("# eco")
    (base / "empty").mkdir()
    assert ls.list_skills(str(repo)) == ["eco"]
    assert ls.list_skills(str(repo / "nope")) == []


def test_read_skill_round_trip(repo):
    base = repo / ".agents" / "skills" / "eco"
    base.mkdir(parents=True)
    (base / "SKILL.md").write_text("# eco\nbody\n")
    assert ls.read_skill(str(repo), "eco") == "# eco\nbody\n"


def test_read_skill_missing_and_traversal(repo):
    with pytest.raises(ls.SkillNotFound):
        ls.read_skill(str(repo), "nope")
    with pytest.raises(ls.SkillNotFound):
        ls.read_skill(str(repo), "../..")


def test_repo_root_prefers_main_with_worktrees(repo):
    wt_dir = repo / ".worktrees"
    wt_dir.mkdir()
    assert ls.repo_root_for(str(repo)) == str(repo)


def test_system_prompt_starts_with_mandatory_protocol(repo, worktree):
    prompt = ls.build_system_prompt(str(worktree), "the brief")
    assert prompt.startswith("[MANDATORY LOW-TOKEN PROTOCOL FOR CLI AGENTS]")
    assert "td init-and-rag" in prompt
    assert "td verify-scope" in prompt
    assert "the brief" in prompt
