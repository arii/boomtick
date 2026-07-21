"""Test install workflows."""
import os
import tempfile
from unittest.mock import MagicMock, patch

from dev_tools.orchestrator import Orchestrator

def test_install_workflows_standalone():
    """Test workflow installation in standalone mode."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock repository structure
        source_dir = os.path.join(temp_dir, ".github", "workflows")
        os.makedirs(source_dir, exist_ok=True)

        # Write dummy workflow files
        for name in ["chatops-trigger.yml", "ci-repair.yml", "issue-operations.yml", "agent-orchestrator.yml"]:
            with open(os.path.join(source_dir, name), "w", encoding="utf-8") as f:
                f.write("uses: ./mcp/actions/setup\nuses: ./.github/actions/setup-all\n$GITHUB_WORKSPACE/cli\n")

        with patch("os.getcwd", return_value=temp_dir), \
             patch("subprocess.run") as mock_run:

            # Mock subprocess run to simulate non-submodule (empty result)
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = ""
            mock_run.return_value = mock_res

            orch = Orchestrator()
            res = orch.install_workflows(dry_run=False)

            assert res["status"] == "success"
            assert res["submodule_name"] == ""
            assert len(res["copied_files"]) == 4

            # Verify no rewrite happened for standalone
            for dest_file in res["copied_files"]:
                with open(dest_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    assert "uses: ./mcp/actions/setup" in content
                    assert "uses: ./.github/actions/setup-all" in content
                    assert "$GITHUB_WORKSPACE/cli" in content

def test_install_workflows_submodule():
    """Test workflow installation in submodule layout."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock repository structure
        # Parent root: temp_dir
        # Submodule root: temp_dir/boomtick-pkg
        sub_dir = os.path.join(temp_dir, "boomtick-pkg")
        source_dir = os.path.join(sub_dir, ".github", "workflows")
        os.makedirs(source_dir, exist_ok=True)

        # Write dummy workflow files
        for name in ["chatops-trigger.yml", "ci-repair.yml", "issue-operations.yml", "agent-orchestrator.yml"]:
            with open(os.path.join(source_dir, name), "w", encoding="utf-8") as f:
                f.write("uses: ./mcp/actions/setup\nuses: ./.github/actions/setup-all\n$GITHUB_WORKSPACE/cli\n")

        with patch("os.getcwd", return_value=sub_dir), \
             patch("subprocess.run") as mock_run:

            # Mock subprocess run to simulate submodule (returns parent root temp_dir)
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = temp_dir + "\n"
            mock_run.return_value = mock_res

            orch = Orchestrator()
            res = orch.install_workflows(dry_run=False)

            assert res["status"] == "success"
            assert res["submodule_name"] == "boomtick-pkg"
            assert len(res["copied_files"]) == 4

            # Verify paths were correctly rewritten
            for dest_file in res["copied_files"]:
                assert os.path.dirname(dest_file) == os.path.join(temp_dir, ".github", "workflows")
                with open(dest_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    assert "uses: ./boomtick-pkg/mcp/actions/setup" in content
                    assert "uses: ./boomtick-pkg/.github/actions/setup-all" in content
                    assert "$GITHUB_WORKSPACE/boomtick-pkg/cli" in content
