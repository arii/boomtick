import unittest
from unittest.mock import patch, MagicMock
from tdw_services.services.github import GitHubClient
from tdw_services.orchestrator import Orchestrator
from tdw_services.utils import CLIError

class TestLabels(unittest.TestCase):
    def setUp(self):
        patcher = patch('dev_tools.utils.get_github_token')
        self.mock_token = patcher.start()
        self.mock_token.return_value = "dummy_token"
        self.addCleanup(patcher.stop)

        # Mock GitHubClient for Orchestrator tests
        self.orch = Orchestrator()
        self.orch._github = MagicMock(spec=GitHubClient)

    @patch('tdw_services.services.github.requests.Session.request')
    def test_github_client_update_issue_labels(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {"number": 123, "labels": [{"name": "bug"}]}
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = GitHubClient(token="fake_token", repo="owner/repo")
        client.update_issue(123, labels=["bug"])

        # Verify PATCH request
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], 'PATCH')
        self.assertIn('/issues/123', call_args[0][1])
        self.assertEqual(call_args[1]['json']['labels'], ["bug"])

    @patch('tdw_services.services.github.requests.Session.request')
    def test_github_client_remove_label(self, mock_request):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        client = GitHubClient(token="fake_token", repo="owner/repo")
        client.remove_label(123, "ui bug")

        # Verify DELETE request with encoded label
        call_args = mock_request.call_args
        self.assertEqual(call_args[0][0], 'DELETE')
        self.assertIn('/issues/123/labels/ui%20bug', call_args[0][1])

    def test_orchestrator_update_issue_add_labels(self):
        self.orch.update_issue(123, add_labels=["new-label"])
        self.orch.github.add_labels.assert_called_once_with(123, ["new-label"])

    def test_orchestrator_update_issue_remove_labels(self):
        self.orch.update_issue(123, remove_labels=["old-label"])
        self.orch.github.remove_label.assert_called_once_with(123, "old-label")

    def test_orchestrator_update_issue_full_labels(self):
        self.orch.update_issue(123, labels=["l1", "l2"])
        self.orch.github.update_issue.assert_called_once_with(123, body=None, labels=["l1", "l2"])

    def test_orchestrator_update_issue_simultaneous_add_remove(self):
        self.orch.update_issue(123, add_labels=["new"], remove_labels=["old"])
        self.orch.github.add_labels.assert_called_once_with(123, ["new"])
        self.orch.github.remove_label.assert_called_once_with(123, "old")

    def test_orchestrator_update_issue_body_validation(self):
        with self.assertRaises(CLIError) as cm:
            self.orch.update_issue(123, body="   ", add_labels=["l1"])
        self.assertEqual(str(cm.exception), "Issue body cannot be empty.")

    def test_orchestrator_update_issue_body_and_add_labels(self):
        self.orch.update_issue(123, body="new body", add_labels=["l1"])
        self.orch.github.add_labels.assert_called_once_with(123, ["l1"])
        self.orch.github.update_issue.assert_called_once_with(123, body="new body")

if __name__ == '__main__':
    unittest.main()
