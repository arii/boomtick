import unittest
from unittest.mock import patch, MagicMock
import os
import sys

from dev_tools.services.github import GitHubClient

class TestGitHubClientNoGH(unittest.TestCase):
    @patch('dev_tools.services.github.requests.Session.request')
    @patch('dev_tools.services.github.subprocess.run')
    def test_fetch_check_runs_no_gh(self, mock_run, mock_request):
        # Mock requests response
        mock_response = MagicMock()
        mock_response.json.return_value = {"check_runs": []}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = GitHubClient(token="fake_token", repo="owner/repo")
        client.fetch_check_runs("fake_ref")

        # Verify subprocess.run was NOT called with 'gh'
        for call in mock_run.call_args_list:
            args = call[0][0]
            if isinstance(args, list) and args[0] == "gh":
                self.fail(f"gh was called with {args}")

    @patch('dev_tools.services.github.requests.Session.request')
    def test_list_pull_requests_pagination(self, mock_request):
        mock_response1 = MagicMock()
        mock_response1.json.return_value = [{"number": i, "user": {"login": "u"}, "head": {"ref": "h"}, "base": {"ref": "b"}} for i in range(1, 101)]
        mock_response1.status_code = 200
        mock_response1.raise_for_status.return_value = None

        mock_response2 = MagicMock()
        mock_response2.json.return_value = [{"number": 101, "user": {"login": "u"}, "head": {"ref": "h"}, "base": {"ref": "b"}}]
        mock_response2.status_code = 200
        mock_response2.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response1, mock_response2]

        client = GitHubClient(token="fake_token", repo="owner/repo")
        prs = client.list_pull_requests(limit=105)

        self.assertEqual(len(prs), 101)
        self.assertEqual(mock_request.call_count, 2)

        # Verify params
        # Verify params
        call1_kwargs = mock_request.call_args_list[0][1]
        params1 = call1_kwargs.get('params', {})
        self.assertEqual(params1.get('page'), 1)
        self.assertEqual(params1.get('per_page'), 100)

        call2_kwargs = mock_request.call_args_list[1][1]
        params2 = call2_kwargs.get('params', {})
        self.assertEqual(params2.get('page'), 2)

    @patch('dev_tools.services.github.requests.Session.request')
    def test_list_pull_requests_labels_search(self, mock_request):
        # Mocks Search API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {"number": 123, "title": "Bug PR", "user": {"login": "u"}, "draft": False, "updated_at": "2023", "html_url": "url"}
            ]
        }
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = GitHubClient(token="fake_token", repo="owner/repo")
        prs = client.list_pull_requests(labels=["bug", "ui"])

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['number'], 123)

        # Verify endpoint and query params
        call_args_list = mock_request.call_args_list
        self.assertIn("/search/issues", call_args_list[0][0][1])
        params = call_args_list[0][1].get('params', {})
        self.assertIn('label:"bug"', params.get('q', ''))
        self.assertIn('label:"ui"', params.get('q', ''))

    @patch('dev_tools.services.github.requests.Session.request')
    @patch('dev_tools.services.github.subprocess.run')
    def test_list_pull_requests_no_gh(self, mock_run, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = GitHubClient(token="fake_token", repo="owner/repo")
        client.list_pull_requests(limit=10)

        # Verify subprocess.run was NOT called with 'gh'
        for call in mock_run.call_args_list:
            args = call[0][0]
            if isinstance(args, list) and args[0] == "gh":
                self.fail(f"gh was called with {args}")

if __name__ == "__main__":
    unittest.main()
