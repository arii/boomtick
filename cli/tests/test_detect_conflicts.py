# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import json
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


def test_extract_exports_from_diff(orchestrator):
    ts_diff = """
+++ b/src/components/Button.tsx
@@ -10,3 +10,4 @@
+export function CustomButton() { return null; }
+export const BUTTON_SIZE = 42;
+export interface ButtonProps {}
"""
    py_diff = """
+++ b/cli/dev_tools/service.py
@@ -1,3 +1,4 @@
+def new_helper(): pass
+class NewService: pass
"""
    exports_ts = orchestrator.extract_exports_from_diff(ts_diff)
    assert "src/components/Button.tsx" in exports_ts
    assert exports_ts["src/components/Button.tsx"] == {"CustomButton", "BUTTON_SIZE", "ButtonProps"}

    exports_py = orchestrator.extract_exports_from_diff(py_diff)
    assert "cli/dev_tools/service.py" in exports_py
    assert exports_py["cli/dev_tools/service.py"] == {"new_helper", "NewService"}


def test_detect_semantic_overlaps(orchestrator):
    with patch.object(orchestrator, "detect_conflicts", return_value={(1, 2): ["shared.py"]}), \
         patch.object(orchestrator.github, "fetch_pr_diff") as mock_fetch_diff, \
         patch.object(orchestrator.github, "list_pull_requests", return_value=[{"number": 1}, {"number": 2}]):

        def diff_side_effect(pr_num):
            if pr_num == 1:
                return "+++ b/shared.py\n+export function sharedUtil() {}"
            if pr_num == 2:
                return "+++ b/shared.py\n+export function sharedUtil() {}"
            return ""

        mock_fetch_diff.side_effect = diff_side_effect

        overlaps = orchestrator.detect_semantic_overlaps()
        types = [o["type"] for o in overlaps]
        assert "file_overlap" in types
        assert "export_overlap" in types

        export_overlap = next(o for o in overlaps if o["type"] == "export_overlap")
        assert export_overlap["prs"] == [1, 2]
        assert export_overlap["file"] == "shared.py"
        assert export_overlap["symbol"] == "sharedUtil"


def test_orchestrator_detect_conflicts_specific_pr(orchestrator):
    with patch.object(orchestrator, "detect_conflicts") as mock_detect:
        mock_detect.return_value = {(1, 2): ["shared.py"]}
        res = orchestrator.handle_detect_conflicts(pr_num=1)
        mock_detect.assert_called_once_with(1)
        assert len(res) == 1
        assert res[0]["prs"] == [1, 2]
        assert res[0]["files"] == ["shared.py"]


def test_orchestrator_detect_conflicts_all_prs(orchestrator):
    with patch.object(orchestrator, "detect_conflicts") as mock_detect:
        mock_detect.return_value = {(1, 2): ["shared.py"], (3, 4): ["other.py"]}
        res = orchestrator.handle_detect_conflicts(all_prs=True)
        mock_detect.assert_called_once_with(None)
        assert len(res) == 2


def test_cli_detect_conflicts_all():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        # Mock handle_detect_conflicts response
        mock_orch.handle_detect_conflicts.return_value = [
            {"prs": [1, 2], "files": ["shared.py"]}
        ]

        # Invoke CLI command in JSON mode (default)
        result = runner.invoke(cli, ["gh", "detect-conflicts", "--all"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["prs"] == [1, 2]
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None, all_prs=True)


def test_cli_detect_conflicts_specific_pr():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = []

        result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "123"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "success"
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=123, all_prs=False)


def test_cli_detect_conflicts_mutually_exclusive():
    runner = CliRunner()

    result = runner.invoke(cli, ["gh", "detect-conflicts", "--pr", "123", "--all"])

    assert result.exit_code != 0
    assert "Provide either --pr or --all, not both" in result.output


def test_cli_detect_conflicts_no_args():
    runner = CliRunner()

    with patch("dev_tools.cli.LazyOrchestrator") as mock_lazy:
        mock_orch = MagicMock()
        mock_lazy.return_value = mock_orch

        mock_orch.handle_detect_conflicts.return_value = [
            {"prs": [1, 2], "files": ["shared.py"]}
        ]

        result = runner.invoke(cli, ["gh", "detect-conflicts"])

        assert result.exit_code == 0
        assert "Suggestion: Use 'td gh detect-conflicts --all'" in result.output
        stdout = result.stdout
        json_start = stdout.find("{")
        if json_start != -1:
            stdout = stdout[json_start:]
        data = json.loads(stdout)
        assert data["status"] == "success"
        assert len(data["conflicts"]) == 1
        mock_orch.handle_detect_conflicts.assert_called_once_with(pr_num=None, all_prs=True)
