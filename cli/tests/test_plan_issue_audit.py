import os
import shutil
import pytest
from unittest.mock import MagicMock, patch
from dev_tools.orchestrator import Orchestrator

@pytest.fixture
def orchestrator():
    with patch('dev_tools.orchestrator.GitHubClient') as mock_gh:
        orch = Orchestrator()
        orch._github = mock_gh.return_value
        yield orch

def test_plan_issue_audit_all_open(orchestrator, tmp_path):
    # Setup mocks
    mock_issues = [
        {
            "number": 1,
            "title": "Issue 1",
            "body": "Body 1",
            "html_url": "url1",
            "labels": ["bug"],
            "state": "open"
        },
        {
            "number": 2,
            "title": "Issue 2",
            "body": "Body 2",
            "html_url": "url2",
            "labels": [],
            "state": "open"
        }
    ]
    orchestrator.github.list_issues.return_value = mock_issues

    # Mock get_or_create_log_dir and current working directory
    with patch('dev_tools.orchestrator.get_or_create_log_dir') as mock_log_dir:

        # We'll use actual file writes in the tmp_path for better verification
        mock_log_dir.return_value = str(tmp_path / "workflows")
        os.makedirs(tmp_path / "workflows", exist_ok=True)

        # Change CWD to tmp_path for the test
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            res = orchestrator.plan_issue_audit(all_open=True, limit=10)

            assert res["status"] == "success"
            assert res["issues_count"] == 2
            assert os.path.exists(".boomtick/issue-audit-status.md")

            with open(".boomtick/issue-audit-status.md", "r") as f:
                content = f.read()
                assert "# Issue Audit Status" in content
                assert "- [ ] #1: Issue 1" in content
                assert "- [ ] #2: Issue 2" in content

            assert len(res["workflow_plans"]) == 2
            plan1_path = os.path.join(str(tmp_path / "workflows"), "workflow-plan-issue-1.md")
            assert os.path.exists(plan1_path)
            with open(plan1_path, "r") as f:
                content = f.read()
                assert "# Workflow Plan: Issue #1" in content
                assert "Body 1" in content

        finally:
            os.chdir(original_cwd)

def test_plan_issue_audit_specific_issues(orchestrator, tmp_path):
    # Setup mocks
    orchestrator.github.fetch_issue_details.side_effect = [
        {"number": 10, "title": "Issue 10", "body": "Body 10", "html_url": "url10", "labels": ["feat"], "state": "open"}
    ]

    with patch('dev_tools.orchestrator.get_or_create_log_dir') as mock_log_dir:
        mock_log_dir.return_value = str(tmp_path / "workflows")
        os.makedirs(tmp_path / "workflows", exist_ok=True)

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            res = orchestrator.plan_issue_audit(issue_numbers=[10])

            assert res["status"] == "success"
            assert res["issues_count"] == 1
            assert os.path.exists(".boomtick/issue-audit-status.md")

            with open(".boomtick/issue-audit-status.md", "r") as f:
                content = f.read()
                assert "- [ ] #10: Issue 10" in content

            plan_path = os.path.join(str(tmp_path / "workflows"), "workflow-plan-issue-10.md")
            assert os.path.exists(plan_path)
        finally:
            os.chdir(original_cwd)
