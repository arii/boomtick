# pylint: disable=missing-docstring
"""Qualified Allowed/Forbidden Files headings in raw scope specs (#1300)."""

import json
import subprocess

import pytest
from click.testing import CliRunner
from dev_tools.cli import cli
from dev_tools.commands.gates_spec import _spec_backtick_paths, _spec_section_lines

ALLOWED = ("allowed files", "allowed")
FORBIDDEN = ("forbidden files", "forbidden")


def _spec(allowed_heading, forbidden_heading):
    return (
        "# Raw spec\n\n"
        f"## {allowed_heading}\n- `src/widget.py`\n- `src/shared.py`\n\n"
        f"## {forbidden_heading}\n- `src/admin.py`\n- `src/shared.py`\n"
        "- Do not rewrite `src/legacy.py` wholesale\n\n"
        "## Notes\n- `src/notes.py`\n"
    )


QUALIFIED = [
    ("Allowed Files", "Forbidden Files"),
    (
        "Allowed Files (Create / Modify / Delete)",
        "Forbidden Files (Do Not Touch)",
    ),
    ("Allowed Files: Create / Modify / Delete", "Forbidden Files: Do Not Touch"),
    ("Allowed Files - Create / Modify", "Forbidden Files \u2014 Do Not Touch"),
    ("**Allowed Files** (Create / Modify)", "**Forbidden Files**"),
]


@pytest.mark.parametrize(("allowed", "forbidden"), QUALIFIED)
def test_qualified_headings_recognized(allowed, forbidden):
    body = _spec(allowed, forbidden)
    assert _spec_backtick_paths(body, *ALLOWED) == ["src/widget.py", "src/shared.py"]
    assert _spec_backtick_paths(body, *FORBIDDEN) == [
        "src/admin.py",
        "src/shared.py",
        "src/legacy.py",
    ]


def test_section_stops_at_next_heading():
    lines = _spec_section_lines(_spec(*QUALIFIED[2]), *ALLOWED)
    assert not any("notes.py" in line for line in lines)


def test_unrelated_heading_not_matched():
    body = "## Allowed Files Of The Past\n- `a/b.py`\n"
    assert _spec_backtick_paths(body, *ALLOWED) == []


def _git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def _worktree(tmp_path):
    root = tmp_path / "wt"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "src").mkdir()
    for name in ("widget", "admin", "shared", "legacy"):
        (root / "src" / f"{name}.py").write_text("ok\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "remote", "add", "origin", str(root))
    _git(root, "fetch", "-q", "origin")
    return root


@pytest.mark.parametrize(("allowed", "forbidden"), QUALIFIED)
def test_verify_scope_with_qualified_headings(tmp_path, allowed, forbidden):
    root = _worktree(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(_spec(allowed, forbidden))
    for name in ("widget", "shared", "admin"):
        with open(root / "src" / f"{name}.py", "a", encoding="utf-8") as handle:
            handle.write("change\n")
    result = CliRunner().invoke(
        cli,
        [
            "verify-scope",
            "--spec-file",
            str(spec),
            "--worktree",
            str(root),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    # admin.py is genuinely forbidden; shared.py is both allowed and
    # forbidden, so allowed wins; widget.py is allowed.
    assert data["violations"] == ["src/admin.py"]
