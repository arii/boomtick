"""
Unit tests for the ContextBuilder service.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from dev_tools.services.context_builder import ContextBuilder


class TestContextBuilder(unittest.TestCase):
    """Unit tests for the ContextBuilder service class."""

    def setUp(self) -> None:
        self.mock_github = MagicMock()
        self.builder = ContextBuilder(github_client=self.mock_github)

    def test_init(self) -> None:
        """Test initial state of ContextBuilder."""
        self.assertEqual(self.builder.pr_details, {})
        self.assertEqual(self.builder.pr_diff, "")
        self.assertEqual(self.builder.file_tree, {})
        self.assertEqual(self.builder.linked_issues, [])
        self.assertEqual(self.builder.extra_context, {})
        self.assertEqual(self.builder.scratch_pad, [])

    def test_scratch_pad_operations(self) -> None:
        """Test adding, reading, and clearing scratch pad entries."""
        self.builder.add_scratch_note("reviewer", "Code looks good.")
        self.builder.add_scratch_note("auditor", "File tree is compliant.")

        self.assertEqual(len(self.builder.scratch_pad), 2)
        self.assertEqual(self.builder.scratch_pad[0]["role"], "reviewer")
        self.assertEqual(self.builder.scratch_pad[0]["note"], "Code looks good.")
        self.assertEqual(self.builder.scratch_pad[1]["role"], "auditor")
        self.assertEqual(self.builder.scratch_pad[1]["note"], "File tree is compliant.")

        self.builder.clear_scratch_pad()
        self.assertEqual(self.builder.scratch_pad, [])

    def test_ingest_pr(self) -> None:
        """Test PR detail and diff ingestion."""
        mock_details = {"number": 12, "title": "Feat: Add something", "body": "PR description", "state": "open"}
        mock_diff = "diff --git a/src/app.tsx b/src/app.tsx\n+++ b/src/app.tsx\n+added line"

        self.mock_github.fetch_pr_details.return_value = mock_details
        self.mock_github.fetch_pr_diff.return_value = mock_diff

        self.builder.ingest_pr(12)

        self.assertEqual(self.builder.pr_details, mock_details)
        self.assertEqual(self.builder.pr_diff, mock_diff)
        self.mock_github.fetch_pr_details.assert_called_once_with(12)
        self.mock_github.fetch_pr_diff.assert_called_once_with(12)

    def test_ingest_pr_error_handling(self) -> None:
        """Test error handling when PR fetch fails."""
        self.mock_github.fetch_pr_details.side_effect = Exception("API limit")

        self.builder.ingest_pr(15)

        self.assertIn("error", self.builder.pr_details)
        self.assertIn("Error fetching diff", self.builder.pr_diff)

    def test_ingest_linked_issue(self) -> None:
        """Test linked issue details ingestion and normalization."""
        mock_raw_issue = {
            "number": 42,
            "title": "Fix crash",
            "body": "App crashes on launch",
            "state": "open",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/owner/repo/issues/42",
        }
        mock_normalized = {
            "number": 42,
            "title": "Fix crash",
            "body": "App crashes on launch",
            "state": "open",
            "html_url": "https://github.com/owner/repo/issues/42",
            "labels": ["bug"],
        }
        self.mock_github.fetch_issue_details.return_value = mock_raw_issue
        self.mock_github.normalize_issue.return_value = mock_normalized

        self.builder.ingest_linked_issue(42)

        self.assertEqual(len(self.builder.linked_issues), 1)
        self.assertEqual(self.builder.linked_issues[0], mock_normalized)

    def test_ingest_linked_issue_error_handling(self) -> None:
        """Test error handling when issue fetch fails."""
        self.mock_github.fetch_issue_details.side_effect = Exception("Not found")

        self.builder.ingest_linked_issue(999)

        self.assertEqual(len(self.builder.linked_issues), 1)
        self.assertEqual(self.builder.linked_issues[0]["number"], 999)
        self.assertIn("error", self.builder.linked_issues[0])

    def test_ingest_file_tree(self) -> None:
        """Test walking directory layout to build file tree context."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create subdirectories and files
            os.makedirs(os.path.join(tmp_dir, "src", "components"))
            os.makedirs(os.path.join(tmp_dir, "node_modules"))  # Should be ignored
            os.makedirs(os.path.join(tmp_dir, ".git"))  # Should be ignored

            with open(os.path.join(tmp_dir, "src", "app.tsx"), "w", encoding="utf-8") as f:
                f.write("app content")
            with open(os.path.join(tmp_dir, "src", "components", "Button.tsx"), "w", encoding="utf-8") as f:
                f.write("button content")
            with open(os.path.join(tmp_dir, "package.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            self.builder.ingest_file_tree(root_dir=tmp_dir, max_depth=3)

            # Assert node_modules and .git are ignored
            self.assertNotIn("node_modules/", self.builder.file_tree)
            self.assertNotIn(".git/", self.builder.file_tree)

            # Assert expected layout is present
            self.assertIn("package.json", self.builder.file_tree)
            self.assertIn("src/", self.builder.file_tree)
            self.assertIn("components/", self.builder.file_tree["src/"])
            self.assertIsNone(self.builder.file_tree["src/"]["app.tsx"])
            self.assertIsNone(self.builder.file_tree["src/"]["components/"]["Button.tsx"])

    def test_add_extra_context(self) -> None:
        """Test adding supplemental context evidence."""
        self.builder.add_extra_context("ci_logs", "npm run test failed at line 12")
        self.assertEqual(self.builder.extra_context["ci_logs"], "npm run test failed at line 12")

    def test_build_structured_context(self) -> None:
        """Test creating structured dictionary for the programmatic agent."""
        mock_details = {"number": 100, "title": "Feature X", "body": "Add feature X", "state": "closed"}
        mock_diff = "diff --git a/src/index.ts b/src/index.ts\n+++ b/src/index.ts\n+export * from './x';"
        self.mock_github.fetch_pr_details.return_value = mock_details
        self.mock_github.fetch_pr_diff.return_value = mock_diff

        self.builder.ingest_pr(100)
        self.builder.file_tree = {"package.json": None}
        self.builder.add_extra_context("test_run", "success")
        self.builder.add_scratch_note("reviewer", "My note")

        context = self.builder.build_structured_context(step_name="testing")

        self.assertEqual(context["step"], "testing")
        self.assertEqual(context["pr"]["number"], 100)
        self.assertEqual(context["pr"]["changed_files"], ["src/index.ts"])
        self.assertEqual(context["file_tree"], {"package.json": None})
        self.assertEqual(context["extra"], {"test_run": "success"})
        self.assertEqual(context["scratch_pad"], [{"role": "reviewer", "note": "My note"}])

    def test_build_markdown_context(self) -> None:
        """Test generating Markdown prompt context formatted for LLM consumption."""
        mock_details = {"number": 1, "title": "Example", "body": "Example description", "state": "open"}
        mock_diff = "diff --git a/src/app.ts b/src/app.ts\n+++ b/src/app.ts"
        self.mock_github.fetch_pr_details.return_value = mock_details
        self.mock_github.fetch_pr_diff.return_value = mock_diff

        self.builder.ingest_pr(1)
        self.builder.file_tree = {"src/": {"app.ts": None}}
        self.builder.ingest_linked_issue(123)
        self.builder.add_scratch_note("reviewer", "Reviewed successfully.")

        # 1. Review step context
        review_md = self.builder.build_markdown_context("review")
        self.assertIn("# Agent Task Execution Context — Step: REVIEW", review_md)
        self.assertIn("Perform a strict code review", review_md)
        self.assertIn("Pull Request #1: Example", review_md)
        self.assertIn("Repository File Layout Structure", review_md)
        self.assertIn("Agent Scratch Pad (Shared Multi-Role Thinking State)", review_md)
        self.assertIn("Note by Role: REVIEWER", review_md)
        self.assertIn("Reviewed successfully.", review_md)

        # 2. Audit step context
        audit_md = self.builder.build_markdown_context("audit")
        self.assertIn("# Agent Task Execution Context — Step: AUDIT", audit_md)
        self.assertIn("Perform a whole-repository compliance", audit_md)

        # 3. Repair step context
        repair_md = self.builder.build_markdown_context("repair")
        self.assertIn("# Agent Task Execution Context — Step: REPAIR", repair_md)
        self.assertIn("Resolve merge conflicts, bugs, or CI failures", repair_md)


if __name__ == "__main__":
    unittest.main()
