# pylint: disable=missing-docstring,protected-access,unused-import
import sys
import os
import importlib.util
import pytest

# Add repository root to sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Dynamically import the hyphenated script file 'verify-scope.py'
script_path = os.path.join(repo_root, "scripts", "verify-scope.py")
spec = importlib.util.spec_from_file_location("verify_scope", script_path)
assert spec is not None
verify_scope = importlib.util.module_from_spec(spec)
sys.modules["verify_scope"] = verify_scope
assert spec.loader is not None
spec.loader.exec_module(verify_scope)


def test_exact_file_match():
    issue_text = "Fix a bug in .github/workflows/release.yml related to Docker buildx."
    changed_files = [".github/workflows/release.yml"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 1
    assert allowed[0][0] == ".github/workflows/release.yml"
    assert len(disallowed) == 0


def test_out_of_scope_file_blocked():
    issue_text = "Fix a bug in .github/workflows/release.yml related to Docker buildx."
    # publish-runner.yml is NOT mentioned and is unrelated
    changed_files = [".github/workflows/release.yml", ".github/workflows/publish-runner.yml"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is False
    assert len(allowed) == 1
    assert len(disallowed) == 1
    assert disallowed[0] == ".github/workflows/publish-runner.yml"


def test_exempt_configuration_files():
    issue_text = "Fix a bug in .github/workflows/release.yml."
    changed_files = ["package.json", "project_config.json", "ci.yml", "README.md"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 4
    assert len(disallowed) == 0


def test_test_file_mapping():
    issue_text = "Introduce a lightweight Python script in scripts/verify-scope.py."
    # The source file is mentioned, so any test file corresponding to 'verify-scope' should be allowed
    changed_files = ["scripts/verify-scope.py", "cli/tests/test_verify_scope.py"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 2
    assert len(disallowed) == 0


def test_directory_match():
    issue_text = "Optimize files and configurations under scripts/ and help with validation."
    changed_files = ["scripts/run-python-tool.py", "scripts/validate_workspace.py"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 2
    assert len(disallowed) == 0


def test_override_env(monkeypatch):
    monkeypatch.setenv("SCOPE_OVERRIDE", "true")
    assert verify_scope.check_override() is True


def test_override_commit_msg(monkeypatch):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)

    # Mock subprocess.run to return a commit message containing [skip-scope-check]
    class MockCompletedProcess:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = "feat: implement scope verification [skip-scope-check]"
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess()
    )

    assert verify_scope.check_override() is True
