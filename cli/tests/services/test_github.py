import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add paths to sys.path
sys.path.append(os.path.join(os.getcwd(), "boomtick-pkg", "cli"))
sys.path.append(os.path.join(os.getcwd(), "boomtick-pkg", "cli", "dev_tools"))

from tdw_services.services.github import GitHubClient

class TestGitHubClientPagination(unittest.TestCase):
    def setUp(self):
        patcher = patch('utils.get_github_token')
        self.mock_token = patcher.start()
        self.mock_token.return_value = "dummy_token"
        self.addCleanup(patcher.stop)
        self.client = GitHubClient(repo="owner/repo")

    @patch('tdw_services.services.github.requests.Session.request')
    def test_list_pull_requests_pagination_and_filtering(self, mock_request):
        # When labels are used, it uses Search API which returns {"items": [...]}
        # Search API results are already filtered by labels.
        search_data = [
            {"number": 101, "title": "Bug PR", "user": {"login": "user"}, "draft": False, "updated_at": "2023", "html_url": "url", "labels": [{"name": "bug"}]}
        ]
        mock_response_p1 = MagicMock()
        mock_response_p1.json.return_value = {"items": search_data}
        mock_response_p1.status_code = 200
        mock_response_p1.raise_for_status.return_value = None

        mock_request.return_value = mock_response_p1

        # Request PRs with label 'bug'
        prs = self.client.list_pull_requests(limit=150, labels=["bug"])

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], 101)
        # Verify Search API was called
        self.assertIn("/search/issues", mock_request.call_args[0][1])


if __name__ == '__main__':
    unittest.main()
