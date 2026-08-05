# pylint: disable=missing-docstring,protected-access,redefined-outer-name
from unittest.mock import patch, MagicMock
import json
from click.testing import CliRunner
from dev_tools.cli import cli


def test_cli_detect_conflicts_all():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Mock handle_detect_conflicts response
        mock_orch.handle_detect_conflicts.return_value = [
            {
                "prs": [101, 102],
                "files": ["src/index.ts"]
            }
        ]

        # Invoke CLI command with --all
        result = runner.invoke(cli, ["gh", "detect-conflicts", "--all"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["prs"] == [101, 102]
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None)


def test_cli_detect_conflicts_pr():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = []

        # Invoke CLI command with --pr
        result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "101"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=101)


def test_cli_detect_conflicts_none():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = []

        # Invoke CLI command with no options
        result = runner.invoke(cli, ["gh", "detect-conflicts"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None)


def test_cli_detect_conflicts_both_mutually_exclusive():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Invoke CLI command with both --pr and --all (should fail)
        result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "101", "--all"])

        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "Cannot specify both --pr and --all options." in data["message"]
        mock_orch.handle_detect_conflicts.assert_not_called()
