from unittest.mock import Mock

from click.testing import CliRunner

from dev_tools.commands.sessions import ux_audit


def test_ux_audit_forwards_route_and_viewport_options():
    orchestrator = Mock()
    orchestrator.run_ux_audit.return_value = {"status": "success", "results": []}

    result = CliRunner().invoke(
        ux_audit,
        ["--route", "/settings", "--mobile"],
        obj={"ORCHESTRATOR": orchestrator, "JSON": True},
    )

    assert result.exit_code == 0, result.output
    orchestrator.run_ux_audit.assert_called_once_with(
        route="/settings", all_routes=False, desktop=False, mobile=True
    )


def test_ux_audit_returns_nonzero_when_audit_fails():
    orchestrator = Mock()
    orchestrator.run_ux_audit.return_value = {
        "status": "error",
        "results": [{"route": "/", "status": "error"}],
    }

    result = CliRunner().invoke(
        ux_audit, ["--route", "/"], obj={"ORCHESTRATOR": orchestrator, "JSON": True}
    )

    assert result.exit_code == 1
    assert '"status": "error"' in result.output
