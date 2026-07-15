# pylint: disable=missing-docstring,unused-variable
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.services.dependency_graph import DependencyGraph
from dev_tools.utils import CLIError


def test_dependency_graph_fail_fast(tmp_path):
    # Mock subprocess.run to simulate failure
    with patch("subprocess.run") as mock_run:
        # Create required config files
        (tmp_path / ".dependency-cruiser.config.mjs").touch()
        (tmp_path / "tsconfig.app.json").touch()

        # Simulate depcruise failure
        mock_run.return_value = MagicMock(returncode=1, stderr="Error message")

        with pytest.raises(CLIError) as excinfo:
            dg = DependencyGraph(root_dir=str(tmp_path))
        assert "dependency-cruiser failed" in str(excinfo.value)


def test_dependency_graph_malformed_json(tmp_path):
    with patch("subprocess.run") as mock_run:
        # Create required config files
        (tmp_path / ".dependency-cruiser.config.mjs").touch()
        (tmp_path / "tsconfig.app.json").touch()

        # Simulate depcruise success but malformed output
        mock_run.return_value = MagicMock(returncode=0, stdout="invalid json")

        with pytest.raises(CLIError) as excinfo:
            dg = DependencyGraph(root_dir=str(tmp_path))
        assert "Failed to parse dependency-cruiser output" in str(excinfo.value)


if __name__ == "__main__":
    pytest.main([__file__])
