# pylint: disable=missing-docstring,protected-access,unused-import
import sys
import os
import json
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
    changed_files = ["package.json", "project_config.json", "ci.yml", "README.md", "cli/pyproject.toml"]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 5
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


def test_module_hierarchy_subfile():
    issue_text = "Refactor monolithic configuration logic in mcp/src/config.ts into modular files."
    changed_files = [
        "mcp/src/config.ts",
        "mcp/src/config/dynamic.ts",
        "mcp/src/config/github.ts",
        "mcp/src/config/repo.ts"
    ]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 4
    assert len(disallowed) == 0


def test_refactor_import_heuristic():
    issue_text = "Extract helper functions from mcp/src/tools/jules/cancel-session.ts into shared CLI helper."
    # mcp/src/tools/jules/cancel-session.ts imports mcp/src/tools/jules/cli.ts
    changed_files = [
        "mcp/src/tools/jules/cancel-session.ts",
        "mcp/src/tools/jules/cli.ts"
    ]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 2
    assert len(disallowed) == 0


def test_linked_issue_fetching(monkeypatch):
    issue_text = "Clean up MCP server complexity. Fixes #936."

    class MockCompletedProcess:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = json.dumps({
            "title": "[cleanup] MCP Server & Tools",
            "body": "Refactor targets in mcp/src/tools/jules/shared.ts, mcp/src/config.ts."
        })
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess()
    )

    full_text = verify_scope.fetch_linked_issue_bodies(issue_text)
    assert "mcp/src/config.ts" in full_text

    changed_files = ["mcp/src/config.ts", "mcp/src/config/dynamic.ts"]
    success, allowed, disallowed = verify_scope.check_scope(changed_files, full_text)

    assert success is True
    assert len(allowed) == 2
    assert len(disallowed) == 0


def test_pr_949_scenario(monkeypatch):
    pr_body = """Cleaned up dead code, complexity, and duplication in the MCP server package:
1. Removed unused startHttp method in BoomtickMCPServer.
2. Broken down complex files (shared.ts, config.ts) into smaller modular sub-files.
3. Extracted duplicate td execution and error parsing boilerplate in 7 tool handlers into shared runTDCli helper.

Fixes #936"""

    body_text = (
        "## Dead Code\n- Remove unused class member `startHttp` in `mcp/src/mcp/server.ts`.\n\n"
        "## Complexity\n- Refactor targets in `mcp/src/tools/jules/shared.ts` (64 LOC, 6 dependents), "
        "`mcp/src/config.ts` (144 LOC, 9 dependents).\n\n"
        "## Duplication\n- DRY up clone groups in the following files: "
        "`mcp/src/tools/github.comment_triage_summary.ts`, `mcp/src/tools/github.get_pr_diff.ts`, "
        "`mcp/src/tools/jules/cancel-session.ts`, `mcp/src/tools/jules/get-messages.ts`, "
        "`mcp/src/tools/jules/list-sessions.ts`, `mcp/src/tools/jules/send-message.ts`, "
        "`mcp/src/tools/jules/trigger-feedback.ts`."
    )

    class MockCompletedProcess:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = json.dumps({
            "title": "[cleanup] MCP Server & Tools",
            "body": body_text
        })
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess()
    )

    full_text = verify_scope.fetch_linked_issue_bodies(pr_body)

    changed_files = [
        "mcp/src/config.ts",
        "mcp/src/config/dynamic.ts",
        "mcp/src/config/github.ts",
        "mcp/src/config/repo.ts",
        "mcp/src/http.ts",
        "mcp/src/mcp/http.test.ts",
        "mcp/src/mcp/server.ts",
        "mcp/src/tools/github.comment_triage_summary.ts",
        "mcp/src/tools/github.get_pr_diff.ts",
        "mcp/src/tools/jules/cancel-session.ts",
        "mcp/src/tools/jules/cli.ts",
        "mcp/src/tools/jules/get-messages.ts",
        "mcp/src/tools/jules/list-sessions.ts",
        "mcp/src/tools/jules/send-message.ts",
        "mcp/src/tools/jules/session.ts",
        "mcp/src/tools/jules/shared.ts",
        "mcp/src/tools/jules/trigger-feedback.ts",
    ]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, full_text)

    assert success is True
    assert len(allowed) == len(changed_files)
    assert len(disallowed) == 0


def test_unrelated_file_blocked_under_strict():
    issue_text = "Refactor monolithic configuration logic in mcp/src/config.ts into modular files."
    changed_files = [
        "mcp/src/config.ts",
        "mcp/src/config/dynamic.ts",
        "cli/dev_tools/schema_gen.py"  # Completely unrelated package/directory
    ]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is False
    assert len(allowed) == 2
    assert len(disallowed) == 1
    assert disallowed[0] == "cli/dev_tools/schema_gen.py"


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


def test_override_release_please_head_ref(monkeypatch):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)
    monkeypatch.setenv("GITHUB_HEAD_REF", "release-please--branches--main")
    assert verify_scope.check_override() is True


def test_override_release_please_github_ref(monkeypatch):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/release-please--branches--main")
    assert verify_scope.check_override() is True


def test_override_release_please_event_path(monkeypatch, tmp_path):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)

    event_file = tmp_path / "event.json"
    event_data = {
        "pull_request": {
            "title": "chore: release main (#942)",
            "head": {"ref": "release-please--branches--main"},
            "user": {"login": "release-please[bot]"}
        }
    }
    event_file.write_text(json.dumps(event_data), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))

    assert verify_scope.check_override() is True


def test_override_boomtick_bot_user(monkeypatch, tmp_path):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)

    event_file = tmp_path / "event.json"
    event_data = {
        "pull_request": {
            "title": "chore: release main (#972)",
            "head": {"ref": "release-please--branches--main"},
            "user": {"login": "boomtick[bot]"}
        }
    }
    event_file.write_text(json.dumps(event_data), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))

    assert verify_scope.check_override() is True


def test_dockerfile_case_insensitive_exempt():
    issue_text = "Fix a bug in .github/workflows/release.yml."
    changed_files = [
        "Dockerfile",
        "package-lock.json",
        "action.yml",
        ".dependency-cruiser.config.mjs",
        "tsup.config.ts"
    ]

    success, allowed, disallowed = verify_scope.check_scope(changed_files, issue_text)

    assert success is True
    assert len(allowed) == 5
    assert len(disallowed) == 0


def test_override_release_please_commit_msg(monkeypatch):
    monkeypatch.delenv("SCOPE_OVERRIDE", raising=False)
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    class MockCompletedProcess:  # pylint: disable=too-few-public-methods
        returncode = 0
        stdout = "chore: release main (#942)"
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess()
    )

    assert verify_scope.check_override() is True
