# pylint: disable=missing-docstring,protected-access,redefined-outer-name,import-outside-toplevel
import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli, PROJECT_CONFIG
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    with patch("dev_tools.orchestrator.GitHubClient") as mock_gh:
        orch = Orchestrator()
        orch._github = mock_gh.return_value
        yield orch


def test_orchestrator_list_issues(orchestrator):
    # Mock GitHubClient.list_issues
    mock_issues = [
        {
            "number": 42,
            "title": "Bug: Something is broken",
            "html_url": "https://github.com/owner/repo/issues/42",
            "state": "open",
        },
        {
            "number": 43,
            "title": "Feature: Add something",
            "html_url": "https://github.com/owner/repo/issues/43",
            "state": "closed",
        },
    ]
    orchestrator.github.list_issues.return_value = mock_issues

    res = orchestrator.list_issues(state="all", limit=5, labels=["bug"])

    orchestrator.github.list_issues.assert_called_once_with(state="all", limit=5, labels=["bug"])
    assert res["status"] == "success"
    assert len(res["issues"]) == 2
    assert res["issues"][0]["number"] == 42
    assert res["issues"][0]["title"] == "Bug: Something is broken"
    assert res["issues"][1]["number"] == 43


def test_cli_search_issues():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Mock list_issues response
        mock_orch.list_issues.return_value = {
            "status": "success",
            "issues": [
                {
                    "number": 1,
                    "title": "Issue 1",
                    "html_url": "https://url/1",
                    "state": "open",
                }
            ],
        }

        # Invoke CLI command in JSON mode (default)
        result = runner.invoke(cli, ["gh", "search-issues", "--state", "open", "--limit", "10", "--labels", "bug,high"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert len(data["issues"]) == 1
        assert data["issues"][0]["number"] == 1
        mock_orch.list_issues.assert_called_once_with(state="open", limit=10, labels=["bug", "high"])

        # Reset mock and try human-readable format via --no-json flag
        mock_orch.reset_mock()
        result_no_json = runner.invoke(cli, ["--no-json", "gh", "search-issues", "--state", "closed"])

        assert result_no_json.exit_code == 0
        assert "Found 1 issues." in result_no_json.output
        mock_orch.list_issues.assert_called_once_with(state="closed", limit=PROJECT_CONFIG.default_limit, labels=None)


def test_cli_search_issues_invalid_state():
    runner = CliRunner()
    result = runner.invoke(cli, ["gh", "search-issues", "--state", "invalid"])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--state'" in result.output


def test_cli_search_prs_invalid_state():
    runner = CliRunner()
    result = runner.invoke(cli, ["gh", "search-prs", "--state", "invalid"])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--state'" in result.output


def test_list_issues_state_normalization():
    # Test that state == "all" omits 'state:' from the query in list_issues
    with patch("dev_tools.services.github.requests.Session.request") as mock_request:
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        # Use patch to mock get_github_token and DiskCache in services.github
        with patch("dev_tools.utils.get_github_token", return_value="dummy_token"), \
             patch("dev_tools.services.github.DiskCache") as mock_cache:
            mock_cache.return_value.get.return_value = None
            from dev_tools.services.github import GitHubClient
            client = GitHubClient(repo="owner/repo")
            client.list_issues(state="all")

            # Verify that query has is:issue but does NOT have state:all
            call_kwargs = mock_request.call_args[1]
            params = call_kwargs.get("params", {})
            q = params.get("q", "")
            assert "is:issue" in q
            assert "state:" not in q

            # Verify for state="open" it does have state:open
            client.list_issues(state="open")
            call_kwargs = mock_request.call_args[1]
            params = call_kwargs.get("params", {})
            q = params.get("q", "")
            assert "is:issue" in q
            assert "state:open" in q


def test_list_pull_requests_state_normalization_with_labels():
    # Test that state == "all" with labels omits 'state:' from query in list_pull_requests
    with patch("dev_tools.services.github.requests.Session.request") as mock_request:
        mock_response = MagicMock()
        mock_response.json.return_value = {"items": []}
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        with patch("dev_tools.utils.get_github_token", return_value="dummy_token"), \
             patch("dev_tools.services.github.DiskCache") as mock_cache:
            mock_cache.return_value.get.return_value = None
            from dev_tools.services.github import GitHubClient
            client = GitHubClient(repo="owner/repo")
            client.list_pull_requests(state="all", labels=["bug"])

            call_kwargs = mock_request.call_args[1]
            params = call_kwargs.get("params", {})
            q = params.get("q", "")
            assert "is:pr" in q
            assert "label:\"bug\"" in q
            assert "state:" not in q

            # Verify for state="closed" with labels it has state:closed
            client.list_pull_requests(state="closed", labels=["bug"])
            call_kwargs = mock_request.call_args[1]
            params = call_kwargs.get("params", {})
            q = params.get("q", "")
            assert "is:pr" in q
            assert "state:closed" in q
            assert "label:\"bug\"" in q
