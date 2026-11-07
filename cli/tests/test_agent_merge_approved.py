"""Unit tests for agent merge-approved command and eligibility checks."""
import os
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.orchestrator import Orchestrator


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_evaluate_pr_merge_readiness_eligible():
    """Test that a fully approved, clean, non-draft PR with green checks is eligible."""
    orch = Orchestrator()
    orch.github.fetch_pr_details = MagicMock(return_value={
        "title": "Fix something",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": "head123"},
    })
    orch.github.fetch_pr_review_decision = MagicMock(return_value="APPROVED")
    orch.github.fetch_check_runs = MagicMock(return_value=[
        {"name": "build", "conclusion": "success"}
    ])

    readiness = orch.evaluate_pr_merge_readiness(123)
    assert readiness["is_eligible"] is True
    assert readiness["reason"] is None
    assert readiness["pr_number"] == 123
    assert readiness["mergeable"] == "MERGEABLE"
    assert readiness["draft"] is False
    assert readiness["review_decision"] == "APPROVED"
    assert readiness["has_failing_checks"] is False


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_evaluate_pr_merge_readiness_ineligible_reasons():
    """Test refusal reasons for drafts, unapproved, failing checks, and conflicting PRs."""
    orch = Orchestrator()
    # 1. Draft
    orch.github.fetch_pr_details = MagicMock(return_value={
        "title": "Draft PR",
        "draft": True,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": "head123"},
    })
    orch.github.fetch_pr_review_decision = MagicMock(return_value="APPROVED")
    orch.github.fetch_check_runs = MagicMock(return_value=[])

    res = orch.evaluate_pr_merge_readiness(1)
    assert res["is_eligible"] is False
    assert "PR is a draft" in res["reason"]

    # 2. Unapproved
    orch.github.fetch_pr_details = MagicMock(return_value={
        "title": "Unapproved PR",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": "head123"},
    })
    orch.github.fetch_pr_review_decision = MagicMock(return_value="CHANGES_REQUESTED")
    res = orch.evaluate_pr_merge_readiness(2)
    assert res["is_eligible"] is False
    assert "Review decision is CHANGES_REQUESTED" in res["reason"]

    # 3. Failing check run
    orch.github.fetch_pr_details = MagicMock(return_value={
        "title": "Red PR",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "head": {"sha": "head123"},
    })
    orch.github.fetch_pr_review_decision = MagicMock(return_value="APPROVED")
    orch.github.fetch_check_runs = MagicMock(return_value=[
        {"name": "test", "conclusion": "failure"}
    ])
    res = orch.evaluate_pr_merge_readiness(3)
    assert res["is_eligible"] is False
    assert "Head commit has failing check runs" in res["reason"]

    # 4. Conflicting
    orch.github.fetch_pr_details = MagicMock(return_value={
        "title": "Conflicting PR",
        "draft": False,
        "mergeable": False,
        "mergeable_state": "dirty",
        "head": {"sha": "head123"},
    })
    orch.github.fetch_pr_review_decision = MagicMock(return_value="APPROVED")
    orch.github.fetch_check_runs = MagicMock(return_value=[])
    res = orch.evaluate_pr_merge_readiness(4)
    assert res["is_eligible"] is False
    assert "Mergeable status is CONFLICTING" in res["reason"]


@patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"})
def test_merge_approved_dry_run_and_execute():
    """Test dry-run preview and execute modes for merge_approved."""
    orch = Orchestrator()
    orch.list_prs = MagicMock(return_value={"prs": [{"number": 10}, {"number": 20}]})

    def fake_readiness(pr_num, **_kwargs):
        if pr_num == 10:
            return {
                "pr_number": 10,
                "title": "PR 10",
                "draft": False,
                "review_decision": "APPROVED",
                "has_failing_checks": False,
                "mergeable": "MERGEABLE",
                "is_eligible": True,
                "reason": None,
            }
        return {
            "pr_number": 20,
            "title": "PR 20",
            "draft": False,
            "review_decision": None,
            "has_failing_checks": False,
            "mergeable": "MERGEABLE",
            "is_eligible": False,
            "reason": "Review decision is unapproved",
        }

    orch.evaluate_pr_merge_readiness = MagicMock(side_effect=fake_readiness)
    orch.github.merge_pull_request = MagicMock(return_value={"message": "Pull Request successfully merged"})

    # Test Dry Run
    dry_res = orch.merge_approved(repo="owner/repo", execute=False)
    assert dry_res["mode"] == "dry-run"
    assert dry_res["total_evaluated"] == 2
    assert dry_res["eligible_count"] == 1
    assert dry_res["merged_count"] is None
    assert dry_res["results"][0]["is_eligible"] is True
    assert dry_res["results"][1]["is_eligible"] is False
    orch.github.merge_pull_request.assert_not_called()

    # Test Execute (console credential present)
    with patch.dict("os.environ", {"S5_CONSOLE_MERGE_TOKEN": "console-test"}):
        exec_res = orch.merge_approved(repo="owner/repo", execute=True)
    assert exec_res["mode"] == "execute"
    assert exec_res["total_evaluated"] == 2
    assert exec_res["eligible_count"] == 1
    assert exec_res["merged_count"] == 1
    assert exec_res["results"][0]["merged"] is True
    assert exec_res["results"][1]["merged"] is False
    orch.github.merge_pull_request.assert_called_once_with(
        10,
        commit_title="Merge pull request #10 from owner/repo",
        repo="owner/repo",
    )


def test_merge_approved_execute_refused_without_console_credential():
    """Execute without S5_CONSOLE_MERGE_TOKEN merges nothing (#1163)."""
    with patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token"}):
        orch = Orchestrator()
        orch.list_prs = MagicMock(return_value={"prs": [{"number": 10}]})
        orch.evaluate_pr_merge_readiness = MagicMock(return_value={
            "pr_number": 10,
            "is_eligible": True,
            "reason": None,
        })
        orch.github.merge_pull_request = MagicMock()
        os.environ.pop("S5_CONSOLE_MERGE_TOKEN", None)
        res = orch.merge_approved(repo="owner/repo", execute=True)
        assert res["status"] == "refused"
        assert res["merged_count"] == 0
        assert res["results"] == []
        assert "S5_CONSOLE_MERGE_TOKEN" in res["reason"]
        orch.github.merge_pull_request.assert_not_called()
        orch.list_prs.assert_not_called()
        orch.evaluate_pr_merge_readiness.assert_not_called()


def test_cli_agent_merge_approved():
    """Test CLI invocation of td agent merge-approved."""
    runner = CliRunner()
    with patch("dev_tools.orchestrator.Orchestrator.merge_approved") as mock_merge:
        mock_merge.return_value = {
            "status": "success",
            "mode": "dry-run",
            "total_evaluated": 1,
            "eligible_count": 1,
            "merged_count": None,
            "results": [
                {
                    "pr_number": 101,
                    "title": "Good PR",
                    "draft": False,
                    "review_decision": "APPROVED",
                    "has_failing_checks": False,
                    "mergeable": "MERGEABLE",
                    "is_eligible": True,
                    "reason": None,
                }
            ],
        }

        result = runner.invoke(cli, ["agent", "merge-approved", "-r", "test/repo"])
        assert result.exit_code == 0
        assert '"eligible_count": 1' in result.output
