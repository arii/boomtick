# pylint: disable=missing-docstring
import io
import sys
import unittest
from unittest.mock import patch

from dev_tools.orchestrator import Orchestrator


class TestOpenTelemetryCheck(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()

    @patch("dev_tools.orchestrator.run_command")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("importlib.metadata.version")
    def test_opentelemetry_versions_compatible(self, mock_version, mock_exists, mock_open, mock_run):
        # Setup mocks for standard runtime check to succeed with defaults
        mock_run.side_effect = lambda cmd, **kwargs: "24.16.0" if "node" in cmd else "10.28.2"
        mock_exists.return_value = False
        mock_open.side_effect = FileNotFoundError

        # Mock opentelemetry versions to be compatible
        mock_version.side_effect = lambda name: "1.37.0"

        # Capture output
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            res = self.orchestrator.runtime_check()
            self.assertEqual(res["node"], "24.16.0")
            self.assertEqual(res["pnpm"], "10.28.2")
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertNotIn("OpenTelemetry version conflict detected", output)

    @patch("dev_tools.orchestrator.run_command")
    @patch("builtins.open")
    @patch("os.path.exists")
    @patch("importlib.metadata.version")
    def test_opentelemetry_versions_incompatible(self, mock_version, mock_exists, mock_open, mock_run):
        # Setup mocks for standard runtime check to succeed with defaults
        mock_run.side_effect = lambda cmd, **kwargs: "24.16.0" if "node" in cmd else "10.28.2"
        mock_exists.return_value = False
        mock_open.side_effect = FileNotFoundError

        # Mock opentelemetry versions to be incompatible
        mock_version.side_effect = lambda name: "1.44.0"

        # Capture output
        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            self.orchestrator.runtime_check()
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertIn("WARNING: OpenTelemetry version conflict detected!", output)
        self.assertIn("opentelemetry-api (1.44.0)", output)
        self.assertIn("opentelemetry-sdk (1.44.0)", output)


if __name__ == "__main__":
    unittest.main()
