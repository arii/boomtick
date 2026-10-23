"""Unit tests for td CLI aliases and defaults ('td audit', 'td pr ...', 'td test')."""
from unittest.mock import patch
from click.testing import CliRunner

from dev_tools.cli import cli


def test_top_level_audit_alias():
    """Test that 'td audit' invokes the audit command."""
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.get_audit_results") as mock_audit:
        mock_audit.return_value = {"audits": [], "score": 100}
        result = runner.invoke(cli, ["audit", "--check-dirs", "cli"])
        assert result.exit_code == 0
        mock_audit.assert_called_once_with(targets=["cli"])


def test_pr_detect_conflicts_alias():
    """Test that 'td pr detect-conflicts' maps to handle_detect_conflicts."""
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.handle_detect_conflicts") as mock_conflicts:
        mock_conflicts.return_value = []
        result = runner.invoke(cli, ["pr", "detect-conflicts", "--pr", "123"])
        assert result.exit_code == 0
        mock_conflicts.assert_called_once_with(pr_num=123, all_prs=False)


def test_pr_read_reviews_alias():
    """Test 'td pr read-reviews' and 'td pr read-pr-reviews' aliases."""
    runner = CliRunner()
    with patch("dev_tools.services.github.GitHubClient.fetch_reviews") as mock_reviews:
        mock_reviews.return_value = []

        res1 = runner.invoke(cli, ["pr", "read-reviews", "--pr-number", "456"])
        assert res1.exit_code == 0

        res2 = runner.invoke(cli, ["pr", "read-pr-reviews", "--pr-number", "456"])
        assert res2.exit_code == 0

        assert mock_reviews.call_count == 2


def test_td_test_without_subcommand():
    """Test that 'td test' runs workspace tests by default."""
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.runtime_check") as mock_check, \
         patch("dev_tools.cli.run_command") as mock_run_cmd:
        result = runner.invoke(cli, ["test"])
        assert result.exit_code == 0
        mock_check.assert_called_once()
        mock_run_cmd.assert_called_once_with(["pnpm", "run", "test"])


def test_td_test_cli_subcommand():
    """Test that 'td test cli' runs CLI package tests."""
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.runtime_check") as mock_check, \
         patch("subprocess.run") as mock_subproc:
        mock_subproc.return_value.returncode = 0
        result = runner.invoke(cli, ["test", "cli"])
        assert result.exit_code == 0
        mock_check.assert_called_once()
        mock_subproc.assert_called_once()
