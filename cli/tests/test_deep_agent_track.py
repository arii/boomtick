# pylint: disable=missing-docstring,protected-access,unused-argument
"""Deep-agent track: td commands the deep agent relies on must exist and work.

Covers:
- `td preflight` repo-awareness (audit skip, base-ref discovery)
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


def test_preflight_skips_audit_when_dirs_missing():
    orch = Orchestrator()
    with (
        patch.object(orch, "doctor_check", return_value={"status": "success"}),
        patch.object(orch, "detect_conflicts", return_value={}),
        patch.object(orch, "_pnpm_has_script", return_value=False),
        patch(
            "dev_tools.orchestrator.run_command",
            return_value=MagicMock(returncode=0, stdout="clean"),
        ),
        # Stub the config instead of patching os.path.exists globally:
        # Python 3.14's pathlib routes Path.exists() through os.path.exists,
        # so a global patch also hides project_config.json from the config
        # loader, which then raises on missing required keys.
        patch(
            "dev_tools.orchestrator.get_config",
            return_value=SimpleNamespace(
                audit_check_dirs=["/nonexistent/boomtick-audit-dir"]
            ),
        ),
    ):
        res = orch.run_preflight(base_branch="main")
    assert res["audit"]["status"] == "skipped"
    assert res["status"] == "success"


def test_preflight_skips_merge_simulation_when_no_base_ref():
    orch = Orchestrator()

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        if cmd[:2] == ["git", "rev-parse"]:
            result.returncode = 1  # no base ref verifies
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = "clean"
        return result

    with (
        patch.object(orch, "doctor_check", return_value={"status": "success"}),
        patch.object(orch, "get_audit_results", return_value={"violations": {}}),
        patch.object(orch, "detect_conflicts", return_value={}),
        patch.object(orch, "_pnpm_has_script", return_value=False),
        patch("dev_tools.orchestrator.run_command", side_effect=fake_run),
    ):
        res = orch.run_preflight(base_branch="nonexistent-base")
    assert res["merge_simulation"]["status"] == "skipped"
    assert res["status"] == "success"
