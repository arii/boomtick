"""Tests for workflow installer."""

import tempfile
from pathlib import Path
from dev_tools.handlers.workflow_installer import install_workflows

def test_workflow_installer_dry_run():
    """Test that dry-run mode does not create files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        success = install_workflows(target_dir=temp_dir, dry_run=True, force=False)
        assert success is True

        github_dir = Path(temp_dir) / ".github"
        assert not github_dir.exists()

def test_workflow_installer_execute():
    """Test that execute mode correctly installs the templates."""
    with tempfile.TemporaryDirectory() as temp_dir:
        success = install_workflows(target_dir=temp_dir, dry_run=False, force=False)
        assert success is True

        impact_analysis = Path(temp_dir) / ".github" / "workflows" / "impact-analysis.yml"
        agent_audit = Path(temp_dir) / ".github" / "workflows" / "agent-audit.yml"

        assert impact_analysis.exists()
        assert agent_audit.exists()

        content = impact_analysis.read_text(encoding="utf-8")
        assert "uses: actions/checkout@v4" in content
        assert "uses: actions/setup-node@v4" in content

def test_workflow_installer_force_false():
    """Test that existing files are skipped when force is False."""
    with tempfile.TemporaryDirectory() as temp_dir:
        success = install_workflows(target_dir=temp_dir, dry_run=False, force=False)
        assert success is True

        impact_analysis = Path(temp_dir) / ".github" / "workflows" / "impact-analysis.yml"
        impact_analysis.write_text("modified", encoding="utf-8")

        success2 = install_workflows(target_dir=temp_dir, dry_run=False, force=False)
        assert success2 is True

        assert impact_analysis.read_text(encoding="utf-8") == "modified"

def test_workflow_installer_force_true():
    """Test that existing files are overwritten when force is True."""
    with tempfile.TemporaryDirectory() as temp_dir:
        success = install_workflows(target_dir=temp_dir, dry_run=False, force=False)
        assert success is True

        impact_analysis = Path(temp_dir) / ".github" / "workflows" / "impact-analysis.yml"
        impact_analysis.write_text("modified", encoding="utf-8")

        success2 = install_workflows(target_dir=temp_dir, dry_run=False, force=True)
        assert success2 is True

        assert impact_analysis.read_text(encoding="utf-8") != "modified"
        assert "uses: actions/checkout@v4" in impact_analysis.read_text(encoding="utf-8")
