"""The CLI test command must locate its package independently of caller cwd."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from dev_tools.commands import ops


@pytest.mark.parametrize("nested", [False, True])
def test_cli_runs_package_tests_from_any_caller(tmp_path, monkeypatch, nested):
    """Use the CLI package root, not dev_tools or the invoking directory."""
    caller = tmp_path / "repo"
    if nested:
        caller = caller / "nested" / "directory"
    caller.mkdir(parents=True)
    monkeypatch.chdir(caller)
    orchestrator = Mock()
    orchestrator.runtime_check.side_effect = lambda: (
        Path(".node-version").read_text(),
        Path("package.json").read_text(),
    )
    with patch.object(ops.subprocess, "run") as run:
        result = CliRunner().invoke(
            ops.test, ["cli"], obj={"ORCHESTRATOR": orchestrator, "JSON": True}
        )
    assert result.exit_code == 0, result.output
    assert Path.cwd() == caller
    orchestrator.runtime_check.assert_called_once_with()
    run.assert_called_once_with(
        [sys.executable, "-m", "pytest", "tests/"],
        cwd=str(Path(ops.__file__).resolve().parents[2]),
        check=True,
    )


def test_cli_reports_failing_test_process():
    """A pytest failure must remain a failing td command."""
    with patch.object(
        ops.subprocess, "run", side_effect=subprocess.CalledProcessError(2, "pytest")
    ):
        result = CliRunner().invoke(
            ops.test, ["cli"], obj={"ORCHESTRATOR": Mock(), "JSON": True}
        )
    assert result.exit_code != 0
    assert "exit code 2" in result.output


def test_cli_restores_caller_after_runtime_failure(tmp_path, monkeypatch):
    """Anchoring the runtime check must not leak a cwd change on errors."""
    monkeypatch.chdir(tmp_path)
    orchestrator = Mock()
    orchestrator.runtime_check.side_effect = RuntimeError("runtime failed")
    with patch.object(ops.subprocess, "run") as run:
        result = CliRunner().invoke(
            ops.test, ["cli"], obj={"ORCHESTRATOR": orchestrator, "JSON": True}
        )
    assert result.exit_code != 0
    assert Path.cwd() == tmp_path
    run.assert_not_called()
