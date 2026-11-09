"""Tests for the sessions-unknown merge gate in suggest_next_action.

A failed local-session scan must surface as UNKNOWN (active_sessions None)
instead of defaulting to 0, and the all-clear fast path requires a
known-zero session count — never an unknown one.
"""

from unittest.mock import MagicMock, patch

from dev_tools.orchestrator import Orchestrator


def _make_orch(open_prs=None, failing_runs=None):
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": open_prs or []})
    orch._github = MagicMock()
    orch._github.fetch_workflow_runs = MagicMock(return_value=failing_runs or [])
    return orch


def _patch_scan(monkeypatch_side_effect=None, return_value=None):
    """Patch the session-scan seam used by suggest_next_action."""
    if monkeypatch_side_effect is not None:
        return patch(
            "dev_tools.services.local_sessions.scan_sessions",
            side_effect=monkeypatch_side_effect,
        )
    return patch(
        "dev_tools.services.local_sessions.scan_sessions",
        return_value=return_value,
    )


def test_scan_failure_yields_unknown_not_zero():
    """Scan failure reports sessions_unknown True with active_sessions None."""
    orch = _make_orch()
    with (
        _patch_scan(monkeypatch_side_effect=RuntimeError("scan blew up")),
        patch("dev_tools.services.local_sessions.repo_root_for", return_value="/tmp/x"),
    ):
        res = orch.suggest_next_action()
    assert res["sessions_unknown"] is True
    assert res["counts"]["active_sessions"] is None
    assert res["status"] == "success"


def test_scan_failure_blocks_all_clear_fast_path():
    """Zero PRs + zero failing runs + unknown sessions must NOT fast-path."""
    orch = _make_orch(open_prs=[], failing_runs=[])
    with (
        _patch_scan(monkeypatch_side_effect=OSError("no worktrees")),
        patch("dev_tools.services.local_sessions.repo_root_for", return_value="/tmp/x"),
    ):
        res = orch.suggest_next_action()
    assert res["fast_path"] is False
    assert res["sessions_unknown"] is True
    assert res["suggestion"].startswith("SUGGEST: triage")


def test_known_zero_sessions_still_takes_fast_path():
    """Control: a successful scan with zero sessions keeps the all-clear."""
    orch = _make_orch(open_prs=[], failing_runs=[])
    with (
        _patch_scan(return_value=[]),
        patch("dev_tools.services.local_sessions.repo_root_for", return_value="/tmp/x"),
    ):
        res = orch.suggest_next_action()
    assert res["fast_path"] is True
    assert res["sessions_unknown"] is False
    assert res["counts"]["active_sessions"] == 0
    assert res["suggestion"].startswith("SUGGEST: none")


def test_triage_suggestion_flags_unknown_sessions():
    """Triage suggestion labels the session count UNKNOWN and says why."""
    orch = _make_orch(open_prs=[], failing_runs=[])
    with (
        _patch_scan(monkeypatch_side_effect=RuntimeError("scan blew up")),
        patch("dev_tools.services.local_sessions.repo_root_for", return_value="/tmp/x"),
    ):
        res = orch.suggest_next_action()
    assert "UNKNOWN" in res["suggestion"]
    assert "Sessions scan unavailable" in res["suggestion"]


def test_known_sessions_reported_numerically_without_unknown_flag():
    """Control: a healthy scan reports a real count and no unknown warning."""
    orch = _make_orch(open_prs=[], failing_runs=[])
    sessions = [{"sessionId": "sess_a"}, {"sessionId": "sess_b"}]
    with (
        _patch_scan(return_value=sessions),
        patch("dev_tools.services.local_sessions.repo_root_for", return_value="/tmp/x"),
    ):
        res = orch.suggest_next_action()
    assert res["sessions_unknown"] is False
    assert res["counts"]["active_sessions"] == 2
    assert res["fast_path"] is False
    assert "Active Sessions: 2" in res["suggestion"]
    assert "UNKNOWN" not in res["suggestion"]
    assert "Sessions scan unavailable" not in res["suggestion"]
