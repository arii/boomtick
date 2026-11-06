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

def test_validate_content_ci_failure_exempt(orchestrator):
    orchestrator.get_audit_results = MagicMock(return_value={"violations": {}, "config": {}})

    res1 = orchestrator.validate_content("fix(ci): CI failure for PR #944", "CI failure detected in run 123.")
    assert not any("Missing spec-driven sections" in f for f in res1["findings"])
    assert not any("No acceptance criteria" in w for w in res1["warnings"])

    res2 = orchestrator.validate_content("Regular Title", "Body <!-- ci-failure-branch:main -->")
    assert not any("Missing spec-driven sections" in f for f in res2["findings"])

    res3 = orchestrator.validate_content("Task [skip-spec-check]", "Just a quick bug description.")
    assert not any("Missing spec-driven sections" in f for f in res3["findings"])

def test_scope_status_mixed_case_paths(tmp_path):
    from dev_tools.services.spec_issue import scope_status

    checkout = tmp_path / "checkout"
    (checkout / "utils").mkdir(parents=True)
    (checkout / "utils" / "clientId.ts").write_text("export const id = 1;\n")

    body = "Scope: touch utils/clientId.ts and utils/missingDir/missingFile.ts"
    items = scope_status(body, str(checkout))
    by_path = {i["path"]: i["status"] for i in items}

    assert by_path["utils/clientId.ts"] == "in checkout"
    assert by_path["utils/missingDir/missingFile.ts"] == "NEW - confirm (not in checkout)"


def test_extract_mentions_ignores_prose_and_code_fragments():
    # Regression test for #1142: dotted identifiers, generic word/
    # fragments, and single-letter paths must not become scope entries.
    # Proper-noun single-segment dirs (arii/) still extract: they are
    # structurally identical to deliberate mentions (scripts/, cli/),
    # which test_directory_match requires; callers confirm via checkout
    # existence checks (scope_status NEW vs in-checkout).
    from dev_tools.services.scope_gate import extract_mentions

    body = ("Revalidation reported: os.path.isfile, os.path.isdir, "
            "issue_text.lower, scope_gate.extract, spec_issue.scope, e.g, "
            "arii/, file/, i/ - all flagged NEW - confirm (not in checkout).")
    files, dirs = extract_mentions(body)
    assert files == set()
    assert dirs == {"arii/"}


def test_extract_mentions_keeps_deliberate_mentions():
    # Deliberate mentions still extract: slashed paths, multi-segment
    # dirs, and bare filenames with known file context.
    from dev_tools.services.scope_gate import extract_mentions

    body = ("Touches cli/dev_tools/services/scope_gate.py and the "
            "mcp/src/tools/ registry, plus action.yml and "
            "cli/dev_tools/resources/visual_guidelines.json")
    files, dirs = extract_mentions(body)
    assert "cli/dev_tools/services/scope_gate.py" in files
    assert "cli/dev_tools/resources/visual_guidelines.json" in files
    assert "action.yml" in files
    assert "mcp/src/tools/" in dirs


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

    # Patch get_config in dev_tools.cli
    with patch("dev_tools.cli.get_config", return_value=mock_config):
        result = runner.invoke(cli, ["--no-json", "gh", "scaffold-issue"])
        if result.exit_code != 0:
            print(result.output)
        assert result.exit_code == 0
        assert "# Section 1" in result.output
        assert "# Section 2" in result.output
        assert "# Issue Title" in result.output


def test_cli_scaffold_issue_file(tmp_path):
    runner = CliRunner()
    # Mocking the spec_sections of the returned config object
    mock_config = MagicMock()
    mock_config.spec_sections = ["Section 1", "Section 2"]

    scaffold_file = tmp_path / "scaffold.md"

    # Patch get_config in dev_tools.cli
    with patch("dev_tools.cli.get_config", return_value=mock_config):
        result = runner.invoke(cli, ["--no-json", "gh", "scaffold-issue", "--file", str(scaffold_file)])
        if result.exit_code != 0:
            print(result.output)
        assert result.exit_code == 0
        assert f"Scaffold successfully written to {scaffold_file}" in result.output

        # Verify the file was written and has correct content
        assert scaffold_file.exists()
        content = scaffold_file.read_text(encoding="utf-8")
        assert "# Section 1" in content
        assert "# Section 2" in content
        assert "# Issue Title" in content
