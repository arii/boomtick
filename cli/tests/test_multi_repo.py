"""Unit tests for multi-repository discovery, status, and sequential command execution."""

import json
import pathlib
import pytest
from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.multi_repo import (
    discover_ecosystem_repos,
    get_repo_summary,
    exec_in_repos,
    warm_ecosystem_context,
)


@pytest.fixture
def temp_ecosystem(tmp_path):
    """Creates a temporary multi-repo directory tree."""
    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    (repo1 / ".git").mkdir()
    (repo1 / "project_config.json").write_text(
        json.dumps({"github_repo": "org/repo1", "packageName": "repo1", "vite_base_path": "/repo1/"})
    )
    (repo1 / "package.json").write_text(json.dumps({"name": "repo1", "scripts": {"agent:prime": "echo prime1"}}))

    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    (repo2 / ".git").mkdir()
    (repo2 / "project_config.json").write_text(
        json.dumps({"github_repo": "org/repo2", "packageName": "repo2", "vite_base_path": "/repo2/"})
    )
    (repo2 / "package.json").write_text(json.dumps({"name": "repo2", "scripts": {"doctor": "echo doctor2"}}))

    return {"root": tmp_path, "repo1": repo1, "repo2": repo2}


def test_discover_ecosystem_repos_auto(temp_ecosystem):
    repo1 = temp_ecosystem["repo1"]
    repos = discover_ecosystem_repos(root_dir=repo1)

    assert "org/repo1" in repos or "repo1" in repos
    assert "org/repo2" in repos or "repo2" in repos


def test_discover_ecosystem_repos_explicit(temp_ecosystem):
    repo1 = temp_ecosystem["repo1"]
    explicit_cfg = {
        "ecosystem_repos": {
            "custom-repo1": ".",
            "custom-repo2": "../repo2",
        }
    }
    repos = discover_ecosystem_repos(root_dir=repo1, explicit_config=explicit_cfg)

    assert "custom-repo1" in repos
    assert "custom-repo2" in repos
    assert repos["custom-repo1"] == repo1
    assert repos["custom-repo2"] == temp_ecosystem["repo2"]


def test_discover_ecosystem_repos_filter(temp_ecosystem):
    repo1 = temp_ecosystem["repo1"]
    repos = discover_ecosystem_repos(root_dir=repo1, filter_repos=["repo2"])

    assert len(repos) == 1
    assert any("repo2" in k for k in repos.keys())


def test_get_repo_summary(temp_ecosystem):
    repo1 = temp_ecosystem["repo1"]
    (repo1 / ".agent-context.json").write_text(json.dumps({"packageName": "repo1"}))

    summary = get_repo_summary("org/repo1", repo1)
    assert summary["repo"] == "org/repo1"
    assert summary["path"] == str(repo1)
    assert summary["has_context"] is True
    assert summary["config"]["packageName"] == "repo1"


def test_exec_in_repos(temp_ecosystem):
    repos = {
        "repo1": temp_ecosystem["repo1"],
        "repo2": temp_ecosystem["repo2"],
    }
    res = exec_in_repos(repos, "echo 'hello from repo'")

    assert res["status"] == "success"
    assert res["total_repos"] == 2
    assert res["total_passed"] == 2
    assert res["total_failed"] == 0
    assert len(res["results"]) == 2
    assert "hello from repo" in res["results"][0]["stdout"]


def test_exec_in_repos_fail_fast(temp_ecosystem):
    repos = {
        "repo1": temp_ecosystem["repo1"],
        "repo2": temp_ecosystem["repo2"],
    }
    # Command fails on repo1
    res = exec_in_repos(repos, "exit 1", continue_on_error=False)

    assert res["status"] == "error"
    assert res["total_failed"] == 1
    # Only 1 was executed because fail-fast stopped it
    assert len(res["results"]) == 1


def test_cli_multi_repo_list():
    runner = CliRunner()
    res = runner.invoke(cli, ["multi-repo", "list"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["status"] == "success"
    assert "repos" in data
    assert data["total"] >= 1


def test_cli_multi_repo_status():
    runner = CliRunner()
    res = runner.invoke(cli, ["multi-repo", "status"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["status"] == "success"
    assert len(data["repos"]) >= 1


def test_cli_multi_repo_exec():
    runner = CliRunner()
    res = runner.invoke(cli, ["multi-repo", "exec", "echo test-multi-exec"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["status"] == "success"
    assert data["total_passed"] >= 1
