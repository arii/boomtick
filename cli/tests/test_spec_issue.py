# pylint: disable=missing-docstring,line-too-long
"""Tests for td gh spec-issue (service-level; no network)."""
import json
import subprocess
from unittest.mock import patch

from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.services import spec_issue as spec


def _checkout(tmp_path):
    root = tmp_path / "co"
    (root / "mcp" / "src").mkdir(parents=True)
    (root / "mcp" / "src" / "tool.ts").write_text("x")
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (root / "package.json").write_text(json.dumps(
        {"scripts": {"test": "vitest", "lint": "oxlint"}}))
    (root / "scripts").mkdir()
    (root / "scripts" / "verify-scope.py").write_text("# gate\n")
    return root


FULL_BODY = """# Problem Statement

Login redirect is broken.

# Goal

Fix it.

# Scope

Touches mcp/src/tool.ts.

# Definition of Done

Redirect works.
"""

BARE_BODY = "Login redirect is broken, please fix."


def test_ready_issue(tmp_path):
    root = _checkout(tmp_path)
    improved, report = spec.render_body("Fix login", FULL_BODY, str(root))
    assert report["ready"] is True
    assert report["missing_headers"] == []
    assert any(i["path"] == "mcp/src/tool.ts" and
               i["status"] == "in checkout" for i in report["scope"])
    assert "## Agent scope" in improved
    assert "## Validation" in improved
    assert any("pytest" in g for g in report["gates"])
    assert any("verify-scope" in g for g in report["gates"])


def test_bare_issue_not_ready(tmp_path):
    root = _checkout(tmp_path)
    improved, report = spec.render_body("Fix login", BARE_BODY, str(root))
    assert report["ready"] is False
    assert "Problem Statement" in report["missing_headers"]
    assert report["scope"] == []
    assert "no file paths mentioned" in improved


def test_new_file_flagged(tmp_path):
    root = _checkout(tmp_path)
    body = FULL_BODY + "\nAlso add mcp/src/brand-new.ts.\n"
    _improved, report = spec.render_body("t", body, str(root))
    item = next(i for i in report["scope"]
                if i["path"] == "mcp/src/brand-new.ts")
    assert item["status"].startswith("NEW - confirm")


def test_idempotent_rerun(tmp_path):
    root = _checkout(tmp_path)
    once, _rep1 = spec.render_body("Fix login", FULL_BODY, str(root))
    twice, rep2 = spec.render_body("Fix login", once, str(root))
    assert twice.count("## Agent scope") == 1
    assert twice.count("## Validation") == 1
    assert rep2["ready"] is True
    assert rep2["sections_added"] == []


def test_missing_headers_substring():
    assert spec.missing_headers("# SPECIFY SCOPE\n# Goal\n"
                                "# Problem Statement\n"
                                "# Definition of Done\n") == []


def test_gates_empty_checkout(tmp_path):
    assert spec.detect_gates(str(tmp_path)) == [
        "Scope: changes limited to the scope files above"]


def test_cli_dry_run_and_write(tmp_path):
    root = _checkout(tmp_path)
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.get_issue_details",
               return_value={"title": "Fix login",
                             "body": FULL_BODY}), \
            patch("dev_tools.orchestrator.Orchestrator.update_issue") \
            as update_mock, \
            patch("dev_tools.services.local_sessions.repo_root_for",
                  return_value=str(root)):
        result = runner.invoke(
            cli, ["--json", "gh", "spec-issue", "12",
                  "--path", str(root)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ready"] is True
    assert payload["wrote"] is False
    update_mock.assert_not_called()


def test_cli_write_calls_update(tmp_path):
    root = _checkout(tmp_path)
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.get_issue_details",
               return_value={"title": "Fix login",
                             "body": FULL_BODY}), \
            patch("dev_tools.orchestrator.Orchestrator.update_issue") \
            as update_mock, \
            patch("dev_tools.services.local_sessions.repo_root_for",
                  return_value=str(root)):
        result = runner.invoke(
            cli, ["--json", "gh", "spec-issue", "12", "--write",
                  "--path", str(root)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["wrote"] is True
    update_mock.assert_called_once()
    _kwargs = update_mock.call_args
    assert "## Agent scope" in _kwargs.kwargs["body"]


def test_cli_not_ready_exits_1(tmp_path):
    root = _checkout(tmp_path)
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.get_issue_details",
               return_value={"title": "Fix login",
                             "body": BARE_BODY}):
        result = runner.invoke(
            cli, ["--json", "gh", "spec-issue", "12",
                  "--path", str(root)])
    assert result.exit_code == 1
    assert json.loads(result.output)["ready"] is False
