# pylint: disable=missing-docstring
import io
import json
import sys
import unittest
from unittest.mock import MagicMock, patch

from dev_tools.orchestrator import Orchestrator
from dev_tools.utils import CLIError


def _contract_files_present(mock_exists, mock_open):
    """Simulate present .node-version / package.json contract files (#1172)."""
    mock_exists.return_value = True

    def _open(path, *args, **kwargs):
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        if str(path) == ".node-version":
            mock_file.read.return_value = "24.16.0\n"
        else:
            mock_file.read.return_value = json.dumps({"packageManager": "pnpm@10.28.2"})
        return mock_file

    mock_open.side_effect = _open


class TestOpenTelemetryCheck(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()

    @patch("dev_tools.orchestrator.run_command")
    @patch("builtins.open")
    @patch("os.path.exists")
    def test_no_otel_gate_for_any_version(self, mock_exists, mock_open, mock_run):
        # No OpenTelemetry version gate: latest-only policy, telemetry deps
        # float transitively. runtime_check must stay silent whatever the
        # installed OTEL set is (the old 1.37.0 gate prescribed downgrades
        # that skewed the resolver and broke the RAG backend).
        mock_run.side_effect = lambda cmd, **kwargs: "24.16.0" if "node" in cmd else "10.28.2"
        _contract_files_present(mock_exists, mock_open)

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            res = self.orchestrator.runtime_check()
            self.assertEqual(res["node"], "24.16.0")
            self.assertEqual(res["pnpm"], "10.28.2")
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        self.assertNotIn("OpenTelemetry", output)

    @patch("dev_tools.orchestrator.run_command")
    @patch("builtins.open")
    @patch("os.path.exists")
    def test_runtime_check_fails_without_node_version_file(self, mock_exists, mock_open, mock_run):
        # No hardcoded fallback (#1172): a missing .node-version must fail.
        mock_exists.return_value = False
        mock_open.side_effect = FileNotFoundError
        with self.assertRaises(CLIError):
            self.orchestrator.runtime_check()
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
