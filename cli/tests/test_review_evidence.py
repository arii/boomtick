"""Deterministic review must not manufacture approval or runtime evidence."""

from unittest.mock import Mock

import pytest
from dev_tools.handlers.command_handler import CommandHandler
from dev_tools.orchestrator import Orchestrator


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [{"name": "tests", "status": "queued", "conclusion": None}],
        [{"name": "tests", "status": "completed", "conclusion": "success"}],
    ],
)
def test_rules_never_approve(runs):
    orch = Orchestrator()
    orch._github = Mock()
    orch.github.fetch_pr_details.return_value = {
        "number": 1,
        "head": {"sha": "abc"},
        "mergeable": True,
    }
    orch.github.fetch_check_runs.return_value = runs
    orch.github.fetch_pr_diff.return_value = (
        "+++ b/src/example.ts\n+export const value = 1"
    )
    result = orch.review_pr(1)
    assert result["recommendation"] == "Review Required"
    assert result["modelUsed"] is False
    assert result["reviewMode"] == "deterministic-heuristics"
    assert "src/example.ts" in result["reviewComment"]
    assert "All CI checks" not in result["reviewComment"]
    assert "console errors" not in result["reviewComment"]
    assert "No model was called" in result["reviewComment"]
    handler = CommandHandler(orch)
    handler.handle(1, "/ai-review")
    assert orch.github.create_review.call_args.args[-1] == "COMMENT"


def test_no_diff_or_checks_remains_unverified():
    orch = Orchestrator()
    text = orch.evaluate_pr_heuristics({"number": 2}, "", {"check_runs": []})
    assert "diff coverage is unverified" in text
    assert "CI status is unverified" in text
    assert "Human review is still required" in text


def test_deleted_and_binary_files_are_listed():
    orch = Orchestrator()
    diff = "diff --git a/old.txt b/old.txt\n--- a/old.txt\n+++ /dev/null\ndiff --git a/image.png b/image.png\nBinary files differ"
    assert orch._review_files(diff) == ["image.png", "old.txt"]


def test_merge_conflict_blocks_recommendation():
    orch = Orchestrator()
    orch._github = Mock()
    orch.github.fetch_pr_details.return_value = {
        "number": 3,
        "head": {"sha": "abc"},
        "mergeable": False,
    }
    orch.github.fetch_check_runs.return_value = []
    orch.github.fetch_pr_diff.return_value = "+++ b/test.txt\n+data"
    assert orch.review_pr(3)["recommendation"] == "Not Approved"
