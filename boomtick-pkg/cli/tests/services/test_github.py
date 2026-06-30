import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add paths to sys.path
sys.path.append(os.path.join(os.getcwd(), "boomtick-pkg", "cli"))
sys.path.append(os.path.join(os.getcwd(), "boomtick-pkg", "cli", "dev_tools"))

from tdw_services.services.github import GitHubClient

class TestGitHubClientPagination(unittest.TestCase):
    @patch('utils.get_github_token')
    def setUp(self, mock_token):
        mock_token.return_value = "dummy_token"
        self.client = GitHubClient(repo="owner/repo")

    @patch('tdw_services.services.github.requests.Session.request')
    def test_list_pull_requests_pagination_and_filtering(self, mock_request):
        # Mocking 2 pages of PRs
        # Page 1: 100 PRs, none with 'bug' label
        page1_data = [
            {"number": i, "title": f"PR {i}", "user": {"login": "user"}, "head": {"ref": "b"}, "base": {"ref": "m"}, "draft": False, "mergeable_state": "clean", "updated_at": "2023", "html_url": "url", "labels": [{"name": "feat"}]}
            for i in range(1, 101)
        ]
        mock_response_p1 = MagicMock()
        mock_response_p1.json.return_value = page1_data
        mock_response_p1.status_code = 200
        mock_response_p1.raise_for_status.return_value = None

        # Page 2: 50 PRs, one with 'bug' label
        page2_data = [
            {"number": i, "title": f"PR {i}", "user": {"login": "user"}, "head": {"ref": "b"}, "base": {"ref": "m"}, "draft": False, "mergeable_state": "clean", "updated_at": "2023", "html_url": "url", "labels": [{"name": "bug"} if i == 101 else {"name": "feat"}]}
            for i in range(101, 151)
        ]
        mock_response_p2 = MagicMock()
        mock_response_p2.json.return_value = page2_data
        mock_response_p2.status_code = 200
        mock_response_p2.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response_p1, mock_response_p2]

        # Request up to 150 PRs with label 'bug'
        prs = self.client.list_pull_requests(limit=150, labels=["bug"])

        # Should only find 1 PR
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], 101)
        # Should have called API twice to get all 150 PRs
        self.assertEqual(mock_request.call_count, 2)

if __name__ == '__main__':
    unittest.main()
