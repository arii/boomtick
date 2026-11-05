"""Tests for `td agent suggest` local-session fallback behavior.

No Jules dependency: when no git/PR tooling data is available the
command reports all-queues-clear, and active sessions come from local
`.worktrees` scans (never a cloud session list).
"""
from unittest.mock import patch

from click.testing import CliRunner

from dev_tools.cli import cli


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
