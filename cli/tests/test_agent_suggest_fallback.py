from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator
from dev_tools.services.jules import JulesClient


def test_jules_client_init_without_api_key():
    with patch.dict("os.environ", {}, clear=True):
        client = JulesClient()
        assert client.api_key is None
        with pytest.raises(ValueError, match="JULES_API_KEY is not set or empty"):
            _ = client.headers


def test_cli_list_sessions_without_api_key():
    runner = CliRunner()
    with patch.dict("os.environ", {"JULES_API_KEY": ""}):
        result = runner.invoke(cli, ["agent", "list-sessions"])
        assert result.exit_code == 0
        assert '"warning": "JULES_API_KEY unset"' in result.output
        assert '"sessions": []' in result.output


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_suggest_next_action_fast_path():
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": []})
    orch.github.fetch_workflow_runs = MagicMock(return_value=[])
    orch._jules = MagicMock()
    orch.jules.list_sessions = MagicMock(return_value=[])

    res = orch.suggest_next_action()
    assert res["status"] == "success"
    assert res["fast_path"] is True
    assert res["suggestion"] == "SUGGEST: none :: All queues clear and checks green."
    assert res["runnable_command"] is None
    assert res["counts"] == {"open_prs": 0, "failing_runs": 0, "active_sessions": 0}


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_suggest_next_action_with_conflicted_pr():
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": [{"number": 42, "mergeStateStatus": "DIRTY"}]})
    orch.github.fetch_workflow_runs = MagicMock(return_value=[])
    orch._jules = MagicMock()
    orch.jules.list_sessions = MagicMock(return_value=[])

    res = orch.suggest_next_action()
    assert res["status"] == "success"
    assert res["runnable_command"] == "td gh resolve-conflicts --pr 42"


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_suggest_next_action_with_failing_ci():
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": [{"number": 15, "mergeStateStatus": "CLEAN"}]})
    orch.github.fetch_workflow_runs = MagicMock(return_value=[{"conclusion": "failure", "status": "completed"}])
    orch._jules = MagicMock()
    orch.jules.list_sessions = MagicMock(return_value=[])

    res = orch.suggest_next_action()
    assert res["status"] == "success"
    assert res["runnable_command"] == "td --json agent fix-ci --pr 15 --execute"


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_suggest_next_action_with_approved_pr():
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": [{"number": 88, "mergeStateStatus": "CLEAN"}]})
    orch.github.fetch_workflow_runs = MagicMock(return_value=[])
    orch.github.fetch_pr_review_decision = MagicMock(return_value="APPROVED")
    orch._jules = MagicMock()
    orch.jules.list_sessions = MagicMock(return_value=[])

    res = orch.suggest_next_action(repo="owner/repo")
    assert res["status"] == "success"
    assert res["runnable_command"] == "td agent merge-approved -r owner/repo --execute"


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_suggest_next_action_with_changes_requested():
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": [{"number": 99, "mergeStateStatus": "CLEAN"}]})
    orch.github.fetch_workflow_runs = MagicMock(return_value=[])
    orch.github.fetch_pr_review_decision = MagicMock(return_value="CHANGES_REQUESTED")
    orch._jules = MagicMock()
    orch.jules.list_sessions = MagicMock(return_value=[])

    res = orch.suggest_next_action()
    assert res["status"] == "success"
    assert res["runnable_command"] == "td gh read-pr-reviews --pr 99"


def test_cli_agent_suggest():
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.suggest_next_action") as mock_suggest:
        mock_suggest.return_value = {
            "status": "success",
            "suggestion": "SUGGEST: none :: All queues clear and checks green.",
            "fast_path": True,
            "counts": {"open_prs": 0, "failing_runs": 0, "active_sessions": 0},
        }
        result = runner.invoke(cli, ["agent", "suggest"])
        assert result.exit_code == 0
        assert "SUGGEST: none :: All queues clear and checks green." in result.output
