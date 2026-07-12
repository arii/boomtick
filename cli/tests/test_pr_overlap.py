# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import unittest
from unittest.mock import patch
from dev_tools.pr_overlap import get_pr_overlaps

class TestPrOverlap(unittest.TestCase):
    @patch("dev_tools.services.github.GitHubClient")
    def test_get_pr_overlaps(self, mock_github_client):
        # Setup mocks
        github = mock_github_client.return_value
        github.list_pull_requests.return_value = [
            {"number": 1, "title": "PR 1", "author": {"login": "user1"}},
            {"number": 2, "title": "PR 2", "author": {"login": "user2"}},
            {"number": 3, "title": "PR 3", "author": {"login": "user3"}},
        ]

        def mock_fetch_pr_files(pr_num):
            if pr_num == 1:
                return [{"filename": "file1.py"}, {"filename": "shared.py"}]
            if pr_num == 2:
                return [{"filename": "file2.py"}, {"filename": "shared.py"}]
            if pr_num == 3:
                return [{"filename": "file3.py"}]
            return []

        github.fetch_pr_files.side_effect = mock_fetch_pr_files

        # Execute
        clusters = get_pr_overlaps(github, limit=5)

        # Verify
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(set(cluster["prs"]), {1, 2})
        self.assertEqual(cluster["files"], ["shared.py"])
        self.assertIn(1, cluster["metadata"])
        self.assertIn(2, cluster["metadata"])
        self.assertNotIn(3, cluster["metadata"])

    @patch("dev_tools.services.github.GitHubClient")
    def test_no_overlaps(self, mock_github_client):
        # Setup mocks
        github = mock_github_client.return_value
        github.list_pull_requests.return_value = [
            {"number": 1, "title": "PR 1", "author": {"login": "user1"}},
            {"number": 2, "title": "PR 2", "author": {"login": "user2"}},
        ]

        def mock_fetch_pr_files(pr_num):
            if pr_num == 1:
                return [{"filename": "file1.py"}]
            if pr_num == 2:
                return [{"filename": "file2.py"}]
            return []

        github.fetch_pr_files.side_effect = mock_fetch_pr_files

        # Execute
        clusters = get_pr_overlaps(github, limit=5)

        # Verify
        self.assertEqual(len(clusters), 0)

if __name__ == "__main__":
    unittest.main()
