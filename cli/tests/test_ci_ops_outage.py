"""Regression test: get_ci_logs must record outage identities (PR #1220)."""
from unittest.mock import MagicMock, patch

from dev_tools.orchestrator import Orchestrator


def _orchestrator_with_stub_github():
    with patch("dev_tools.orchestrator.GitHubClient"), patch("dev_tools.orchestrator.get_config"):
        orch = Orchestrator()
    orch._github = MagicMock()
    return orch


def test_get_ci_logs_records_outage_identities():
    """Broken suite/run ids land in failedSuites/failedLogs while healthy runs collect."""
    orch = _orchestrator_with_stub_github()
    gh = orch.github
    gh.fetch_pr_details.return_value = {"head": {"sha": "abc123"}}
    gh.fetch_check_runs.return_value = []
    gh.fetch_check_suites.return_value = [{"id": 11}, {"id": 22}]

    def _runs_for_suite(suite_id, repo=None):
        if suite_id == 22:
            raise RuntimeError("suite API outage")
        return [
            {"id": 101, "name": "ok-job", "conclusion": "failure", "external_id": None},
            {"id": 102, "name": "bad-job", "conclusion": "failure", "external_id": None},
        ]

    def _run_logs(run_id, external_id=None, repo=None):
        if run_id == 102:
            raise RuntimeError("log API outage")
        return "log-content-ok"

    gh.fetch_check_runs_for_suite.side_effect = _runs_for_suite
    gh.fetch_check_run_logs.side_effect = _run_logs

    result = orch.get_ci_logs(123)

    assert result["failedSuites"] == [22]
    assert result["failedLogs"] == [102]
    assert result["logs"] == {"ok-job": "log-content-ok"}
