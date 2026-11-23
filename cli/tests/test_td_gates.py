# pylint: disable=missing-docstring,line-too-long
"""Tests for td validate-issue / verify-scope / audit-code gates (no network)."""

import json
import subprocess

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.commands.gates_spec import _spec_backtick_paths

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


def test_1359_allowed_file_body_constraints_do_not_forbid_whole_file(tmp_path):
    root = _worktree(tmp_path)
    source = root / "deep-agent" / "deep_chat.py"
    source.parent.mkdir()
    source.write_text("before\n")
    _git(root, "add", "deep-agent/deep_chat.py")
    _git(root, "commit", "-qm", "baseline")
    source.write_text("after\n")
    body = VALID_SPEC.replace("src/widget.py", "deep-agent/deep_chat.py").replace(
        "- `src/admin.py`",
        "- `src/admin.py`\n"
        "- The bodies of `trim_history_by_count` and `trim_thread_history` "
        "inside `deep-agent/deep_chat.py` must remain unchanged.",
    )
    path = tmp_path / "issue-1359.md"
    path.write_text(body)
    forbidden = _spec_backtick_paths(body, "forbidden files", "forbidden")
    assert "deep-agent/deep_chat.py" in forbidden
    assert "src/admin.py" in forbidden
    result = CliRunner().invoke(
        cli, ["verify-scope", "--spec-file", str(path), "--worktree", str(root)]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["passed"]


def test_forbidden_paths_without_explicit_allowlist_still_apply():
    body = "### Forbidden Files\n- `deep-agent/deep_chat.py`\n"
    assert _spec_backtick_paths(body, "forbidden files") == ["deep-agent/deep_chat.py"]
    assert _spec_backtick_paths("", "forbidden files") == []


@pytest.mark.parametrize(
    "heading",
    [
        "Allowed Files",
        "Allowed Files (Create / Modify / Delete)",
        "Allowed Files (Create/Modify/Delete)",
    ],
)
def test_explicit_allowed_path_wins_over_exception_basename(tmp_path, heading):
    root = _worktree(tmp_path)
    for directory in ("deep-agent", "other"):
        source = root / directory / "deep_chat.py"
        source.parent.mkdir()
        source.write_text("before\n")
    _git(root, "add", "deep-agent/deep_chat.py", "other/deep_chat.py")
    _git(root, "commit", "-qm", "baseline")
    _git(root, "fetch", "-q", "origin")
    source = root / "deep-agent" / "deep_chat.py"
    source.write_text("after\n")
    body = VALID_SPEC.replace("src/widget.py", "./DEEP-AGENT/deep_chat.py").replace(
        "- `src/admin.py`", "- `deep-agent/` modules other than `deep_chat.py`"
    )
    body = body.replace("### Allowed Files", "### " + heading)
    path = tmp_path / "issue-1359.md"
    path.write_text(body)
    args = ["verify-scope", "--spec-file", str(path), "--worktree", str(root)]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["violations"] == []

    (root / "other" / "deep_chat.py").write_text("after\n")
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["violations"] == ["other/deep_chat.py"]


@pytest.mark.parametrize("allowed", ["deep_chat.py", "deep-agent/deep_chat.py"])
def test_allowed_path_does_not_remove_forbidden_suffix_for_other_paths(
    tmp_path, allowed
):
    root = _worktree(tmp_path)
    other = "other/" + allowed
    for name in (allowed, other):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("before\n")
    _git(root, "add", allowed, other)
    _git(root, "commit", "-qm", "baseline")
    _git(root, "fetch", "-q", "origin")
    spec = tmp_path / "spec.md"
    spec.write_text(
        VALID_SPEC.replace("src/widget.py", allowed).replace("src/admin.py", allowed)
    )
    (root / allowed).write_text("after\n")
    args = ["verify-scope", "--spec-file", str(spec), "--worktree", str(root)]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    (root / other).write_text("after\n")
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["violations"] == [other]


def test_forbidden_extraction_preserves_paths_for_per_file_precedence():
    body = (
        "### Allowed Files\n- `./deep-agent/deep_chat.py`\n"
        "### Forbidden Files\n- `DEEP-AGENT/deep_chat.py`\n- `other.py`\n"
    )
    assert _spec_backtick_paths(body, "forbidden files") == [
        "DEEP-AGENT/deep_chat.py",
        "other.py",
    ]


def _git(worktree, *args):
    subprocess.run(
        ["git", "-C", str(worktree), *args], check=True, capture_output=True, text=True
    )


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
    # The verification command names tests/test_widget.py, which must
    # exist (or be CREATE-marked) since #1182 removed the
    # command-mention existence bypass.
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(VALID_SPEC)
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
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
    result = CliRunner().invoke(
        cli,
        ["validate-issue", "--file", str(spec), "--repo-root", str(tmp_path), "--json"],
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["valid"] is False
    assert any("Problem Statement" in e for e in data["errors"])
    assert any("TODO" in e for e in data["errors"])


def test_validate_issue_mixed_case_and_dirs(tmp_path):
    root = tmp_path / "co"
    (root / "src").mkdir(parents=True)
    (root / "src" / "Widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Mixed case\n\n## Problem Statement\n\nFix it.\n\n"
        "## Goal\n\nDone.\n\n## Scope\n\nTouched: `src/Widget.py`.\n\n"
        "## Definition of Done\n\nWorks.\n\n"
        "## Acceptance Criteria\n- [ ] Widget fixed\n\n"
        "## Verification Commands\n```bash\n"
        "test -f src/Widget.py\n"
        "```\n"
    )
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"] is True


def test_verify_scope_pass_and_violation(tmp_path):
    root = _worktree(tmp_path)
    with open(root / "src" / "widget.py", "a", encoding="utf-8") as handle:
        handle.write("change\n")
    result = CliRunner().invoke(
        cli,
        [
            "verify-scope",
            "--spec-file",
            _spec_file(tmp_path),
            "--worktree",
            str(root),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["violations"] == []

    with open(root / "src" / "admin.py", "a", encoding="utf-8") as handle:
        handle.write("bad\n")
    result = CliRunner().invoke(
        cli,
        [
            "verify-scope",
            "--spec-file",
            _spec_file(tmp_path),
            "--worktree",
            str(root),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["violations"] == ["src/admin.py"]


def test_verify_scope_auto_revert(tmp_path):
    root = _worktree(tmp_path)
    with open(root / "src" / "admin.py", "a", encoding="utf-8") as handle:
        handle.write("bad\n")
    result = CliRunner().invoke(
        cli,
        [
            "verify-scope",
            "--spec-file",
            _spec_file(tmp_path),
            "--worktree",
            str(root),
            "--auto-revert",
            "--json",
        ],
    )
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
    (root / "src" / "widget.tsx").write_text("export function Widget() { return 1; }\n")
    (root / "src" / "app.tsx").write_text(
        'import { Widget } from "./widget";\n'
        "export function App() { return Widget(); }\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "widget.test.tsx").write_text(
        'import { Widget } from "../src/widget";\n'
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "remote", "add", "origin", str(root))
    _git(root, "fetch", "-q", "origin")
    return root


def test_audit_impact_clean_reports_blast_radius(tmp_path):
    root = _impact_repo(tmp_path)
    with open(root / "src" / "widget.tsx", "a", encoding="utf-8") as handle:
        handle.write("export const v = 2;\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit-impact", "--worktree", str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["violations"] == []
    assert "src/widget.tsx" in data["impacted_files"]
    assert "src/app.tsx" in data["impacted_files"]
    assert "tests/widget.test.tsx" in data["dependent_tests"]


def test_audit_impact_skips_heavy_dirs(tmp_path):
    """Dependents walk must not descend into venvs/build output.

    Regression: _impact_dependents walked .venv/, dist/, .tmp*/
    (69k+ files on large repos). Heavy dirs are pruned, so a file
    that imports the changed module from inside .venv/ or dist/ is
    invisible to the blast radius — and the walk stays fast.
    """
    from dev_tools.cli import _prune_walk_dirs

    assert _prune_walk_dirs(
        [
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            "__pycache__",
            ".tmp-cache",
            "pkg.egg-info",
            "src",
        ]
    ) == ["src"]
    root = _impact_repo(tmp_path)
    venv_mod = root / ".venv" / "lib" / "heavy.py"
    venv_mod.parent.mkdir(parents=True)
    venv_mod.write_text("from widget import Widget\n", encoding="utf-8")
    dist_mod = root / "dist" / "bundle.py"
    dist_mod.parent.mkdir()
    dist_mod.write_text("from widget import Widget\n", encoding="utf-8")
    with open(root / "src" / "widget.tsx", "a", encoding="utf-8") as handle:
        handle.write("export const v = 2;\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit-impact", "--worktree", str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert ".venv/lib/heavy.py" not in data["impacted_files"]
    assert "dist/bundle.py" not in data["impacted_files"]
    assert "src/app.tsx" in data["impacted_files"]


def test_audit_impact_violation_fails(tmp_path):
    root = _impact_repo(tmp_path)
    with open(root / "src" / "widget.tsx", "a", encoding="utf-8") as handle:
        handle.write("// @ts-ignore\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["audit-impact", "--worktree", str(root), "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["violations"]
    assert data["violations"][0]["file"] == "src/widget.tsx"


def test_validate_issue_nested_allowed_path(tmp_path):
    # #1168: a nested allowed file validates on its own existence —
    # the parent-dir prefix the dir regex also matches must not fail
    # the spec when the directory exists.
    root = tmp_path / "co"
    comp = root / "frontend" / "src" / "components"
    comp.mkdir(parents=True)
    (comp / "RepoPicker.tsx").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Nested scope\n\n## Problem Statement\n\nFix it.\n\n"
        "## Goal\n\nDone.\n\n## Scope\n\nTouched: "
        "`frontend/src/components/RepoPicker.tsx`.\n\n"
        "## Definition of Done\n\nWorks.\n\n"
        "## Scope & File Boundaries\n### Allowed Files\n"
        "- `frontend/src/components/RepoPicker.tsx`\n\n"
        "## Acceptance Criteria\n- [ ] Picker fixed\n\n"
        "## Verification Commands\n```bash\n"
        "pnpm vitest run picker\n"
        "```\n"
    )
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["valid"] is True, data["errors"]
    assert data["errors"] == []


def test_validate_issue_missing_file_errors(tmp_path):
    # #1168 follow-through: with the dead tail restored, a genuinely
    # missing file (no CREATE marker) fails with the named error.
    root = tmp_path / "co"
    (root / "src").mkdir(parents=True)
    (root / "src" / "widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Missing file\n\n## Problem Statement\n\nFix it.\n\n"
        "## Goal\n\nDone.\n\n## Scope\n\nTouched: `src/widget.py`, "
        "`src/gone.py`.\n\n"
        "## Definition of Done\n\nWorks.\n\n"
        "## Scope & File Boundaries\n### Allowed Files\n"
        "- `src/widget.py`\n- `src/gone.py`\n\n"
        "## Acceptance Criteria\n- [ ] Widget fixed\n\n"
        "## Verification Commands\n```bash\n"
        "pytest tests/test_widget.py\n"
        "```\n"
    )
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["valid"] is False
    assert any(
        "allowed path not in checkout: src/gone.py" in e for e in data["errors"]
    ), data["errors"]


def test_validate_issue_command_mention_still_requires_existence(tmp_path):
    # #1182: an Allowed Scope path named in a verification command
    # (e.g. pytest tests/test_new_module.py) must still fail the
    # checkout-existence check unless marked (CREATE).
    root = tmp_path / "co"
    (root / "src").mkdir(parents=True)
    (root / "src" / "widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Command-mentioned file\n\n## Problem Statement\n\nFix it.\n\n"
        "## Goal\n\nDone.\n\n## Scope\n\nTouched: `src/widget.py`, "
        "`tests/test_new_module.py`.\n\n"
        "## Definition of Done\n\nWorks.\n\n"
        "## Scope & File Boundaries\n### Allowed Files\n"
        "- `src/widget.py`\n- `tests/test_new_module.py`\n\n"
        "## Acceptance Criteria\n- [ ] Widget fixed\n\n"
        "## Verification Commands\n```bash\n"
        "pytest tests/test_new_module.py\n"
        "```\n"
    )
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["valid"] is False
    assert any(
        "allowed path not in checkout: tests/test_new_module.py" in e
        for e in data["errors"]
    ), data["errors"]


def test_validate_issue_mixed_case_create_marker(tmp_path):
    # The CREATE escape must compare case-insensitively: a new
    # mixed-case file marked (CREATE) on its own line validates.
    root = tmp_path / "co"
    (root / "src").mkdir(parents=True)
    # Command-mentioned tests/test_new_widget.py exists; only the
    # CREATE-marked src/NewWidget.py is new.
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_new_widget.py").write_text("ok\n")
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# New file\n\n## Problem Statement\n\nAdd it.\n\n"
        "## Goal\n\nDone.\n\n## Scope\n\nTouched: `src/NewWidget.py` "
        "(CREATE).\n\n"
        "## Definition of Done\n\nWorks.\n\n"
        "## Scope & File Boundaries\n### Allowed Files\n"
        "- `src/NewWidget.py` (CREATE)\n\n"
        "## Acceptance Criteria\n- [ ] Widget added\n\n"
        "## Verification Commands\n```bash\n"
        "pytest tests/test_new_widget.py\n"
        "```\n"
    )
    result = CliRunner().invoke(
        cli, ["validate-issue", "--file", str(spec), "--repo-root", str(root), "--json"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["valid"] is True


def test_audit_code_skips_slang_without_config(tmp_path):
    """Slop audit must not run under another repo's config.

    A worktree without .agents/audit.config.yaml produces no
    slop_findings (previously it fell back to the td package script
    and failed on the missing config).
    """
    root = _worktree(tmp_path)
    with open(root / "src" / "widget.py", "a", encoding="utf-8") as handle:
        handle.write("change\n")
    result = CliRunner().invoke(cli, ["audit-code", "--worktree", str(root), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["slop_findings"] == []
    assert set(data) == {
        "status",
        "passed",
        "slop_findings",
        "suppressions_added",
        "ast_violations",
    }


def test_scope_path_extraction_ignores_explanatory_identifiers():
    body = (
        "### Forbidden Files (Do Not Modify)\n"
        "- Keep `trim_history_by_count` and `trim_thread_history` unchanged "
        "inside `deep-agent/deep_chat.py`.\n"
        "- `deep-agent/` modules other than `deep_chat.py`\n"
        "- `LICENSE` and `.env`\n"
        "- `settings`\n"
    )
    assert _spec_backtick_paths(body, "forbidden files") == [
        "deep-agent/deep_chat.py",
        "deep-agent/",
        "deep_chat.py",
        "LICENSE",
        ".env",
        "settings",
    ]


def _verify_issue_scope(tmp_path, changed, issue_args):
    root = _worktree(tmp_path)
    for rel in changed:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("new\n")
        _git(root, "add", "-f", rel)
    path = tmp_path / "spec.md"
    path.write_text(VALID_SPEC)
    return CliRunner().invoke(
        cli,
        ["verify-scope", "--spec-file", str(path), "--worktree", str(root)]
        + issue_args,
    )


def test_verify_scope_issue_allows_current_issue_spec(tmp_path):
    result = _verify_issue_scope(
        tmp_path, ["docs/specs/issue-1551.md"], ["--issue", "1551"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["passed"]


@pytest.mark.parametrize(
    "changed,issue_args",
    [
        (["docs/specs/issue-1551.md"], []),
        (["docs/specs/issue-1552.md"], ["--issue", "1551"]),
        (["docs/specs/issue-1551.md", "tools/other.py"], ["--issue", "1551"]),
        (["docs/specs/issue-1551/extra.md"], ["--issue", "1551"]),
        (["docs/specs/ISSUE-1551.md"], ["--issue", "1551"]),
        (["docs/specs/issue-1551.md"], ["--issue", "1551x"]),
        (["docs/specs/issue-1551.md"], ["--issue", "0"]),
        (["docs/specs/issue-1551.md"], ["--issue", "-1"]),
        (["docs/specs/issue-1551.md"], ["--issue", ""]),
    ],
)
def test_verify_scope_issue_still_rejects_others(tmp_path, changed, issue_args):
    result = _verify_issue_scope(tmp_path, changed, issue_args)
    assert result.exit_code != 0, result.output


@pytest.mark.parametrize(
    "path",
    [
        "docs/specs/../specs/issue-1551.md",
        "./docs/specs/issue-1551.md",
        "/docs/specs/issue-1551.md",
        "x/docs/specs/issue-1551.md",
    ],
)
def test_check_scope_issue_rejects_non_canonical_spec_paths(path):
    from dev_tools.services import scope_gate

    passed, _allowed, disallowed = scope_gate.check_scope(
        [path], VALID_SPEC, issue=1551
    )
    assert not passed
    assert disallowed == [path]
