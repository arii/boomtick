import os
import pytest
from dev_tools.orchestrator import Orchestrator

def test_check_workflow_compliance_no_violations(tmp_path):
    workflow_file = tmp_path / "compliant.yml"
    workflow_file.write_text("""
name: Compliant
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version-file: '.node-version'
      - run: pnpm install
      - run: pnpm test
""")
    orch = Orchestrator()
    violations = orch._check_workflow_compliance(str(workflow_file))
    assert len(violations) == 0

def test_check_workflow_compliance_with_violations(tmp_path):
    workflow_file = tmp_path / "non_compliant.yml"
    workflow_file.write_text("""
name: Non-compliant
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-node@v3
        with:
          node-version: 16
      - run: npm install
      - run: npm run build
""")
    orch = Orchestrator()
    violations = orch._check_workflow_compliance(str(workflow_file))
    # 1 node-version, 2 npm (install, run), 1 checkout, 1 setup-node = 5
    assert len(violations) == 5
    assert any("node-version:" in v for v in violations)
    assert any("npm" in v for v in violations)
    assert any("checkout@v2" in v for v in violations)
    assert any("setup-node@v3" in v for v in violations)

def test_scan_workflows(tmp_path, monkeypatch):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: CI")
    (workflow_dir / "deploy.yaml").write_text("name: Deploy")
    (workflow_dir / "README.md").write_text("Not a workflow")

    real_exists = os.path.exists
    def mock_exists(path):
        if path == ".github/workflows":
            return True
        return real_exists(path)

    real_listdir = os.listdir
    def mock_listdir(path):
        if path == ".github/workflows":
            return real_listdir(str(workflow_dir))
        return real_listdir(path)

    monkeypatch.setattr(os.path, "exists", mock_exists)
    monkeypatch.setattr(os, "listdir", mock_listdir)

    orch = Orchestrator()
    workflows = orch._scan_workflows()
    assert len(workflows) == 2
    assert any("ci.yml" in f for f in workflows)
    assert any("deploy.yaml" in f for f in workflows)

def test_plan_workflow_audit_invalid_path(tmp_path, monkeypatch):
    from dev_tools.utils import CLIError
    orch = Orchestrator()

    # Extension check
    with pytest.raises(CLIError, match="Invalid workflow file extension"):
        orch.plan_workflow_audit("invalid.txt")

    # Directory check
    with pytest.raises(CLIError, match="Workflow file must reside in .github/workflows/"):
        orch.plan_workflow_audit(".github/ci.yml")

    # Residing in the correct directory but file doesn't exist
    # (assuming we are not mocking existence here yet, or we mock it to False)
    with pytest.raises(CLIError, match="Workflow file must reside in .github/workflows/"):
         # normpath will result in "some/other/ci.yml"
         orch.plan_workflow_audit("some/other/ci.yml")

def test_plan_workflow_audit_valid_path(tmp_path, monkeypatch):
    # Setup mock environment
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow_file = workflow_dir / "test.yml"
    workflow_file.write_text("name: Test")

    # Mock os.path.exists to return True for our specific mock path
    real_exists = os.path.exists
    def mock_exists(path):
        if path == ".github/workflows/test.yml":
            return True
        return real_exists(path)
    monkeypatch.setattr(os.path, "exists", mock_exists)

    orch = Orchestrator()
    # Mocking _check_workflow_compliance to avoid actual file read of non-existent path
    monkeypatch.setattr(orch, "_check_workflow_compliance", lambda x: [])
    # Mocking get_or_create_log_dir
    monkeypatch.setattr("dev_tools.orchestrator.get_or_create_log_dir", lambda x: str(tmp_path))

    res = orch.plan_workflow_audit(".github/workflows/test.yml")
    assert res["status"] == "success"
    assert res["files_count"] == 1
