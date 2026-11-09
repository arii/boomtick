# pylint: disable=missing-docstring,line-too-long,protected-access,redefined-outer-name
"""
Tests for `td gh pr-view` and `td gh run-jobs` commands.
Covers CLI option parsing (positional, --pr/--pr-number, --run/--run-id, --repo)
and the orchestrator shaping contracts.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    with (
        patch("dev_tools.orchestrator.GitHubClient"),
        patch("dev_tools.orchestrator.get_config"),
    ):
        orch = Orchestrator()
        orch._github = MagicMock()
        return orch


def _pr_view_payload():
    return {
        "prNumber": 42,
        "title": "Test PR",
        "state": "OPEN",
        "draft": False,
        "reviewDecision": "APPROVED",
        "mergeable": "MERGEABLE",
        "checks": [{"name": "ci", "status": "completed", "conclusion": "success"}],
        "checksSummary": {
            "total": 1,
            "passed": 1,
            "failed": 0,
            "pending": 0,
            "skipped": 0,
        },
    }


def _run_jobs_payload():
    return {
        "runId": 123,
        "totalCount": 1,
        "jobs": [
            {
                "id": 1,
                "name": "build",
                "status": "completed",
                "conclusion": "success",
                "html_url": "http://example.com",
                "steps": [
                    {
                        "number": 1,
                        "name": "checkout",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
            }
        ],
    }


def test_gh_pr_view_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_pr_view_shapen.return_value = _pr_view_payload()

        res_pos = runner.invoke(cli, ["gh", "pr-view", "42"])
        assert res_pos.exit_code == 0, res_pos.output
        assert json.loads(res_pos.output)["status"] == "success"

        res_pr = runner.invoke(cli, ["gh", "pr-view", "--pr", "42"])
        assert res_pr.exit_code == 0, res_pr.output
        assert json.loads(res_pr.output)["prNumber"] == 42

        res_pr_num = runner.invoke(cli, ["gh", "pr-view", "--pr-number", "42"])
        assert res_pr_num.exit_code == 0, res_pr_num.output
        assert json.loads(res_pr_num.output)["reviewDecision"] == "APPROVED"


def test_gh_pr_view_repo_passthrough():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_pr_view_shapen.return_value = _pr_view_payload()

        res = runner.invoke(cli, ["gh", "pr-view", "--pr", "42", "--repo", "org/repo"])
        assert res.exit_code == 0, res.output
        mock_orch.get_pr_view_shapen.assert_called_with(42, repo="org/repo")


def test_gh_pr_view_missing_and_invalid_pr():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_pr_view_shapen.return_value = _pr_view_payload()

        res_missing = runner.invoke(cli, ["gh", "pr-view"])
        assert res_missing.exit_code != 0
        assert json.loads(res_missing.output)["status"] == "error"

        res_invalid = runner.invoke(cli, ["gh", "pr-view", "--pr", "0"])
        assert res_invalid.exit_code != 0
        assert json.loads(res_invalid.output)["status"] == "error"


def test_gh_run_jobs_positional_and_options():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_run_jobs_shapen.return_value = _run_jobs_payload()

        res_pos = runner.invoke(cli, ["gh", "run-jobs", "123"])
        assert res_pos.exit_code == 0, res_pos.output
        assert json.loads(res_pos.output)["status"] == "success"

        res_run = runner.invoke(cli, ["gh", "run-jobs", "--run", "123"])
        assert res_run.exit_code == 0, res_run.output
        assert json.loads(res_run.output)["runId"] == 123

        res_run_id = runner.invoke(cli, ["gh", "run-jobs", "--run-id", "123"])
        assert res_run_id.exit_code == 0, res_run_id.output
        assert len(json.loads(res_run_id.output)["jobs"]) == 1


def test_gh_run_jobs_repo_passthrough():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_run_jobs_shapen.return_value = _run_jobs_payload()

        res = runner.invoke(
            cli, ["gh", "run-jobs", "--run", "123", "--repo", "org/repo"]
        )
        assert res.exit_code == 0, res.output
        mock_orch.get_run_jobs_shapen.assert_called_with(123, repo="org/repo")


def test_gh_run_jobs_missing_and_invalid_run():
    runner = CliRunner()
    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch
        mock_orch.get_run_jobs_shapen.return_value = _run_jobs_payload()

        res_missing = runner.invoke(cli, ["gh", "run-jobs"])
        assert res_missing.exit_code != 0
        assert json.loads(res_missing.output)["status"] == "error"

        res_invalid = runner.invoke(cli, ["gh", "run-jobs", "--run", "0"])
        assert res_invalid.exit_code != 0
        assert json.loads(res_invalid.output)["status"] == "error"


def test_get_pr_view_shapen_contract(orchestrator):
    orchestrator.github.fetch_pr_details.return_value = {
        "title": "Add feature",
        "state": "open",
        "draft": True,
        "mergeable": True,
        "head": {"sha": "abc123"},
    }
    orchestrator.github.fetch_pr_review_decision.return_value = "CHANGES_REQUESTED"
    orchestrator.github.fetch_check_runs.return_value = [
        {"name": "ci", "status": "completed", "conclusion": "success"},
        {"name": "lint", "status": "completed", "conclusion": "failure"},
        {"name": "e2e", "status": "in_progress", "conclusion": None},
        {"name": "docs", "status": "completed", "conclusion": "skipped"},
    ]

    res = orchestrator.get_pr_view_shapen(42)

    assert res["prNumber"] == 42
    assert res["title"] == "Add feature"
    assert res["state"] == "OPEN"
    assert res["draft"] is True
    assert res["reviewDecision"] == "CHANGES_REQUESTED"
    assert res["mergeable"] == "MERGEABLE"
    assert len(res["checks"]) == 4
    assert res["checks"][0] == {
        "name": "ci",
        "status": "completed",
        "conclusion": "success",
    }
    assert res["checksSummary"] == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "pending": 1,
        "skipped": 1,
    }
    orchestrator.github.fetch_check_runs.assert_called_once_with("abc123")


def test_get_pr_view_shapen_mergeable_mapping(orchestrator):
    orchestrator.github.fetch_pr_review_decision.return_value = None
    orchestrator.github.fetch_check_runs.return_value = []

    orchestrator.github.fetch_pr_details.return_value = {
        "title": "t",
        "state": "open",
        "draft": False,
        "mergeable": False,
        "head": {"sha": "s"},
    }
    assert orchestrator.get_pr_view_shapen(1)["mergeable"] == "CONFLICTING"

    orchestrator.github.fetch_pr_details.return_value = {
        "title": "t",
        "state": "open",
        "draft": False,
        "mergeable": None,
        "head": {"sha": "s"},
    }
    assert orchestrator.get_pr_view_shapen(1)["mergeable"] == "UNKNOWN"


def test_get_pr_view_shapen_no_head_sha_skips_checks(orchestrator):
    orchestrator.github.fetch_pr_details.return_value = {
        "title": "t",
        "state": "closed",
        "draft": False,
        "mergeable": True,
        "head": {},
    }
    orchestrator.github.fetch_pr_review_decision.return_value = None

    res = orchestrator.get_pr_view_shapen(7)

    assert res["checks"] == []
    assert res["checksSummary"] == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pending": 0,
        "skipped": 0,
    }
    orchestrator.github.fetch_check_runs.assert_not_called()


def test_get_pr_view_shapen_repo_passthrough(orchestrator):
    orchestrator.github.fetch_pr_details.return_value = {
        "title": "t",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "head": {"sha": "s"},
    }
    orchestrator.github.fetch_pr_review_decision.return_value = None
    orchestrator.github.fetch_check_runs.return_value = []

    orchestrator.get_pr_view_shapen(9, repo="org/repo")

    orchestrator.github.fetch_pr_details.assert_called_once_with(9, repo="org/repo")
    orchestrator.github.fetch_pr_review_decision.assert_called_once_with(
        9, repo="org/repo"
    )
    orchestrator.github.fetch_check_runs.assert_called_once_with("s", repo="org/repo")


def test_get_run_jobs_shapen_contract(orchestrator):
    orchestrator.github.fetch_workflow_run_jobs.return_value = [
        {
            "id": 1,
            "name": "build",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "http://example.com/job/1",
            "steps": [
                {
                    "number": 1,
                    "name": "checkout",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "number": 2,
                    "name": "test",
                    "status": "completed",
                    "conclusion": "failure",
                },
            ],
        }
    ]

    res = orchestrator.get_run_jobs_shapen(123)

    assert res["runId"] == 123
    assert res["totalCount"] == 1
    assert len(res["jobs"]) == 1
    job = res["jobs"][0]
    assert job["name"] == "build"
    assert job["conclusion"] == "failure"
    assert job["htmlUrl"] == "http://example.com/job/1"
    assert len(job["steps"]) == 2
    assert job["steps"][1]["name"] == "test"


def test_get_run_jobs_shapen_empty_and_repo_passthrough(orchestrator):
    orchestrator.github.fetch_workflow_run_jobs.return_value = []

    res = orchestrator.get_run_jobs_shapen(999, repo="org/repo")

    assert res["runId"] == 999
    assert res["totalCount"] == 0
    assert res["jobs"] == []
    orchestrator.github.fetch_workflow_run_jobs.assert_called_once_with(
        999, repo="org/repo"
    )
