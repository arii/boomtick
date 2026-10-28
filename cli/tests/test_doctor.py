"""Unit tests for td doctor full-stack runtime and diagnostic checks."""
import os
from unittest.mock import patch
from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


def test_doctor_check_all_configured():
    """Test doctor check when all environment variables and tools are configured."""
    orch = Orchestrator()
    env = {
        "APP_ID": "123456",
        "APP_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\ntest_key\n-----END RSA PRIVATE KEY-----",
        "GEMINI_API_KEY": "test_gemini_key_123",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            res = orch.doctor_check()
            assert res["node"] == "24.16.0"
            assert res["pnpm"] == "10.28.2"
            assert res["app_id"] == "configured"
            assert res["app_private_key"] == "configured"
            assert res["gemini_api_key"] == "configured"
            assert res["git_safe_directory"] in ["configured", "unconfigured"]


def test_doctor_check_missing_env():
    """Test doctor check when credentials environment variables are missing."""
    orch = Orchestrator()
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            res = orch.doctor_check()
            assert res["app_id"] == "missing"
            assert res["app_private_key"] == "missing"
            assert res["gemini_api_key"] == "missing"


def test_doctor_check_invalid_app_id():
    """Test doctor check when APP_ID is not a numeric string."""
    orch = Orchestrator()
    env = {
        "APP_ID": "not-a-number",
        "APP_PRIVATE_KEY": "short",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            res = orch.doctor_check()
            assert res["app_id"] == "invalid"
            assert res["app_private_key"] == "invalid"


def test_doctor_cli_command():
    """Test running the td doctor CLI command via click runner."""
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "status" in result.output or "Doctor" in result.output


def test_doctor_git_safe_directory_deduplication():
    """Test that git_safe_directory deduplicates duplicate safe.directory entries."""
    orch = Orchestrator()
    mock_safe_dirs_out = "/repo/path\n/repo/path\n/other/path\n/repo/path\n"

    def mock_run_command(cmd, **_kwargs):
        if cmd == ["git", "config", "--get-all", "safe.directory"]:
            return type("Res", (), {"stdout": mock_safe_dirs_out, "stderr": ""})()
        return ""

    with patch("dev_tools.orchestrator.run_command", side_effect=mock_run_command):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            with patch("os.getcwd", return_value="/repo/path"):
                with patch("os.path.realpath", side_effect=lambda p: p):
                    res = orch.doctor_check()
                    assert res["git_safe_directory"] == "configured"
                    configured = res["checks"]["git_safe_directory"]["configured_directories"]
                    assert configured == ["/repo/path", "/other/path"]


def test_doctor_git_safe_directory_strict_ownership():
    """Test strict ownership and safe.directory matching logic."""
    orch = Orchestrator()

    def mock_run_command(_cmd, **_kwargs):
        return type("Res", (), {"stdout": "", "stderr": ""})()

    # Case 1: Not in safe_dirs, process UID does not match repo stat UID -> unconfigured
    with patch("dev_tools.orchestrator.run_command", side_effect=mock_run_command):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            with patch("os.getcwd", return_value="/repo/path"):
                with patch("os.path.realpath", side_effect=lambda p: p):
                    with patch("os.getuid", return_value=1000):
                        stat_mismatch = type("StatResMismatch", (), {"st_uid": 1001})()
                        with patch("os.stat", return_value=stat_mismatch):
                            res = orch.doctor_check()
                            assert res["git_safe_directory"] == "unconfigured"

    # Case 2: Not in safe_dirs, process UID matches repo stat UID -> configured
    with patch("dev_tools.orchestrator.run_command", side_effect=mock_run_command):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            with patch("os.getcwd", return_value="/repo/path"):
                with patch("os.path.realpath", side_effect=lambda p: p):
                    with patch("os.getuid", return_value=1000):
                        stat_match = type("StatResMatch", (), {"st_uid": 1000})()
                        with patch("os.stat", return_value=stat_match):
                            res = orch.doctor_check()
                            assert res["git_safe_directory"] == "configured"
