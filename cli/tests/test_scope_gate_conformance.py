# pylint: disable=missing-docstring,line-too-long,protected-access
"""Conformance: scope_gate.py and scripts/verify-scope.py agree.

scripts/verify-scope.py re-exports scope_gate's matching core, so
both entry points run over shared fixtures and must agree on
(success, allowed set, disallowed set). This test keeps the single
source of truth honest, including the script's re-export wiring.
"""
import importlib.util
import os

import pytest

from dev_tools.services import scope_gate

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "verify-scope.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_scope_ref", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REF = _load_script()

ISSUE = """
# Fix login redirect

Touches mcp/src/tools/agent.submit_pr.ts and the session docs.
Also updates cli/dev_tools/services/worktrees.py helpers.
"""

CASES = [
    # (changed files, expect success)
    (["mcp/src/tools/agent.submit_pr.ts"], True),
    (["mcp/src/tools/agent.submit_pr.test.ts"], True),  # test for in-scope
    (["cli/dev_tools/services/worktrees.py"], True),
    (["README.md"], True),  # exempt
    (["mcp/src/unrelated/thing.ts"], False),
    (["mcp/src/tools/agent.submit_pr.ts", "mcp/src/unrelated/x.ts"], False),
    (["cli/dev_tools/services/"], True),  # dir-ish entries tolerated
]


def _verdict(fn, files, text):
    ok, allowed, disallowed = fn(files, text)
    return ok, sorted(f for f, _ in allowed), sorted(disallowed)


@pytest.mark.parametrize("files,expected", CASES)
def test_matches_reference(files, expected):
    mine = _verdict(scope_gate.check_scope, files, ISSUE)
    ref = _verdict(REF.check_scope, files, ISSUE)
    assert mine == ref
    assert mine[0] is expected


def test_empty_issue_passes_both():
    assert _verdict(scope_gate.check_scope, ["a/b.ts"], "") == \
        _verdict(REF.check_scope, ["a/b.ts"], "")
    assert scope_gate.check_scope(["a/b.ts"], "")[0] is True


def test_import_heuristic_matches_reference(tmp_path, monkeypatch):
    # Allowed file imports a new helper in the same tree -> pass 2 allow.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("from pkg.helper import run\n")
    (pkg / "helper.py").write_text("def run(): pass\n")
    issue = "Change pkg/core.py behaviour."
    files = ["pkg/core.py", "pkg/helper.py"]
    monkeypatch.chdir(tmp_path)
    mine = _verdict(scope_gate.check_scope, files, issue)
    ref = _verdict(REF.check_scope, files, issue)
    assert mine == ref
    assert mine[0] is True


def test_root_anchors_import_reads(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "core.py").write_text("from pkg.helper import run\n")
    (pkg / "helper.py").write_text("def run(): pass\n")
    issue = "Change pkg/core.py behaviour."
    files = ["pkg/core.py", "pkg/helper.py"]
    ok, _allowed, disallowed = scope_gate.check_scope(
        files, issue, root=str(tmp_path))
    assert ok is True
    assert disallowed == []


def test_script_reexports_single_implementation():
    # #1178: one implementation of the matching rules — the script
    # must re-export scope_gate's core, not carry its own copy.
    assert REF.check_scope is scope_gate.check_scope
    assert REF.extract_mentions is scope_gate.extract_mentions
    assert REF.EXEMPT_FILES is scope_gate.EXEMPT_FILES
    assert REF.STOP_WORDS is scope_gate.STOP_WORDS
    assert REF.KNOWN_FILE_EXTENSIONS is scope_gate.KNOWN_FILE_EXTENSIONS
