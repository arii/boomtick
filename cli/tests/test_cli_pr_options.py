# pylint: disable=missing-docstring,line-too-long
"""
Tests for PR option standardization across `td gh` and other CLI subcommands.
Verifies that both --pr and --pr-number (and positional args where supported)
are accepted without CLI parsing errors.
"""

import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from dev_tools.cli import cli


def test_gh_list_pr_commits_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.github.fetch_pr_commits.return_value = []

        res_pr = runner.invoke(cli, ["gh", "list-pr-commits", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output
        assert json.loads(res_pr.output)["status"] == "success"

        res_pr_num = runner.invoke(cli, ["gh", "list-pr-commits", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output
        assert json.loads(res_pr_num.output)["status"] == "success"


def test_gh_read_pr_reviews_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.github.fetch_reviews.return_value = []

        res_pr = runner.invoke(cli, ["gh", "read-pr-reviews", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "read-pr-reviews", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_read_pr_comments_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_pr_comments.return_value = {"pr": {"number": 42, "title": "Test PR"}, "comments": [], "review_comments": []}

        res_pr = runner.invoke(cli, ["gh", "read-pr-comments", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "read-pr-comments", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_post_comment_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.post_comment.return_value = {"id": 123}

        res_pr = runner.invoke(cli, ["gh", "post-comment", "--pr", "42", "--body", "hello"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "post-comment", "--pr-number", "42", "--body", "hello"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_detect_conflicts_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.handle_detect_conflicts.return_value = []

        res_pr = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "detect-conflicts", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_resolve_conflicts_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.resolve_pr_conflicts.return_value = {"message": "Resolved"}

        res_pr = runner.invoke(cli, ["gh", "resolve-conflicts", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "resolve-conflicts", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_track_review_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.track_review.return_value = {"status": "ok"}

        res_pr = runner.invoke(cli, ["gh", "track-review", "--pr", "42", "--status", "approved", "--auditor", "jules"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "track-review", "--pr-number", "42", "--status", "approved", "--auditor", "jules"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_merge_conflicts_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_merge_conflicts.return_value = {"has_conflicts": False}

        res_pos = runner.invoke(cli, ["gh", "merge-conflicts", "42"])
        assert res_pos.exit_code == 0, res_pos.output

        res_pr = runner.invoke(cli, ["gh", "merge-conflicts", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "merge-conflicts", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_pr_diff_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_pr_diff_shapen.return_value = {"diff": ""}

        res_pos = runner.invoke(cli, ["gh", "pr-diff", "42"])
        assert res_pos.exit_code == 0, res_pos.output

        res_pr = runner.invoke(cli, ["gh", "pr-diff", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "pr-diff", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_sync_pr_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.sync_pr.return_value = {"message": "Synced"}

        res_pos = runner.invoke(cli, ["gh", "sync-pr", "42"])
        assert res_pos.exit_code == 0, res_pos.output

        res_pr = runner.invoke(cli, ["gh", "sync-pr", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "sync-pr", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_gh_view_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.github.fetch_pr_details.return_value = {"number": 42, "title": "PR Title", "state": "OPEN"}

        res_pos = runner.invoke(cli, ["gh", "view", "42"])
        assert res_pos.exit_code == 0, res_pos.output

        res_pr = runner.invoke(cli, ["gh", "view", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["gh", "view", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_ai_comment_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.handle_comment_command.return_value = {"message": "Done"}

        res_pr = runner.invoke(cli, ["ai", "comment", "--pr", "42", "--command", "review"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["ai", "comment", "--pr-number", "42", "--command", "review"])
        assert res_pr_num.exit_code == 0, res_pr_num.output


def test_agent_plan_review_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.generate_review_workflow.return_value = {"plan_path": "/tmp/plan"}

        res_pr = runner.invoke(cli, ["agent", "plan-review", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output

        res_pr_num = runner.invoke(cli, ["agent", "plan-review", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output
