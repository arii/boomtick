# pylint: disable=missing-docstring,protected-access,redefined-outer-name,line-too-long,unused-argument,unused-import
from unittest.mock import patch, MagicMock
import pytest
from click.testing import CliRunner

from dev_tools.services.jules import JulesClient
from dev_tools.orchestrator import Orchestrator
from dev_tools.cli import cli


def test_extract_title_from_prompt_markdown_header():
    client = JulesClient(api_key="fake-key")
    prompt = "\n\n# Integration and Reconciliation Task: Pull Requests #97\n\n## Objective\nReconcile PRs..."
    title = client.extract_title_from_prompt(prompt)
    assert title == "Integration and Reconciliation Task: Pull Requests #97"


def test_extract_title_from_prompt_markdown_subheader():
    client = JulesClient(api_key="fake-key")
    prompt = "### Fix CI Failure in dev_tools\n\nSome body content"
    title = client.extract_title_from_prompt(prompt)
    assert title == "Fix CI Failure in dev_tools"


def test_extract_title_from_prompt_multiline_plain_text():
    client = JulesClient(api_key="fake-key")
    prompt = "\nFix bug in td agent dispatch where Jules session name is too long\nDetailed description follows..."
    title = client.extract_title_from_prompt(prompt)
    assert title == "Fix bug in td agent dispatch where Jules session name is too long"


def test_extract_title_from_prompt_truncation():
    client = JulesClient(api_key="fake-key")
    long_first_line = "A" * 150
    prompt = f"{long_first_line}\nSecond line"
    title = client.extract_title_from_prompt(prompt)
    assert len(title) == 100
    assert title == "A" * 100


def test_extract_title_from_prompt_empty():
    client = JulesClient(api_key="fake-key")
    assert client.extract_title_from_prompt("") == "Jules Agent Task"
    assert client.extract_title_from_prompt("   \n\n  ") == "Jules Agent Task"


@patch("requests.post")
def test_create_session_from_source_with_explicit_title(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"name": "sessions/12345", "state": "ACTIVE"}
    mock_post.return_value = mock_response

    client = JulesClient(api_key="fake-key")
    res = client.create_session_from_source(
        source_id="sources/my-source",
        branch="main",
        prompt="Detailed task body instructions...",
        title="Reconcile PRs #97, #100",
    )

    assert res == {"name": "sessions/12345", "state": "ACTIVE"}
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]

    assert payload["title"] == "Reconcile PRs #97, #100"
    assert payload["prompt"] == "# Reconcile PRs #97, #100\n\nDetailed task body instructions..."
    assert payload["sourceContext"]["githubRepoContext"]["startingBranch"] == "main"


@patch("requests.post")
def test_create_session_from_source_auto_extract_title(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"name": "sessions/67890", "state": "ACTIVE"}
    mock_post.return_value = mock_response

    client = JulesClient(api_key="fake-key")
    prompt = "# Fix UI Overflow Issue\n\nEnsure table columns align properly."
    res = client.create_session_from_source(
        source_id="sources/my-source",
        branch="main",
        prompt=prompt,
    )

    assert res == {"name": "sessions/67890", "state": "ACTIVE"}
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    payload = kwargs["json"]

    assert payload["title"] == "Fix UI Overflow Issue"
    assert payload["prompt"] == prompt


@patch("dev_tools.orchestrator.GitHubClient")
@patch("dev_tools.orchestrator.JulesClient")
def test_orchestrator_dispatch_jules_review_passes_title(mock_jules_cls, mock_gh_cls):
    orch = Orchestrator()
    orch.github.branch_exists.return_value = True
    orch.jules.discover_source_id.return_value = "clean-source-id"
    orch.jules.create_session_from_source.return_value = {"name": "sessions/111"}

    res = orch.dispatch_jules_review(
        branch="main",
        prompt="Some multi-line task description",
        title="Custom Title Here",
    )

    assert res == {"name": "sessions/111"}
    orch.jules.create_session_from_source.assert_called_once_with(
        "clean-source-id", "main", "Some multi-line task description", title="Custom Title Here"
    )


@patch("dev_tools.orchestrator.Orchestrator.dispatch_jules_review")
def test_cli_agent_dispatch_with_title_flag(mock_dispatch):
    mock_dispatch.return_value = {"name": "sessions/222", "title": "My Custom Title"}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["agent", "dispatch", "--title", "My Custom Title", "main", "Task details"],
        obj={},
    )

    assert result.exit_code == 0
    mock_dispatch.assert_called_once_with("main", "Task details", title="My Custom Title")


@patch("dev_tools.orchestrator.Orchestrator.dispatch_jules_review")
def test_cli_agent_dispatch_without_title_flag(mock_dispatch):
    mock_dispatch.return_value = {"name": "sessions/333"}
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["agent", "dispatch", "main", "# Auto Extracted Title\n\nTask details"],
        obj={},
    )

    assert result.exit_code == 0
    mock_dispatch.assert_called_once_with("main", "# Auto Extracted Title\n\nTask details", title=None)
