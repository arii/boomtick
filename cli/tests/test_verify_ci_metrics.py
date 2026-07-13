# pylint: disable=missing-docstring
import json
import unittest
from unittest.mock import patch
from dev_tools.utils import verify_ci_metrics

class TestVerifyMetrics(unittest.TestCase):
    def setUp(self):
        # Default thresholds
        self.input_threshold = 800000
        self.output_threshold = 200000
        self.total_threshold = 1000000

    @patch('dev_tools.utils.Path.exists')
    @patch('dev_tools.utils.get_or_create_log_dir')
    def test_verify_ci_metrics_missing_logs(self, mock_get_log_dir, mock_exists):
        # Mocking Path.exists to return False
        mock_exists.return_value = False
        mock_get_log_dir.return_value = "/tmp/ai"

        result = verify_ci_metrics(
            input_threshold=self.input_threshold,
            output_threshold=self.output_threshold,
            total_threshold=self.total_threshold
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "No AI usage logs found. Assuming 0 tokens used.")
        self.assertEqual(result["metrics"]["inputTokens"], 0)
        self.assertEqual(result["metrics"]["outputTokens"], 0)
        self.assertEqual(result["metrics"]["totalTokens"], 0)

    @patch('dev_tools.utils.Path.exists')
    @patch('dev_tools.utils.Path.open')
    @patch('dev_tools.utils.get_or_create_log_dir')
    def test_verify_ci_metrics_success(self, mock_get_log_dir, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_get_log_dir.return_value = "/tmp/ai"

        # Mocking jsonl file content
        log_content = [
            json.dumps({"inputTokens": 100, "outputTokens": 50}),
            json.dumps({"inputTokens": 200, "outputTokens": 100}),
        ]
        mock_open.return_value.__enter__.return_value = log_content

        result = verify_ci_metrics(
            input_threshold=self.input_threshold,
            output_threshold=self.output_threshold,
            total_threshold=self.total_threshold
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metrics"]["inputTokens"], 300)
        self.assertEqual(result["metrics"]["outputTokens"], 150)
        self.assertEqual(result["metrics"]["totalTokens"], 450)

    @patch('dev_tools.utils.Path.exists')
    @patch('dev_tools.utils.Path.open')
    @patch('dev_tools.utils.get_or_create_log_dir')
    def test_verify_ci_metrics_exceed_threshold(self, mock_get_log_dir, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_get_log_dir.return_value = "/tmp/ai"

        # Mocking logs that exceed threshold
        log_content = [
            json.dumps({"inputTokens": 500000, "outputTokens": 0}),
        ]
        mock_open.return_value.__enter__.return_value = log_content

        result = verify_ci_metrics(
            input_threshold=100000,
            output_threshold=100000,
            total_threshold=1000000
        )

        self.assertEqual(result["status"], "error")
        expected_msg = "AI Token threshold exceeded: Input tokens (500000) exceeded limit (100000)"
        self.assertEqual(result["message"], expected_msg)

if __name__ == "__main__":
    unittest.main()
