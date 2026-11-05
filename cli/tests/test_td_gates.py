# pylint: disable=missing-docstring,line-too-long
"""Tests for td validate-issue / verify-scope / audit-code gates (no network)."""
import json
import subprocess

from click.testing import CliRunner

from dev_tools.cli import cli


VALID_SPEC = """# Fix the widget

## Problem Statement
Stale data at `src/widget.py:42`.

## Goal
Fresh data.

## Scope
Touched: `src/widget.py`, `src/new_widget.py` (CREATE).

## Definition of Done
Fresh.

## Scope & File Boundaries
### Allowed Files
- `src/widget.py`
- `src/new_widget.py` (CREATE)
### Forbidden Files
- `src/admin.py`

## Implementation Plan
1. Refresh on mount.

## Acceptance Criteria
- [ ] Widget refreshes on mount

## Verification Commands
```bash
pytest tests/test_widget.py
```
"""

BARE_SPEC = "# vague idea\n\nSome TODO left behind.\n"


def _git(worktree, *args):
    subprocess.run(["git", "-C", str(worktree), *args],
                   check=True, capture_output=True, text=True)


def _worktree(tmp_path):
    root = tmp_path / "wt"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "src").mkdir()
    (root / "src" / "widget.py").write_text("ok\n")
    (root / "src" / "admin.py").write_text("ok\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "remote", "add", "origin", str(root))
    _git(root, "fetch", "-q", "origin")
    return root


def _spec_file(tmp_path):
    path = tmp_path / "spec.md"
    path.write_text(VALID_SPEC)
    return str(path)


def test_validate_issue_valid(tmp_path):
    root = tmp_path / "co"
    (root / "src").mkdir(parents=True)
    (root / "src" / "widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(VALID_SPEC)
    result = CliRunner().invoke(cli, ["validate-issue", "--file", str(spec),
                                      "--repo-root", str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["valid"] is True
    assert data["errors"] == []
    assert "src/widget.py" in data["allowed_files"]
    assert "src/admin.py" in [f.lower() for f in data["forbidden_files"]]
    assert data["forbidden_files"]
    assert data["verification_commands"] == ["pytest tests/test_widget.py"]
    assert data["acceptance_criteria"] == ["Widget refreshes on mount"]


def test_validate_issue_invalid(tmp_path):
    spec = tmp_path / "bad.md"
    spec.write_text(BARE_SPEC)
    result = CliRunner().invoke(cli, ["validate-issue", "--file", str(spec),
                                      "--repo-root", str(tmp_path), "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["valid"] is False
    assert any("Problem Statement" in e for e in data["errors"])
    assert any("TODO" in e for e in data["errors"])


def test_verify_scope_pass_and_violation(tmp_path):
    root = _worktree(tmp_path)
    with open(root / "src" / "widget.py", "a", encoding="utf-8") as handle:
        handle.write("change\n")
    result = CliRunner().invoke(cli, ["verify-scope", "--spec-file",
                                      _spec_file(tmp_path), "--worktree",
                                      str(root), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["violations"] == []

    with open(root / "src" / "admin.py", "a", encoding="utf-8") as handle:
        handle.write("bad\n")
    result = CliRunner().invoke(cli, ["verify-scope", "--spec-file",
                                      _spec_file(tmp_path), "--worktree",
                                      str(root), "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["violations"] == ["src/admin.py"]


def test_verify_scope_auto_revert(tmp_path):
    root = _worktree(tmp_path)
    with open(root / "src" / "admin.py", "a", encoding="utf-8") as handle:
        handle.write("bad\n")
    result = CliRunner().invoke(cli, ["verify-scope", "--spec-file",
                                      _spec_file(tmp_path), "--worktree",
                                      str(root), "--auto-revert", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["violations"] == []
    assert data["reverted"] == ["src/admin.py"]
    assert "bad" not in (root / "src" / "admin.py").read_text()


def _impact_repo(tmp_path):
    root = tmp_path / "impact"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "src").mkdir()
    (root / "src" / "widget.tsx").write_text(
        "export function Widget() { return 1; }\n")
    (root / "src" / "app.tsx").write_text(
        'import { Widget } from "./widget";\n'
        "export function App() { return Widget(); }\n")
    (root / "tests").mkdir()
    (root / "tests" / "widget.test.tsx").write_text(
        'import { Widget } from "../src/widget";\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "remote", "add", "origin", str(root))
    _git(root, "fetch", "-q", "origin")
    return root


def test_audit_impact_clean_reports_blast_radius(tmp_path):
    root = _impact_repo(tmp_path)
    with open(root / "src" / "widget.tsx", "a",
              encoding="utf-8") as handle:
        handle.write("export const v = 2;\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit-impact", "--worktree",
                                 str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["violations"] == []
    assert "src/widget.tsx" in data["impacted_files"]
    assert "src/app.tsx" in data["impacted_files"]
    assert "tests/widget.test.tsx" in data["dependent_tests"]


def test_audit_impact_violation_fails(tmp_path):
    root = _impact_repo(tmp_path)
    with open(root / "src" / "widget.tsx", "a",
              encoding="utf-8") as handle:
        handle.write("// @ts-ignore\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit-impact", "--worktree",
                                 str(root), "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["violations"]
    assert data["violations"][0]["file"] == "src/widget.tsx"


def test_audit_code_skips_slang_without_config(tmp_path):
    """Slop audit must not run under another repo's config.

    A worktree without .agents/audit.config.yaml produces no
    slop_findings (previously it fell back to the td package script
    and failed on the missing config).
    """
    root = _worktree(tmp_path)
    with open(root / "src" / "widget.py", "a", encoding="utf-8") as handle:
        handle.write("change\n")
    result = CliRunner().invoke(cli, ["audit-code", "--worktree",
                                      str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["slop_findings"] == []
    assert set(data) == {"status", "passed", "slop_findings",
                         "suppressions_added", "ast_violations"}
