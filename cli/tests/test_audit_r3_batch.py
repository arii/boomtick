# pylint: disable=missing-docstring,protected-access,too-many-locals
"""Independent regression tests for audit batch #1231-#1236 (PR #1237).

Covers: fail-closed scope gate + tsc/ruff wiring (#1231), worktree
skills link + dirty-state indexing (#1232), remote-server separation
(#1233), single canonical visual_guidelines.json (#1234), and the
#1236 measured cuts with deferred-claim pins.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


def _load_verify_scope():
    script_path = os.path.join(REPO_ROOT, "scripts", "verify-scope.py")
    spec = importlib.util.spec_from_file_location("verify_scope_r3batch", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_scope_r3batch"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _clear_scope_env(monkeypatch):
    for var in (
        "SCOPE_OVERRIDE",
        "GITHUB_HEAD_REF",
        "GITHUB_REF",
        "GITHUB_EVENT_PATH",
        "GITHUB_BASE_REF",
    ):
        monkeypatch.delenv(var, raising=False)


def test_missing_issue_strict_fails_closed_default_warns(monkeypatch, tmp_path, capsys):
    # #1231: missing issue text exits 1 under --strict-scope (was silent 0).
    verify_scope = _load_verify_scope()
    _clear_scope_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["verify-scope.py", "--strict-scope"])
    with pytest.raises(SystemExit) as exc:
        verify_scope.main()
    assert exc.value.code == 1
    assert "Failing closed" in capsys.readouterr().out

    # Default stays warning-only (exit 0): unchanged behavior pin.
    _clear_scope_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["verify-scope.py"])
    with pytest.raises(SystemExit) as exc:
        verify_scope.main()
    assert exc.value.code == 0


def test_typecheck_ts_covers_lib():
    # #1231: root type-check:ts covers lib/ + scripts/ (was mcp-only).
    with open(os.path.join(REPO_ROOT, "tsconfig.ts.json"), encoding="utf-8") as fh:
        tsconfig = json.load(fh)
    assert any(str(e).startswith("lib") for e in tsconfig["include"])
    assert any(str(e).startswith("scripts") for e in tsconfig["include"])

    with open(os.path.join(REPO_ROOT, "package.json"), encoding="utf-8") as fh:
        pkg = json.load(fh)
    assert pkg["scripts"]["type-check:ts"] == "tsc --noEmit -p tsconfig.ts.json"

    with open(
        os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8"
    ) as fh:
        assert "pnpm run type-check:ts" in fh.read()


def test_ruff_format_wired():
    # #1231: ruff format --check in script + CI + hook + dev deps.
    with open(os.path.join(REPO_ROOT, "package.json"), encoding="utf-8") as fh:
        pkg = json.load(fh)
    gate = pkg["scripts"]["lint:format"]
    assert "ruff format --check" in gate
    assert "cli/dev_tools/models/contracts.py" in gate

    with open(
        os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8"
    ) as fh:
        assert "lint:format" in fh.read()

    with open(
        os.path.join(REPO_ROOT, "scripts", "hooks", "pre-push"), encoding="utf-8"
    ) as fh:
        hook = fh.read()
    assert "ruff format --check" in hook

    with open(
        os.path.join(REPO_ROOT, "cli", "requirements-dev.txt"), encoding="utf-8"
    ) as fh:
        assert any(
            line.strip() == "ruff" or line.strip().startswith("ruff==") for line in fh
        )


def test_worktree_carries_linked_skills(tmp_path):
    # #1232: .agents/skills joins WARM_LINK_DIRS with parent-dir creation.
    from dev_tools.services import worktrees as wt

    assert ".agents/skills" in wt.WARM_LINK_DIRS

    root = tmp_path / "root"
    wt_dir = tmp_path / "wt"
    skill_dir = root / ".agents" / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# demo\n")
    wt_dir.mkdir()

    linked = wt.link_warm_deps(str(root), str(wt_dir))
    assert ".agents/skills" in linked
    dst = wt_dir / ".agents" / "skills"
    assert os.path.islink(str(dst))
    assert (dst / "demo-skill" / "SKILL.md").is_file()


def _init_repo(root):
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)


def _head(root):
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_git_dirty_files_detects_dirty_and_untracked(tmp_path):
    # #1232: uncommitted edits surface as indexable dirty paths.
    from dev_tools.services import vector_store as vs

    root = tmp_path / "repo"
    root.mkdir()
    _init_repo(root)
    (root / "a.py").write_text("x = 1\n")
    (root / "notes.txt").write_text("hi\n")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)

    (root / "a.py").write_text("x = 2\n")  # dirty, indexable
    (root / "b.py").write_text("y = 3\n")  # untracked, indexable
    (root / "c.txt").write_text("untracked\n")  # untracked, not indexable

    dirty = vs.git_dirty_files(str(root))
    assert "a.py" in dirty
    assert "b.py" in dirty
    assert "c.txt" not in dirty


def test_update_index_reembeds_dirty_buffers(tmp_path, monkeypatch):
    # #1232: update_index re-embeds git-status dirty buffers.
    from dev_tools.services import vector_store as vs

    root = tmp_path / "repo"
    root.mkdir()
    _init_repo(root)
    (root / "a.py").write_text("x = 1\n")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)

    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"last_indexed_sha": _head(root)}))

    (root / "a.py").write_text("x = 2\n")  # dirty, uncommitted
    (root / "b.py").write_text("y = 3\n")  # untracked, uncommitted

    seen = []

    class _FakeCollection:
        def count(self):
            return 5

    class _FakeStore:
        def __init__(self, persist_directory=""):
            self.collection = _FakeCollection()

        def is_available(self):
            return True

        def add_file_incremental(self, filepath, code, force_reembed=False):
            seen.append((filepath, code))
            return [filepath + ":1-1:abcd"]

        def delete_by_filepath(self, filepath):
            return 0

    monkeypatch.setattr(vs, "VectorStore", _FakeStore)
    data = vs.update_index(
        str(root),
        incremental=True,
        persist_directory=str(tmp_path / "chroma"),
        meta_file=str(meta),
    )
    assert sorted(data["updated_files"]) == ["a.py", "b.py"]
    by_path = dict(seen)
    assert by_path["a.py"] == "x = 2\n"
    assert by_path["b.py"] == "y = 3\n"


def test_remote_server_audit_doc_removed():
    # #1233: tracked remote-server audit leaves the boomtick tree.
    assert not os.path.exists(os.path.join(REPO_ROOT, "design_audit_report.md"))


def test_no_remote_server_literal_in_source():
    # #1233: no /srv/remote-server literal in boomtick source (tracked files).
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    src_suffixes = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sh")
    offenders = []
    for rel in out.stdout.splitlines():
        if rel.startswith("docs/"):
            continue  # audit evidence record, not source coupling
        base = rel.rsplit("/", 1)[-1]
        if (
            "/tests/" in rel
            or "/test/" in rel
            or base.startswith("test_")
            or ".test." in base
        ):
            continue  # the tests asserting this property, not product coupling
        if not (rel.endswith(src_suffixes) or rel.endswith(".json")):
            continue
        if rel.endswith("pnpm-lock.yaml"):
            continue
        full = os.path.join(REPO_ROOT, rel)
        try:
            with open(full, encoding="utf-8", errors="strict") as fh:
                content = fh.read()
        except (OSError, ValueError):
            continue
        if "/srv/remote-server" in content:
            offenders.append(rel)
    assert offenders == []


def test_single_canonical_visual_guidelines():
    # #1234: lib/ copy is canonical; cli/ duplicate deleted; copy retired.
    cli_copy = os.path.join(
        REPO_ROOT, "cli", "dev_tools", "resources", "visual_guidelines.json"
    )
    lib_copy = os.path.join(REPO_ROOT, "lib", "resources", "visual_guidelines.json")
    assert not os.path.exists(cli_copy)
    with open(lib_copy, encoding="utf-8") as fh:
        payload = json.load(fh)
    assert "VISUAL_DESIGN_GUIDELINES" in payload

    with open(
        os.path.join(REPO_ROOT, "lib", "visualGuidelines.ts"), encoding="utf-8"
    ) as fh:
        assert "./resources/visual_guidelines.json" in fh.read()

    with open(
        os.path.join(REPO_ROOT, "scripts", "ensure-schemas.sh"), encoding="utf-8"
    ) as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert not ("visual_guidelines" in line and "cp " in line), (
                "copy block must stay retired"
            )


def test_relative_score_cut_measured():
    # #1236 claim 1: relative-score cut in vector_store.query, measured 8->3.
    import inspect

    from dev_tools.services import vector_store as vs

    assert (
        inspect.signature(vs.VectorStore.query).parameters["min_relative_score"].default
        == 0.4
    )
    scores = [1.0, 0.85, 0.6, 0.39, 0.3, 0.2, 0.1, 0.0]
    results = [
        {"id": f"c{i}", "bm25_score": s, "document": "x" * 500}
        for i, s in enumerate(scores)
    ]
    kept = vs.drop_low_relative_scores(results)
    assert len(kept) == 3  # 8 -> 3
    assert sum(len(r["document"]) for r in results) == 4000
    assert sum(len(r["document"]) for r in kept) == 1500  # 62.5% fewer chars

    # Dormant-BM25 shape (all-zero scores) keeps everything: no silent drops.
    flat = [
        {"id": "a", "bm25_score": 0.0},
        {"id": "b", "bm25_score": 0.0},
    ]
    assert vs.drop_low_relative_scores(flat) == flat
    assert vs.drop_low_relative_scores([]) == []

    # Pin (TRUE): BM25 stays dormant on the product index/query path --
    # update_index never builds it; only the test-only index_files() does.
    assert "build_bm25_index" not in inspect.getsource(vs.update_index)
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    callers = []
    for rel in out.stdout.splitlines():
        if rel.startswith("cli/tests/") or rel.startswith("cli/build/"):
            continue
        full = os.path.join(REPO_ROOT, rel)
        with open(full, encoding="utf-8") as fh:
            for line in fh:
                if "index_files(" in line and "def index_files" not in line:
                    callers.append(rel)
                    break
    assert callers == []


def test_workflow_context_bounded_windows():
    # #1236 claim 3: sliding-window caps, measured 150 -> 100.
    from datetime import datetime

    from dev_tools.workflows.context import WorkflowContext

    assert WorkflowContext.MAX_HISTORY_ENTRIES == 100
    assert WorkflowContext.MAX_SCRATCHPAD_KEYS == 100

    ctx = WorkflowContext()
    tick = datetime(2026, 1, 1)
    for i in range(150):
        ctx.record_node_execution(f"n{i}", "ok", tick, tick)
    assert len(ctx.history) == 100

    for i in range(150):
        ctx.write_scratchpad(f"k{i}", i)
    assert len(ctx.scratchpad) == 100
    assert ctx.read_scratchpad("k149") == 149
    assert ctx.read_scratchpad("k0") is None

    # Pins (all TRUE): deferred claim 2 needs typed DAG state replacing the
    # untyped WorkflowContext._state (workflows/context.py) plus every node
    # call site (workflows/nodes.py); changed-file scoping already exists
    # (services/context_builder.py); prompt gating already done
    # (lib/buildCodeReviewPrompt.ts touchesUI gate).
    with open(
        os.path.join(REPO_ROOT, "cli", "dev_tools", "workflows", "context.py"),
        encoding="utf-8",
    ) as fh:
        assert "self._state: Dict[str, Any] = {}" in fh.read()
    with open(
        os.path.join(REPO_ROOT, "cli", "dev_tools", "workflows", "nodes.py"),
        encoding="utf-8",
    ) as fh:
        nodes_src = fh.read()
    assert (
        sum(nodes_src.count("context." + m + "(") for m in ("get", "set", "update"))
        >= 5
    )
    with open(
        os.path.join(REPO_ROOT, "cli", "dev_tools", "services", "context_builder.py"),
        encoding="utf-8",
    ) as fh:
        builder_src = fh.read()
    assert "changed_files" in builder_src
    assert "Diff truncated" in builder_src
    with open(
        os.path.join(REPO_ROOT, "lib", "buildCodeReviewPrompt.ts"), encoding="utf-8"
    ) as fh:
        prompt_src = fh.read()
    assert "touchesUI" in prompt_src
    assert "summary.changedFiles" in prompt_src
    assert "VISUAL_DESIGN_GUIDELINES" in prompt_src
