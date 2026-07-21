# pylint: disable=missing-docstring,protected-access,redefined-outer-name
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator

@pytest.fixture
def orchestrator():
    with patch("dev_tools.orchestrator.GitHubClient") as mock_gh:
        orch = Orchestrator()
        orch._github = mock_gh.return_value
        yield orch

def test_validate_content_basic(orchestrator):
    # Mock get_audit_results to return empty violations
    orchestrator.get_audit_results = MagicMock(return_value={"violations": {}, "config": {}})

    title = "Test Issue"
    body = "Problem Statement\nGoal\nNon-Goals\nProposed Approach..."

    # We need to make sure _has_spec_section works for these headers.
    # In orchestrator.py, SPEC_SECTIONS are:
    # "Problem Statement", "Goal", "Non-Goals", "Proposed Approach", "Alternatives Considered",
    # "Architectural Impact", "Scope", "UNDERSTAND THE ISSUE", "DETERMINE APPROACH", "SPECIFY SCOPE", ...

    # Let's use headers that definitely match
    body = """
# Problem Statement
some problem
# Goal
some goal
# Non-Goals
none
# Proposed Approach
approach
# Alternatives Considered
alt
# Architectural Impact
none
# Scope
scope
# UNDERSTAND THE ISSUE
yes
# DETERMINE APPROACH
yes
# SPECIFY SCOPE
yes
# DEFINITION OF DONE
yes
## Acceptance Criteria
test
"""

    res = orchestrator.validate_content(title, body)
    assert res["findings"] == []
    # warnings might contain "No acceptance criteria" if regex doesn't match
    # acceptance criteria|definition of done|## done|verify|test
    assert not any("Acceptance Criteria" in w or "acceptance criteria" in w.lower() for w in res["warnings"])

def test_validate_content_missing_sections(orchestrator):
    orchestrator.get_audit_results = MagicMock(return_value={"violations": {}, "config": {}})
    title = "Test Issue"
    body = "Some body with missing sections"

    res = orchestrator.validate_content(title, body)
    assert len(res["findings"]) > 0
    assert any("Missing spec-driven sections" in f for f in res["findings"])

def test_cli_validate_issue_file(tmp_path):
    runner = CliRunner()
    draft = tmp_path / "draft.md"
    draft.write_text("\n".join(["# Problem Statement", "# Goal", "# Non-Goals", "# Proposed Approach", \
                                 "# Alternatives Considered", "# Architectural Impact", "# Scope", \
                                 "# UNDERSTAND THE ISSUE", "# DETERMINE APPROACH", "# SPECIFY SCOPE", \
                                 "# DEFINITION OF DONE", "Acceptance Criteria"]))

    with patch("dev_tools.cli.PROJECT_CONFIG"), \
         patch("dev_tools.orchestrator.GitHubClient"):
        # We need to mock the Orchestrator used in the CLI
        with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
            mock_orch = MagicMock()
            mock_lazy.return_value = mock_orch
            # Mock _read_safe_file and validate_content
            mock_orch._read_safe_file.return_value = draft.read_text()
            mock_orch.validate_content.return_value = {"findings": [], "warnings": []}

            result = runner.invoke(cli, ["--no-json", "gh", "validate-issue", "--file", str(draft)])
            if result.exit_code != 0:
                print(result.output)
            assert result.exit_code == 0
            assert "✅ File:" in result.output
            assert "Issue validation complete" in result.output

def test_cli_scaffold_issue():
    runner = CliRunner()
    # Mocking the spec_sections of the returned config object
    mock_config = MagicMock()
    mock_config.spec_sections = ["Section 1", "Section 2"]

    # Patch PROJECT_CONFIG in dev_tools.cli
    with patch("dev_tools.cli.PROJECT_CONFIG", mock_config):
        result = runner.invoke(cli, ["--no-json", "gh", "scaffold-issue"])
        if result.exit_code != 0:
            print(result.output)
        assert result.exit_code == 0
        assert "# Section 1" in result.output
        assert "# Section 2" in result.output
        assert "# Issue Title" in result.output
