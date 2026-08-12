# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    with patch("dev_tools.orchestrator.GitHubClient") as mock_gh:
        orch = Orchestrator()
        orch._github = mock_gh.return_value
        yield orch


def test_orchestrator_detect_conflicts_specific_pr(orchestrator):
    with patch.object(orchestrator, "detect_conflicts") as mock_detect:
        mock_detect.return_value = {(1, 2): ["shared.py"]}
        res = orchestrator.handle_detect_conflicts(pr_num=1)
        mock_detect.assert_called_once_with(1)
        assert len(res) == 1
        assert res[0]["prs"] == [1, 2]
        assert res[0]["files"] == ["shared.py"]


def test_orchestrator_detect_conflicts_all_prs(orchestrator):
    with patch.object(orchestrator, "detect_conflicts") as mock_detect:
        mock_detect.return_value = {(1, 2): ["shared.py"], (3, 4): ["other.py"]}
        res = orchestrator.handle_detect_conflicts(all_prs=True)
        mock_detect.assert_called_once_with(None)
        assert len(res) == 2


def test_cli_detect_conflicts_all():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Mock handle_detect_conflicts response
        mock_orch.handle_detect_conflicts.return_value = [
            {"prs": [1, 2], "files": ["shared.py"]}
        ]

        # Invoke CLI command in JSON mode (default)
        result = runner.invoke(cli, ["gh", "detect-conflicts", "--all"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["prs"] == [1, 2]
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None, all_prs=True)


def test_cli_detect_conflicts_specific_pr():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = []

        result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=123, all_prs=False)


def test_cli_detect_conflicts_mutually_exclusive():
    runner = CliRunner()

    result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "123", "--all"])

    assert result.exit_code != 0
    assert "Provide either --pr or --all, not both" in result.output


def test_cli_conflicts_deprecated():
    runner = CliRunner(mix_stderr=False)

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = [
            {"prs": [1, 2], "files": ["shared.py"]}
        ]

        result = runner.invoke(cli, ["gh", "conflicts"])

        assert result.exit_code == 0
        assert "WARNING: 'td-cli gh conflicts' is deprecated" in result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        mock_orch.handle_detect_conflicts.assert_called_once_with(all_prs=True)


def test_cli_detect_conflicts_no_args():
    runner = CliRunner(mix_stderr=False)

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = [
            {"prs": [1, 2], "files": ["shared.py"]}
        ]

        result = runner.invoke(cli, ["gh", "detect-conflicts"])

        assert result.exit_code == 0
        assert "Suggestion: Use 'td-cli gh detect-conflicts --all'" in result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None, all_prs=True)
