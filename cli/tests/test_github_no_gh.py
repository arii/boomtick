import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Setup PYTHONPATH
sys.path.insert(0, os.path.abspath("boomtick-pkg/cli"))
sys.path.insert(0, os.path.abspath("boomtick-pkg/cli/dev_tools"))

from tdw_services.services.github import GitHubClient

class TestGitHubClientNoGH(unittest.TestCase):
    @patch('tdw_services.services.github.requests.Session.request')
    @patch('tdw_services.services.github.subprocess.run')
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

    @patch('tdw_services.services.github.requests.Session.request')
    def test_list_pull_requests_pagination(self, mock_request):
        mock_response1 = MagicMock()
        mock_response1.json.return_value = [{"number": i} for i in range(1, 101)]
        mock_response1.status_code = 200

        mock_response2 = MagicMock()
        mock_response2.json.return_value = [{"number": 101}]
        mock_response2.status_code = 200

        mock_request.side_effect = [mock_response1, mock_response2]

        client = GitHubClient(token="fake_token", repo="owner/repo")
        prs = client.list_pull_requests(limit=105)

        self.assertEqual(len(prs), 101)
        self.assertEqual(mock_request.call_count, 2)

        # Verify params
        call1_params = mock_request.call_args_list[0][1]['params']
        self.assertEqual(call1_params['page'], 1)
        self.assertEqual(call1_params['per_page'], 100)

        call2_params = mock_request.call_args_list[1][1]['params']
        self.assertEqual(call2_params['page'], 2)

    @patch('tdw_services.services.github.requests.Session.request')
    def test_list_pull_requests_labels_search(self, mock_request):
        # Search response
        mock_search_res = MagicMock()
        mock_search_res.json.return_value = {"items": [{"number": 123}]}
        mock_search_res.status_code = 200

        # Details response
        mock_details_res = MagicMock()
        mock_details_res.json.return_value = {"number": 123, "title": "Bug PR"}
        mock_details_res.status_code = 200

        mock_request.side_effect = [mock_search_res, mock_details_res]

        client = GitHubClient(token="fake_token", repo="owner/repo")
        prs = client.list_pull_requests(labels=["bug", "ui"])

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['number'], 123)

        # Verify search query
        call_args_list = mock_request.call_args_list
        self.assertEqual(call_args_list[0][0][1], "https://api.github.com/search/issues")
        q = call_args_list[0][1]['params']['q']
        self.assertIn("repo:owner/repo", q)
        self.assertIn("is:pr", q)
        self.assertIn('label:"bug"', q)
        self.assertIn('label:"ui"', q)

    @patch('tdw_services.services.github.requests.Session.request')
    @patch('tdw_services.services.github.subprocess.run')
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
