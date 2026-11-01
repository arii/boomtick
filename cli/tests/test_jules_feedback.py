# pylint: disable=missing-docstring,protected-access,redefined-outer-name,line-too-long
from unittest.mock import patch, MagicMock
import pytest
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    with patch("dev_tools.orchestrator.GitHubClient") as mock_gh, \
         patch("dev_tools.orchestrator.JulesClient") as mock_jules:
        orch = Orchestrator()
        orch._github = mock_gh.return_value
        orch._jules = mock_jules.return_value
        yield orch


def test_trigger_jules_feedback_no_messages(orchestrator):
    # Setup mocks
    orchestrator.jules.get_session.return_value = {"name": "sessions/test-session-1"}
    orchestrator.get_pr_for_session = MagicMock(return_value=123)
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "fake-sha"}}

    # Mock successful check runs (meaning success feedback "All checks passed successfully. You may proceed.")
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "success", "name": "Build"}
    ]

    # Return empty list of messages (no previous messages)
    orchestrator.jules.get_messages.return_value = []

    res = orchestrator.trigger_jules_feedback("test-session-1")

    assert res["status"] == "success"
    assert res["feedback"] == "All checks passed successfully. You may proceed."
    orchestrator.jules.send_message.assert_called_once_with(
        "test-session-1",
        "All checks passed successfully. You may proceed."
    )


def test_trigger_jules_feedback_identical_success_message(orchestrator):
    # Setup mocks
    orchestrator.jules.get_session.return_value = {"name": "sessions/test-session-1"}
    orchestrator.get_pr_for_session = MagicMock(return_value=123)
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "fake-sha"}}

    # Mock successful check runs
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "success", "name": "Build"}
    ]

    # Return last message from user with identical success message
    orchestrator.jules.get_messages.return_value = [
        {"role": "user", "content": "All checks passed successfully. You may proceed."}
    ]

    res = orchestrator.trigger_jules_feedback("test-session-1")

    assert res["status"] == "skipped"
    assert "identical" in res["message"] or "redundant" in res["message"] or "already" in res["message"]
    orchestrator.jules.send_message.assert_not_called()


def test_trigger_jules_feedback_identical_failure_message(orchestrator):
    # Setup mocks
    orchestrator.jules.get_session.return_value = {"name": "sessions/test-session-1"}
    orchestrator.get_pr_for_session = MagicMock(return_value=123)
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "fake-sha"}}

    # Mock failed check runs
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "failure", "name": "Lint", "id": 111}
    ]
    orchestrator.github.fetch_check_run_logs.return_value = "Error: Lint failed"

    # Return last message from user with the same failure details
    expected_feedback = (
        "The CI pipeline reported failures. Here are the details:\n\n"
        "### Failed Check: Lint\n"
        "```\nError: Lint failed\n```\n\n"
    )

    orchestrator.jules.get_messages.return_value = [
        {"role": "user", "content": expected_feedback}
    ]

    res = orchestrator.trigger_jules_feedback("test-session-1")

    assert res["status"] == "skipped"
    assert "identical" in res["message"] or "redundant" in res["message"]
    orchestrator.jules.send_message.assert_not_called()


def test_trigger_jules_feedback_state_changed_failure_to_success(orchestrator):
    # Setup mocks
    orchestrator.jules.get_session.return_value = {"name": "sessions/test-session-1"}
    orchestrator.get_pr_for_session = MagicMock(return_value=123)
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "fake-sha"}}

    # Mock successful check runs (state is now success)
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "success", "name": "Build"}
    ]

    # Return last user message indicating failure (previous state was failure)
    previous_failure = (
        "The CI pipeline reported failures. Here are the details:\n\n"
        "### Failed Check: Lint\n"
        "```\nError: Lint failed\n```\n\n"
    )
    orchestrator.jules.get_messages.return_value = [
        {"role": "user", "content": previous_failure}
    ]

    res = orchestrator.trigger_jules_feedback("test-session-1")

    assert res["status"] == "success"
    assert res["feedback"] == "All checks passed successfully. You may proceed."
    orchestrator.jules.send_message.assert_called_once_with(
        "test-session-1",
        "All checks passed successfully. You may proceed."
    )


def test_trigger_jules_feedback_state_changed_success_to_failure(orchestrator):
    # Setup mocks
    orchestrator.jules.get_session.return_value = {"name": "sessions/test-session-1"}
    orchestrator.get_pr_for_session = MagicMock(return_value=123)
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "fake-sha"}}

    # Mock failed check runs (state is now failure)
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "failure", "name": "Lint", "id": 111}
    ]
    orchestrator.github.fetch_check_run_logs.return_value = "Error: Lint failed"

    # Return last user message indicating success (previous state was success)
    orchestrator.jules.get_messages.return_value = [
        {"role": "user", "content": "All checks passed successfully. You may proceed."}
    ]

    res = orchestrator.trigger_jules_feedback("test-session-1")

    assert res["status"] == "success"
    assert "The CI pipeline reported failures" in res["feedback"]
    orchestrator.jules.send_message.assert_called_once()


def test_get_repo_for_session(orchestrator):
    # From pullRequest URL
    session_with_url = {
        "outputs": [{"pullRequest": {"url": "https://github.com/arii/remote-server/pull/135"}}]
    }
    assert orchestrator.get_repo_for_session(session_with_url) == "arii/remote-server"

    # From sourceContext
    session_with_src = {
        "sourceContext": {"source": "sources/github/arii/boomtick"}
    }
    assert orchestrator.get_repo_for_session(session_with_src) == "arii/boomtick"

    # Fallback to None
    assert orchestrator.get_repo_for_session({}) is None


def test_trigger_jules_feedback_multi_repo(orchestrator):
    orchestrator.jules.get_session.return_value = {
        "name": "sessions/test-remote-session",
        "outputs": [{"pullRequest": {"url": "https://github.com/arii/remote-server/pull/135"}}],
    }
    orchestrator.github.fetch_pr_details.return_value = {"head": {"sha": "sha-135"}}
    orchestrator.github.fetch_check_runs.return_value = [
        {"status": "completed", "conclusion": "success", "name": "CI"}
    ]
    orchestrator.jules.get_messages.return_value = []

    res = orchestrator.trigger_jules_feedback("test-remote-session")

    assert res["status"] == "success"
    orchestrator.github.fetch_pr_details.assert_called_once_with(135, repo="arii/remote-server")
    orchestrator.github.fetch_check_runs.assert_called_once_with("sha-135", repo="arii/remote-server")


def test_daemon_batch_pre_match_chunks():
    from dev_tools.daemon import JulesFeedbackDaemon
    with patch("dev_tools.daemon.ExtendedJulesClient"), \
         patch("dev_tools.daemon.GitHubClient") as mock_gh_cls, \
         patch("dev_tools.daemon.Orchestrator"):
        daemon = JulesFeedbackDaemon()
        daemon.github = mock_gh_cls.return_value
        daemon.github.search_pull_requests.return_value = []

        # 12 sessions -> should execute in chunks of at most 5
        sessions = [{"name": f"sessions/s{i}"} for i in range(12)]
        daemon._pre_match_sessions_batch(sessions)

        assert daemon.github.search_pull_requests.call_count == 3
        calls = daemon.github.search_pull_requests.call_args_list
        assert calls[0][0][0].count(" OR ") == 4
        assert calls[1][0][0].count(" OR ") == 4
        assert calls[2][0][0].count(" OR ") == 1


def test_daemon_get_pr_for_session_error_handling():
    from dev_tools.daemon import JulesFeedbackDaemon
    with patch("dev_tools.daemon.ExtendedJulesClient"), \
         patch("dev_tools.daemon.GitHubClient") as mock_gh_cls, \
         patch("dev_tools.daemon.Orchestrator") as mock_orch_cls:
        daemon = JulesFeedbackDaemon()
        daemon.github = mock_gh_cls.return_value
        daemon.orchestrator = mock_orch_cls.return_value

        daemon.orchestrator.get_pr_for_session.return_value = 999
        daemon.orchestrator.get_repo_for_session.return_value = "arii/remote-server"
        daemon.github.fetch_pr_details.side_effect = Exception("404 Not Found")

        result = daemon._get_pr_for_session({"name": "sessions/err-session"})
        assert result is None

