# pylint: disable=missing-docstring,protected-access,redefined-outer-name
from unittest.mock import MagicMock, mock_open, patch

import pytest
from dev_tools.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    with patch("dev_tools.orchestrator.GitHubClient"), patch("dev_tools.orchestrator.get_config"):
        orch = Orchestrator()
        orch._github = MagicMock()
        return orch


def test_generate_aggregation_workflow_logic(orchestrator):
    # Mock PR details
    orchestrator.github.fetch_pr_details.side_effect = lambda pr_num: {
        "number": pr_num,
        "title": f"PR {pr_num} [with brackets]",
        "user": {"login": f"user_{pr_num}"},
    }

    # Mock PR files
    orchestrator.github.fetch_pr_files.side_effect = lambda pr_num: [
        {"filename": "overlapping_file.py"},
        {"filename": f"unique_to_{pr_num}.py"},
    ]

    # Mock PR diff with overlapping hunks
    orchestrator.github.fetch_pr_diff.side_effect = lambda pr_num: (
        "+++ b/overlapping_file.py\n" "@@ -10,5 +10,5 @@\n" "+content\n"
    )

    # Mock runtime check
    orchestrator.runtime_check = MagicMock(return_value={"node": "24.x", "pnpm": "10.x"})

    # Mock log directories and file operations
    with patch("dev_tools.orchestrator.get_or_create_log_dir", return_value="/tmp/logs"), patch(
        "builtins.open", mock_open()
    ) as mocked_file:

        res = orchestrator.generate_aggregation_workflow([3281, 3282], "feat/test-aggregation")

        assert res["status"] == "success"
        # Verify sanitized target in filenames
        assert "workflow-plan-aggregation-feat-test-aggregation.md" in res["plan_path"]
        assert "aggregation-context-feat-test-aggregation.md" in res["context_path"]
        assert "aggregation-plan-feat-test-aggregation.md" in res["skeleton_path"]

        # Verify Github API calls
        assert orchestrator.github.fetch_pr_details.call_count == 2
        assert orchestrator.github.fetch_pr_files.call_count == 2
        assert orchestrator.github.fetch_pr_diff.call_count == 2

        # Verify content was written (at least once for each of the 3 files)
        assert mocked_file.call_count >= 3

        # Capture all written content to verify escaping
        written_content = "".join(call.args[0] for call in mocked_file().write.call_args_list)
        assert "PR 3281 \\[with brackets\\]" in written_content
        assert "overlapping_file.py" in written_content
        assert "overlap at lines 10-14" in written_content
