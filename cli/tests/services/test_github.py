# pylint: disable=missing-docstring
import unittest
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.services.github import GitHubClient
from dev_tools.utils import CLIError


class TestGitHubClientPagination(unittest.TestCase):
    def setUp(self):
        with patch("dev_tools.utils.get_github_token") as mock_token:
            mock_token.return_value = "dummy_token"
            # Mock DiskCache to prevent cache hits during tests
            with patch("dev_tools.services.github.DiskCache") as mock_cache:
                mock_cache.return_value.get.return_value = None
                self.client = GitHubClient(repo="owner/repo")
                self.client.repo = "owner/repo"  # Ensure repo is set if init fails

    @patch("dev_tools.services.github.requests.Session.request")
    def test_list_pull_requests_pagination_and_filtering(self, mock_request):
        # When labels are used, it uses Search API which returns {"items": [...]}
        # Search API results are already filtered by labels.
        search_data = [
            {
                "number": 101,
                "title": "Bug PR",
                "user": {"login": "user"},
                "draft": False,
                "updated_at": "2023",
                "html_url": "url",
                "labels": [{"name": "bug"}],
            }
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
        self.assertTrue(mock_request.called, "mock_request was not called")
        # Unpack call_args which is a tuple of (args, kwargs)
        args, kwargs = mock_request.call_args
        call_url = args[1] if len(args) > 1 else kwargs.get("url", "")

        self.assertIn("/search/issues", call_url)
        # mock_request is actually Session.request, so we check calls on the mock
        found_search_call = False
        for call in mock_request.call_args_list:
            if any("/search/issues" in str(arg) for arg in call.args):
                found_search_call = True
                break
        self.assertTrue(found_search_call, "Search API call not found in mock_request calls")


def test_validate_review_payload_boilerplate_rejection():
    """Ensures that payloads consisting solely of boilerplate are rejected by the validator."""
    # Payload with only placeholders in body
    payload_only_placeholders = {
        "body": "## ANTI-AI-SLOP\n<findings>",
        "recommendation": "Approved",
        "labels": [],
        "comments": [],
    }
    with pytest.raises(CLIError) as excinfo:
        GitHubClient.validate_review_payload(payload_only_placeholders)
    assert "No meaningful content found in body or comments" in str(excinfo.value)

    # Payload with placeholder in recommendation
    payload_bad_recommendation = {
        "body": "Meaningful feedback",
        "recommendation": "<Approved | Approved with Minor Changes | Not Approved>",
        "labels": [],
        "comments": [],
    }
    with pytest.raises(CLIError) as excinfo:
        GitHubClient.validate_review_payload(payload_bad_recommendation)
    assert "Recommendation contains boilerplate placeholder" in str(excinfo.value)

    # Payload with placeholder in comment
    payload_bad_comment = {
        "body": "Meaningful feedback",
        "recommendation": "Approved",
        "labels": [],
        "comments": [{"path": "file.py", "line": 1, "body": "<findings>"}],
    }
    with pytest.raises(CLIError) as excinfo:
        GitHubClient.validate_review_payload(payload_bad_comment)
    assert "Comment contains boilerplate placeholder" in str(excinfo.value)


if __name__ == "__main__":
    unittest.main()
