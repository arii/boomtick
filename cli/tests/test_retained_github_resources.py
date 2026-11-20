"""Retained GitHub resource APIs still dispatch through the composed client."""

from unittest.mock import Mock

from dev_tools.services.github import GitHubClient


def test_retained_pull_read_operations():
    client = GitHubClient(token="offline-token", repo="owner/repo", no_cache=True)
    client._request = Mock(return_value={"ok": True})
    assert client.fetch_pr_details(17) == {"ok": True}
    client._request.assert_called_once_with("GET", "/repos/owner/repo/pulls/17")
    client._request.reset_mock()
    client.fetch_pr_files(17, repo="other/repo")
    client._request.assert_called_once_with(
        "GET", "/repos/other/repo/pulls/17/files", ttl=600
    )


def test_retained_issue_write_operations():
    client = GitHubClient(token="offline-token", repo="owner/repo", no_cache=True)
    client._request = Mock(
        return_value={"number": 7, "html_url": "offline", "state": "open"}
    )
    assert client.create_issue("title", "body")["number"] == 7
    client._request.assert_called_once_with(
        "POST", "/repos/owner/repo/issues", json_data={"title": "title", "body": "body"}
    )
    client._request.reset_mock()
    client.create_issue_comment(7, "comment", repo="other/repo")
    client._request.assert_called_once_with(
        "POST", "/repos/other/repo/issues/7/comments", json_data={"body": "comment"}
    )


def test_retained_check_read_operation():
    client = GitHubClient(token="offline-token", repo="owner/repo", no_cache=True)
    client._request = Mock(return_value={"check_runs": [{"id": 1}]})
    assert client.fetch_check_runs("sha")[0]["id"] == 1
    client._request.assert_called_once_with(
        "GET", "/repos/owner/repo/commits/sha/check-runs"
    )
