# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner
from dev_tools.cli import cli


def test_cli_issue_view_positional():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Mock get_issue_details response
        mock_orch.get_issue_details.return_value = {
            "number": 123,
            "title": "Bug in issue-view",
            "html_url": "https://github.com/owner/repo/issues/123",
            "state": "open",
            "body": "This is a bug report body.",
        }

        # Invoke CLI with positional argument
        result = runner.invoke(cli, ["gh", "issue-view", "123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["issue"]["number"] == 123
        assert data["issue"]["title"] == "Bug in issue-view"
        mock_orch.get_issue_details.assert_called_once_with(123)


def test_cli_issue_view_flag():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.get_issue_details.return_value = {
            "number": 123,
            "title": "Bug in issue-view",
            "html_url": "https://github.com/owner/repo/issues/123",
            "state": "open",
            "body": "This is a bug report body.",
        }

        # Invoke CLI with --issue-number flag
        result = runner.invoke(cli, ["gh", "issue-view", "--issue-number", "123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["issue"]["number"] == 123
        mock_orch.get_issue_details.assert_called_once_with(123)


def test_cli_issue_view_missing():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Invoke CLI with no arguments
        result = runner.invoke(cli, ["gh", "issue-view"])

        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "Provide --issue-number or a positional issue number" in data["message"]
        mock_orch.get_issue_details.assert_not_called()
