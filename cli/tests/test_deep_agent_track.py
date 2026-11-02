# pylint: disable=missing-docstring,protected-access,unused-argument
"""Deep-agent track: td commands the deep agent relies on must exist and work.

Covers:
- `td jules list-sessions` (alias used by remote-server deep-agent fallbacks)
- `td agent dispatch --prompt/--branch` (flag form used by buttons/server.py)
- `td preflight` repo-awareness (audit skip, base-ref discovery)
"""
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


def test_cli_jules_list_sessions_without_api_key():
    runner = CliRunner()
    with patch.dict("os.environ", {"JULES_API_KEY": ""}):
        result = runner.invoke(cli, ["jules", "list-sessions"])
        assert result.exit_code == 0
        assert '"warning": "JULES_API_KEY unset"' in result.output
        assert '"sessions": []' in result.output


def test_cli_jules_list_sessions_matches_agent():
    runner = CliRunner()
    with patch.dict("os.environ", {"JULES_API_KEY": ""}):
        agent_res = runner.invoke(cli, ["agent", "list-sessions"])
        jules_res = runner.invoke(cli, ["jules", "list-sessions"])
        assert agent_res.exit_code == 0
        assert jules_res.exit_code == 0
        assert jules_res.output == agent_res.output


@patch("dev_tools.orchestrator.Orchestrator.dispatch_jules_review")
def test_cli_agent_dispatch_with_prompt_and_branch_flags(mock_dispatch):
    mock_dispatch.return_value = {"name": "sessions/777", "title": "Flag task"}
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["agent", "dispatch", "--prompt", "Do the thing", "--branch", "main"],
        obj={},
    )
    assert result.exit_code == 0
    mock_dispatch.assert_called_once_with("main", "Do the thing", title=None, repo=None)


@patch("dev_tools.orchestrator.Orchestrator.dispatch_jules_review")
def test_cli_agent_dispatch_missing_branch_and_task_errors(mock_dispatch):
    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "dispatch", "--prompt", "No branch"], obj={})
    assert result.exit_code != 0
    mock_dispatch.assert_not_called()


def test_preflight_skips_audit_when_dirs_missing():
    orch = Orchestrator()
    with patch.object(orch, "doctor_check", return_value={"status": "success"}), \
         patch.object(orch, "detect_conflicts", return_value={}), \
         patch.object(orch, "_pnpm_has_script", return_value=False), \
         patch("dev_tools.orchestrator.run_command",
               return_value=MagicMock(returncode=0, stdout="clean")), \
         patch("os.path.exists", return_value=False):
        res = orch.run_preflight(base_branch="main")
    assert res["audit"]["status"] == "skipped"
    assert res["status"] == "success"


def test_preflight_skips_merge_simulation_when_no_base_ref():
    orch = Orchestrator()

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        if cmd[:2] == ["git", "rev-parse"]:
            result.returncode = 1  # no base ref verifies
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = "clean"
        return result

    with patch.object(orch, "doctor_check", return_value={"status": "success"}), \
         patch.object(orch, "get_audit_results", return_value={"violations": {}}), \
         patch.object(orch, "detect_conflicts", return_value={}), \
         patch.object(orch, "_pnpm_has_script", return_value=False), \
         patch("dev_tools.orchestrator.run_command", side_effect=fake_run):
        res = orch.run_preflight(base_branch="nonexistent-base")
    assert res["merge_simulation"]["status"] == "skipped"
    assert res["status"] == "success"
