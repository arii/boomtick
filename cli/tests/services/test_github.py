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


def test_fetch_pr_info_graphql():
    with patch("dev_tools.utils.get_github_token", return_value="dummy_token"), patch(
        "dev_tools.services.github.DiskCache"
    ) as mock_cache:
        mock_cache.return_value.get.return_value = None
        client = GitHubClient(repo="owner/repo")

        # Mock Response of GraphQL query
        graphql_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "title": "My GraphQL PR",
                        "body": "This is body",
                        "author": {
                            "login": "testauthor"
                        },
                        "headRefName": "my-head-branch",
                        "headRefOid": "head-sha-123",
                        "baseRefName": "main",
                        "files": {
                            "nodes": [
                                {"path": "file1.py"},
                                {"path": "file2.py"}
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(client, "_request", return_value=graphql_response) as mock_request:
            result = client.fetch_pr_info_graphql(123)

            # Verify _request was called
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "POST"
            assert args[1] == "/graphql"
            json_data = kwargs.get("json_data", {})
            assert "query getPrInfo" in json_data.get("query", "")
            assert json_data.get("variables", {}).get("prNumber") == 123

            # Verify returned REST-compatible dictionary
            assert result["pr"]["title"] == "My GraphQL PR"
            assert result["pr"]["body"] == "This is body"
            assert result["pr"]["user"]["login"] == "testauthor"
            assert result["pr"]["head"]["ref"] == "my-head-branch"
            assert result["pr"]["head"]["sha"] == "head-sha-123"
            assert result["pr"]["base"]["ref"] == "main"
            assert result["files"] == [{"filename": "file1.py"}, {"filename": "file2.py"}]


if __name__ == "__main__":
    unittest.main()
