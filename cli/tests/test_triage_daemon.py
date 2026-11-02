# pylint: disable=missing-docstring,protected-access,redefined-outer-name,line-too-long
from unittest.mock import MagicMock, patch
import pytest
from dev_tools.daemon import AutonomousTriageDaemon, JulesFeedbackDaemon


@pytest.fixture
def daemon():
    with patch("dev_tools.daemon.ExtendedJulesClient") as mock_jules_cls, \
         patch("dev_tools.daemon.GitHubClient") as mock_gh_cls, \
         patch("dev_tools.daemon.Orchestrator") as mock_orch_cls:
        d = AutonomousTriageDaemon(repos=["arii/remote-server", "arii/tech-dancer"])
        d.jules = mock_jules_cls.return_value
        d.github = mock_gh_cls.return_value
        d.orchestrator = mock_orch_cls.return_value
        yield d


def test_daemon_aliasing():
    assert JulesFeedbackDaemon is AutonomousTriageDaemon


def test_nudge_session_awaiting_user_feedback_with_plan(daemon):
    session = {"name": "sessions/sess-123", "state": "AWAITING_USER_FEEDBACK"}
    daemon.jules.get_activities.return_value = [
        {"planGenerated": {"plan": {"steps": [{"description": "Write code"}]}}}
    ]

    results = {"sessions_nudged": []}
    daemon._process_session(session, results=results, dry_run=False)

    assert len(results["sessions_nudged"]) == 1
    assert results["sessions_nudged"][0]["session"] == "sess-123"
    assert results["sessions_nudged"][0]["has_plan"] is True
    daemon.jules.send_message.assert_called_once_with(
        "sess-123",
        "Plan looks great! Please proceed with implementation, verify syntax, ensure unit tests pass, and submit the pull request.",
    )


def test_nudge_session_skips_if_already_sent_approval(daemon):
    session = {"name": "sessions/sess-dup", "state": "AWAITING_USER_FEEDBACK"}
    approval_prompt = (
        "Plan looks great! Please proceed with implementation, verify syntax, ensure unit tests pass, and submit the pull request."
    )
    daemon.jules.get_activities.return_value = [
        {"userMessaged": approval_prompt}
    ]

    results = {"sessions_nudged": []}
    daemon._process_session(session, results=results, dry_run=False)

    assert len(results["sessions_nudged"]) == 0
    daemon.jules.send_message.assert_not_called()


def test_empty_pr_detection_and_closure(daemon):
    session = {"name": "sessions/sess-empty", "state": "IN_PROGRESS"}
    daemon._get_pr_for_session = MagicMock(return_value={"number": 42, "headRefName": "empty-branch"})
    daemon.orchestrator.get_repo_for_session.return_value = "arii/remote-server"
    daemon.github.fetch_pr_view_details.return_value = {
        "number": 42,
        "files": [],
        "body": "Empty session PR",
    }

    results = {"empty_prs_handled": []}
    daemon._process_session(session, results=results, dry_run=False)

    assert len(results["empty_prs_handled"]) == 1
    assert results["empty_prs_handled"][0]["pr"] == 42
    daemon.github.close_pr.assert_called_once_with(
        42,
        repo="arii/remote-server",
        comment="Automated triage: Closed empty PR with 0 files changed.",
    )


def test_evaluate_and_merge_prs_success(daemon):
    daemon.github.list_pull_requests.side_effect = lambda state, limit, repo: [
        {"number": 100}
    ] if repo == "arii/remote-server" else []

    daemon.github.fetch_pr_view_details.return_value = {
        "number": 100,
        "isDraft": True,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [
            {"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
        ],
        "files": [{"path": "server.py"}],
        "body": "Fixes #50",
    }
    daemon.github.merge_pr.return_value = True
    daemon.github.fetch_issue_details.return_value = {"number": 50, "state": "open"}

    results = {"prs_merged": [], "empty_prs_handled": []}
    daemon._evaluate_and_merge_prs(target_repos=["arii/remote-server"], results=results, dry_run=False)

    daemon.github.mark_pr_ready.assert_called_once_with(100, repo="arii/remote-server")
    daemon.github.merge_pr.assert_called_once_with(100, repo="arii/remote-server", method="merge", delete_branch=True)
    daemon.github.close_issue.assert_called_once_with(50, repo="arii/remote-server", comment="Resolved by PR #100")
    assert len(results["prs_merged"]) == 1
    assert results["prs_merged"][0]["pr"] == 100


def test_evaluate_and_merge_prs_skips_failing_or_conflicting(daemon):
    # Conflicting PR
    daemon.github.list_pull_requests.return_value = [{"number": 101}]
    daemon.github.fetch_pr_view_details.return_value = {
        "number": 101,
        "isDraft": False,
        "mergeable": "CONFLICTING",
        "statusCheckRollup": [{"name": "test", "status": "COMPLETED", "conclusion": "SUCCESS"}],
        "files": [{"path": "file.txt"}],
    }

    results = {"prs_merged": []}
    daemon._evaluate_and_merge_prs(target_repos=["arii/remote-server"], results=results, dry_run=False)
    assert len(results["prs_merged"]) == 0
    daemon.github.merge_pr.assert_not_called()

    # Failing CI PR
    daemon.github.fetch_pr_view_details.return_value = {
        "number": 101,
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"name": "test", "status": "COMPLETED", "conclusion": "FAILURE"}],
        "files": [{"path": "file.txt"}],
    }
    daemon._evaluate_and_merge_prs(target_repos=["arii/remote-server"], results=results, dry_run=False)
    assert len(results["prs_merged"]) == 0
    daemon.github.merge_pr.assert_not_called()


def test_cleanup_stale_ci_issues(daemon):
    daemon.github.list_issues.side_effect = lambda state, labels, repo: [
        {"number": 200, "title": "fix(ci): CI failure for PR #88", "body": "Failure logs"}
    ] if repo == "arii/remote-server" else []

    daemon.github.fetch_pr_details.return_value = {
        "number": 88,
        "state": "closed",
        "merged": True,
    }

    results = {"stale_issues_closed": []}
    daemon._cleanup_stale_ci_issues(target_repos=["arii/remote-server"], results=results, dry_run=False)

    assert len(results["stale_issues_closed"]) == 1
    assert results["stale_issues_closed"][0]["issue"] == 200
    daemon.github.close_issue.assert_called_once()
    assert daemon.github.close_issue.call_args[0][0] == 200


def test_dispatch_backlog_respects_concurrency(daemon):
    # 2 active sessions out of 2 concurrency limit -> no dispatch
    sessions = [
        {"name": "sessions/s1", "state": "IN_PROGRESS"},
        {"name": "sessions/s2", "state": "AWAITING_USER_FEEDBACK"},
    ]

    results = {"backlog_dispatched": []}
    daemon._dispatch_backlog(sessions, concurrency_limit=2, target_repos=["arii/remote-server"], results=results, dry_run=False)
    assert len(results["backlog_dispatched"]) == 0
    daemon.github.add_labels.assert_not_called()

    # 1 active session out of 2 concurrency limit -> 1 available slot
    sessions_one = [{"name": "sessions/s1", "state": "IN_PROGRESS"}]
    daemon.github.list_issues.return_value = [
        {"number": 301, "title": "feat: new feature", "labels": ["enhancement"]},
        {"number": 302, "title": "feat: already jules", "labels": ["jules"]},
        {"number": 303, "title": "fix: bug", "labels": ["bug"]},
    ]

    daemon._dispatch_backlog(sessions_one, concurrency_limit=2, target_repos=["arii/remote-server"], results=results, dry_run=False)
    assert len(results["backlog_dispatched"]) == 1
    assert results["backlog_dispatched"][0]["issue"] == 301
    daemon.github.add_labels.assert_called_once_with(301, ["jules"], repo="arii/remote-server")


def test_cli_run_triage_invocation():
    from click.testing import CliRunner
    from dev_tools.cli import cli

    runner = CliRunner()
    with patch.dict("os.environ", {"GITHUB_TOKEN": "mock-token", "GH_TOKEN": "mock-token"}), \
         patch("dev_tools.daemon.AutonomousTriageDaemon.run_triage") as mock_run:
        mock_run.return_value = {
            "status": "success",
            "sessions_evaluated": 1,
            "sessions_nudged": [],
            "empty_prs_handled": [],
            "prs_merged": [],
            "stale_issues_closed": [],
            "backlog_dispatched": [],
        }

        res = runner.invoke(cli, ["agent", "run-triage", "--limit", "5", "--concurrency", "2", "--dry-run"], catch_exceptions=False)
        assert res.exit_code == 0
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["limit"] == 5
        assert kwargs["concurrency_limit"] == 2
        assert kwargs["dry_run"] is True
