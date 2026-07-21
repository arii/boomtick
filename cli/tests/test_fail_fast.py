# pylint: disable=missing-docstring,unused-variable
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.services.dependency_graph import DependencyGraph
from dev_tools.utils import CLIError


def test_dependency_graph_fail_fast(tmp_path):
    # Mock subprocess.run to simulate failure
    with patch("subprocess.run") as mock_run, patch(
        "os.path.exists", side_effect=lambda x: "artifacts" not in x
    ):
        # First call for pnpm --version
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="Error message"),
        ]

        with pytest.raises(CLIError) as excinfo:
            dg = DependencyGraph(root_dir=str(tmp_path))
        assert "dependency-cruiser failed" in str(excinfo.value)


def test_dependency_graph_malformed_json(tmp_path):
    with patch("subprocess.run") as mock_run, patch(
        "os.path.exists", side_effect=lambda x: "artifacts" not in x
    ):
        # First call for pnpm --version, second for depcruise
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="invalid json"),
        ]

        with pytest.raises(CLIError) as excinfo:
            dg = DependencyGraph(root_dir=str(tmp_path))
        assert "Failed to parse dependency-cruiser output" in str(excinfo.value)


if __name__ == "__main__":
    pytest.main([__file__])
