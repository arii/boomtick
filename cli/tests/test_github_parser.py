import unittest
from unittest.mock import patch, mock_open
from dev_tools.services.github import GitHubClient

class TestGitHubParser(unittest.TestCase):
    @patch('dev_tools.services.github.GitHubClient.fetch_pr_details')
    @patch('dev_tools.services.github.GitHubClient.fetch_check_runs')
    @patch('dev_tools.services.github.GitHubClient.create_review')
    @patch('os.path.exists', return_value=True)
    def test_submit_pr_review_multiple_json_blocks(self, mock_exists, mock_create, mock_checks, mock_details):
        mock_details.return_value = {'head': {'sha': 'dummy'}, 'labels': []}
        mock_checks.return_value = []

        # Test finding metadata when there's an earlier code sample
        content = """Here is a review.

```json
{
  "code": "sample"
}
```

Some more text.

```json
{
  "recommendation": "Approved",
  "labels": ["lgtm"],
  "comments": []
}
```
"""
        with patch('builtins.open', mock_open(read_data=content)):
            client = GitHubClient(token="dummy", repo="owner/repo")
            client.submit_pr_review(1, "fake_path", dry_run=False)

            mock_create.assert_called_once()
            args, kwargs = mock_create.call_args
            # Verify body is extracted correctly
            self.assertIn("Here is a review.", args[1])
            self.assertIn("Some more text.", args[1])

            # Verify metadata was parsed correctly
            self.assertEqual(args[3], "APPROVE")
            self.assertEqual(args[2], [])


    @patch('dev_tools.services.github.GitHubClient.fetch_pr_details')
    @patch('dev_tools.services.github.GitHubClient.fetch_check_runs')
    @patch('dev_tools.services.github.GitHubClient.create_review')
    @patch('os.path.exists', return_value=True)
    def test_submit_pr_review_missing_keys(self, mock_exists, mock_create, mock_checks, mock_details):
        mock_details.return_value = {'head': {'sha': 'dummy'}, 'labels': []}
        mock_checks.return_value = []

        # Missing recommendation/labels/comments should fail
        content = """Review.

```json
{
  "status": "Approved"
}
```
"""
        with patch('builtins.open', mock_open(read_data=content)):
            client = GitHubClient(token="dummy", repo="owner/repo")
            from dev_tools.utils import CLIError
            with self.assertRaises(CLIError) as context:
                client.submit_pr_review(1, "fake_path")

            self.assertIn("Could not find a valid JSON metadata block", str(context.exception))

    @patch('dev_tools.services.github.GitHubClient.fetch_pr_details')
    @patch('dev_tools.services.github.GitHubClient.fetch_check_runs')
    @patch('dev_tools.services.github.GitHubClient.create_review')
    @patch('os.path.exists', return_value=True)
    def test_submit_pr_review_missing_keys_but_valid(self, mock_exists, mock_create, mock_checks, mock_details):
        mock_details.return_value = {'head': {'sha': 'dummy'}, 'labels': []}
        mock_checks.return_value = []

        # Testing where keys are missing but valid, like missing comments or missing labels
        content = """Review.

```json
{
  "recommendation": "Approved"
}
```
"""
        with patch('builtins.open', mock_open(read_data=content)):
            client = GitHubClient(token="dummy", repo="owner/repo")
            client.submit_pr_review(1, "fake_path", dry_run=False)

            mock_create.assert_called_once()

if __name__ == '__main__':
    unittest.main()
