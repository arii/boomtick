# pylint: disable=missing-docstring,line-too-long
"""Tests for td rag index/query/init (SHA-tracked incremental indexing)."""
import importlib.util
import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from dev_tools.cli import cli
from dev_tools.services import vector_store as vs


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@t"], root)
    _git(["config", "user.name", "t"], root)
    (root / "src").mkdir()
    (root / "src" / "widget.py").write_text("def widget():\n    return 1\n")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text(
        "# Guide\n\n## Intro\n\nSome intro text here.\n")
    _git(["add", "-A"], root)
    _git(["commit", "-qm", "init"], root)
    _git(["remote", "add", "origin", str(root)], root)
    _git(["fetch", "-q", "origin"], root)
    return root


def _head(root):
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_update_index_full_and_meta(repo, tmp_path):
    meta = str(tmp_path / "meta.json")
    persist = str(tmp_path / "chroma")
    data = vs.update_index(str(repo), incremental=True,
                           persist_directory=persist, meta_file=meta)
    assert data["status"] == "ready"
    assert data["head_sha"] == _head(repo)
    assert data["last_indexed_sha"] == _head(repo)
    assert sorted(data["updated_files"]) == ["docs/guide.md",
                                             "src/widget.py"]
    assert data["removed_files"] == []
    assert os.path.isfile(meta)


def test_update_index_incremental(repo, tmp_path):
    meta = str(tmp_path / "meta.json")
    persist = str(tmp_path / "chroma")
    vs.update_index(str(repo), persist_directory=persist, meta_file=meta)
    (repo / "src" / "widget.py").write_text(
        "def widget():\n    return 2\n")
    (repo / "docs" / "guide.md").unlink()
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "update"], repo)
    data = vs.update_index(str(repo), persist_directory=persist,
                           meta_file=meta)
    assert data["updated_files"] == ["src/widget.py"]
    assert data["removed_files"] == ["docs/guide.md"]
    assert data["last_indexed_sha"] == _head(repo)


def test_update_index_no_changes_is_empty(repo, tmp_path):
    meta = str(tmp_path / "meta.json")
    persist = str(tmp_path / "chroma")
    vs.update_index(str(repo), persist_directory=persist, meta_file=meta)
    data = vs.update_index(str(repo), persist_directory=persist,
                           meta_file=meta)
    assert data["updated_files"] == []
    assert data["removed_files"] == []


def test_chunk_markdown_sections(tmp_path):
    store = vs.VectorStore(
        persist_directory=str(tmp_path / "chroma"))
    chunks = store.chunk_file(
        "# Title\n\nbody one\n\n## Part A\n\ntext a\n\n## Part B\n\ntext b\n",
        "docs/guide.md")
    assert len(chunks) >= 2
    assert all(c["metadata"]["node_type"] == "md_section" for c in chunks)
    titles = [c["metadata"]["section"] for c in chunks]
    assert "Part A" in titles and "Part B" in titles


def test_query_index_empty_graceful(repo, tmp_path):
    hits = vs.query_index(str(repo), "widget",
                          persist_directory=str(tmp_path / "chroma"))
    assert hits == []


def test_add_file_incremental_counts_embeds_only(tmp_path):
    # #1167: cache-skipped chunks are visited, not added — the
    # returned ids (reported as added_chunks) must exclude them.
    store = vs.VectorStore(persist_directory=str(tmp_path / "chroma"))
    code = "def f():\n    return 1\n"
    first = store.add_file_incremental("src/a.py", code)
    assert len(first) > 0
    assert store.add_file_incremental("src/a.py", code) == []


HAS_CHROMA = (
    importlib.util.find_spec("chromadb") is not None
    and importlib.util.find_spec("sentence_transformers") is not None
)


@pytest.mark.skipif(not HAS_CHROMA,
                    reason="needs chromadb + sentence-transformers")
def test_full_rebuild_recovers_diverged_cache(repo, tmp_path):
    # #1167: hashes cached but vectors missing (wiped collection).
    # --full must rebuild everything and reconcile, not report
    # cache-skips as added on a thin index.
    persist = str(tmp_path / "chroma")
    first = vs.update_index(str(repo), incremental=False,
                            persist_directory=persist)
    total = first["added_chunks"]
    assert total > 0
    store = vs.VectorStore(persist_directory=persist)
    assert store.collection.count() == total
    store.collection.delete(ids=store.collection.get()["ids"])
    assert store.collection.count() == 0
    second = vs.update_index(str(repo), incremental=False,
                             persist_directory=persist)
    assert second["added_chunks"] == total
    fresh = vs.VectorStore(persist_directory=persist)
    assert fresh.collection.count() == total


def test_query_index_broken_store_raises(repo, tmp_path):
    # #1165: exceptions fail loud instead of returning [] silently.
    def broken(self, query_text, n_results=8, hybrid=True):
        raise RuntimeError("index unreadable")

    orig = vs.VectorStore.query
    vs.VectorStore.query = broken
    try:
        with pytest.raises(RuntimeError, match="index unreadable"):
            vs.query_index(str(repo), "widget",
                           persist_directory=str(tmp_path / "chroma"))
    finally:
        vs.VectorStore.query = orig


def test_cli_rag_index_query_init(repo, tmp_path):
    runner = CliRunner()
    indexed = runner.invoke(cli, ["rag", "index", "--repo-root",
                                 str(repo), "--json"])
    assert indexed.exit_code == 0, indexed.output
    payload = json.loads(indexed.output)
    assert payload["status"] == "ready"
    assert payload["head_sha"]

    queried = runner.invoke(cli, ["rag", "query", "--repo-root",
                                 str(repo), "--query", "widget",
                                 "--top-k", "3", "--json"])
    assert queried.exit_code == 0, queried.output
    payload = json.loads(queried.output)
    assert set(payload) >= {"status", "query", "hits", "count"}
    assert isinstance(payload["hits"], list)

    inited = runner.invoke(cli, ["init", "--repo-root", str(repo),
                                "--json"])
    assert inited.exit_code == 0, inited.output
    payload = json.loads(inited.output)
    assert set(payload) >= {"status", "head_sha", "deps_synced",
                            "rag_indexed_sha", "updated_files"}
