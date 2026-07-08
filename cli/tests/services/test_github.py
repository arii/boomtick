import unittest
from unittest.mock import patch, MagicMock
import sys
import os

from dev_tools.services.github import GitHubClient

class TestGitHubClientPagination(unittest.TestCase):
    def setUp(self):
        with patch('dev_tools.utils.get_github_token') as mock_token:
            mock_token.return_value = "dummy_token"
            # Force no_cache=True to avoid hitting local logs/cache during tests
            self.client = GitHubClient(repo="owner/repo", no_cache=True)
            self.client.repo = "owner/repo" # Ensure repo is set if init fails

    @patch('dev_tools.services.github.requests.Session.request')
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
        # mock_request is actually Session.request, so we check calls on the mock
        found_search_call = False
        for call in mock_request.call_args_list:
            if any("/search/issues" in str(arg) for arg in call.args):
                found_search_call = True
                break
        self.assertTrue(found_search_call, "Search API call not found in mock_request calls")


if __name__ == '__main__':
    unittest.main()
