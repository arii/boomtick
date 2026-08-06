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


class TestGitHubClientGraphQL(unittest.TestCase):
    def setUp(self):
        with patch("dev_tools.utils.get_github_token") as mock_token:
            mock_token.return_value = "dummy_token"
            with patch("dev_tools.services.github.DiskCache") as mock_cache:
                mock_cache.return_value.get.return_value = None
                self.client = GitHubClient(repo="owner/repo")

    @patch("dev_tools.services.github.requests.Session.post")
    def test_graphql_query_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"repository": {"id": "repo_123"}}}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        res = self.client.graphql("query { id }", {"var": "val"})

        self.assertEqual(res, {"data": {"repository": {"id": "repo_123"}}})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("/graphql", args[0])
        self.assertEqual(kwargs["json"], {"query": "query { id }", "variables": {"var": "val"}})
        self.assertEqual(kwargs["headers"], {"Accept": "application/json"})

    @patch("dev_tools.services.github.requests.Session.post")
    def test_graphql_query_errors(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"errors": [{"message": "Field 'invalid' doesn't exist"}]}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with self.assertRaises(CLIError) as context:
            self.client.graphql("query { invalid }")
        self.assertIn("Field 'invalid' doesn't exist", str(context.exception))

    @patch("dev_tools.services.github.GitHubClient.graphql")
    def test_add_labels_graphql_single_request_and_caching(self, mock_graphql):
        # 1st call to graphql: _resolve_node_ids (returns issue ID and label ID)
        resolve_response = {
            "data": {
                "repository": {
                    "issueOrPullRequest": {"id": "issue_node_123"},
                    "labels": {"nodes": [{"id": "label_node_bug", "name": "bug"}]},
                }
            }
        }
        # 2nd call: addLabelsToLabelable mutation
        mutation_response = {
            "data": {
                "addLabelsToLabelable": {
                    "labelable": {
                        "number": 123,
                        "title": "A Bug Issue",
                        "url": "https://github.com/owner/repo/issues/123",
                        "state": "OPEN",
                    }
                }
            }
        }
        mock_graphql.side_effect = [resolve_response, mutation_response, mutation_response]

        # First call: should query then mutate
        res1 = self.client.add_labels(123, ["bug"])
        self.assertEqual(res1["number"], 123)
        self.assertEqual(res1["title"], "A Bug Issue")
        self.assertEqual(res1["html_url"], "https://github.com/owner/repo/issues/123")
        self.assertEqual(res1["state"], "open")

        self.assertEqual(mock_graphql.call_count, 2)

        # Second call: since issue node ID and label node ID are now cached,
        # it should directly execute mutation without calling _resolve_node_ids' query!
        res2 = self.client.add_labels(123, ["bug"])
        self.assertEqual(res2["number"], 123)
        self.assertEqual(mock_graphql.call_count, 3)

    @patch("dev_tools.services.github.GitHubClient.graphql")
    def test_remove_label_graphql_single_request_and_caching(self, mock_graphql):
        resolve_response = {
            "data": {
                "repository": {
                    "issueOrPullRequest": {"id": "issue_node_123"},
                    "labels": {"nodes": [{"id": "label_node_bug", "name": "bug"}]},
                }
            }
        }
        mutation_response = {
            "data": {
                "removeLabelsFromLabelable": {
                    "labelable": {
                        "number": 123,
                        "title": "A Bug Issue",
                        "url": "https://github.com/owner/repo/issues/123",
                        "state": "OPEN",
                    }
                }
            }
        }
        mock_graphql.side_effect = [resolve_response, mutation_response, mutation_response]

        # First call: should query then mutate
        res1 = self.client.remove_label(123, "bug")
        self.assertEqual(res1["number"], 123)
        self.assertEqual(mock_graphql.call_count, 2)

        # Second call: cached
        res2 = self.client.remove_label(123, "bug")
        self.assertEqual(res2["number"], 123)
        self.assertEqual(mock_graphql.call_count, 3)

    @patch("dev_tools.services.github.GitHubClient.graphql")
    @patch("dev_tools.services.github.requests.Session.request")
    def test_graphql_add_labels_fallback_to_rest(self, mock_rest_request, mock_graphql):
        # Force GraphQL to fail
        mock_graphql.side_effect = Exception("GraphQL failure")

        # Mock REST responses
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = [{"name": "bug"}]
        mock_post_response.raise_for_status.return_value = None

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "number": 123,
            "title": "REST Bug",
            "html_url": "https://rest.url",
            "state": "open",
        }
        mock_get_response.raise_for_status.return_value = None

        mock_rest_request.side_effect = [mock_post_response, mock_get_response]

        res = self.client.add_labels(123, ["bug"])

        self.assertEqual(res["number"], 123)
        self.assertEqual(res["title"], "REST Bug")
        self.assertEqual(res["html_url"], "https://rest.url")

        # Ensure REST requests were called
        self.assertEqual(mock_rest_request.call_count, 2)
        calls = mock_rest_request.call_args_list
        self.assertEqual(calls[0][0][0], "POST")
        self.assertIn("/issues/123/labels", calls[0][0][1])
        self.assertEqual(calls[1][0][0], "GET")
        self.assertIn("/issues/123", calls[1][0][1])

    @patch("dev_tools.services.github.GitHubClient.graphql")
    @patch("dev_tools.services.github.requests.Session.request")
    def test_graphql_remove_label_fallback_to_rest(self, mock_rest_request, mock_graphql):
        mock_graphql.side_effect = Exception("GraphQL failure")

        mock_delete_response = MagicMock()
        mock_delete_response.raise_for_status.return_value = None

        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {
            "number": 123,
            "title": "REST Bug",
            "html_url": "https://rest.url",
            "state": "open",
        }
        mock_get_response.raise_for_status.return_value = None

        mock_rest_request.side_effect = [mock_delete_response, mock_get_response]

        res = self.client.remove_label(123, "bug")

        self.assertEqual(res["number"], 123)
        self.assertEqual(mock_rest_request.call_count, 2)
        calls = mock_rest_request.call_args_list
        self.assertEqual(calls[0][0][0], "DELETE")
        self.assertIn("/issues/123/labels/bug", calls[0][0][1])


if __name__ == "__main__":
    unittest.main()
