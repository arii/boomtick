import os
from unittest.mock import patch
from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


def test_doctor_check_all_configured():
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
    orch = Orchestrator()
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(orch, "runtime_check", return_value={"node": "24.16.0", "pnpm": "10.28.2"}):
            res = orch.doctor_check()
            assert res["app_id"] == "missing"
            assert res["app_private_key"] == "missing"
            assert res["gemini_api_key"] == "missing"


def test_doctor_check_invalid_app_id():
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
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "status" in result.output or "Doctor" in result.output
