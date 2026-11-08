# pylint: disable=missing-docstring,try-except-raise,import-outside-toplevel
import hashlib
import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from dataclasses import dataclass, field

from dev_tools.utils import log_warn

TD_RAG_DIR = ".td_rag"
META_FILENAME = "meta.json"

INDEXABLE_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts",
    ".md", ".markdown",
)

SKIP_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".worktrees", ".td_rag",
    "chroma_db", "traces", "fixtures", ".mypy_cache", ".pytest_cache",
})


def default_store_paths(repo_root: str) -> Tuple[str, str]:
    """(persist_directory, meta_file) for a repo root."""
    base = os.path.join(os.path.abspath(repo_root), TD_RAG_DIR)
    return os.path.join(base, "chroma_db"), os.path.join(base, META_FILENAME)


def read_meta(meta_file: str) -> Dict[str, Any]:
    """Last indexed state, or {} when no index exists yet."""
    try:
        with open(meta_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_meta(meta_file: str, meta: Dict[str, Any]) -> None:
    """Persist last indexed state (best effort)."""
    try:
        os.makedirs(os.path.dirname(meta_file), exist_ok=True)
        with open(meta_file, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2)
    except OSError as e:
        log_warn(f"vector_store: meta write failed for {meta_file}: {e}")


def git_head_sha(repo_root: str) -> str:
    """HEAD commit SHA, or '' when git is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except OSError:
        return ""


def git_name_status(repo_root: str, base: str, head: str = "HEAD"
                    ) -> List[Tuple[str, str, str]]:
    """[(status, path, old_path)] for base..head (renames split out).

    status is one of A/C/D/M/R/T/U/X; old_path is set for renames.
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-status", "-M",
             f"{base}..{head}", "--", "."],
            cwd=repo_root, capture_output=True, text=True, check=False)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][:1], parts[1]
        old_path = parts[2] if len(parts) > 2 and status == "R" else ""
        out.append((status, path, old_path))
    return out


def iter_repo_files(repo_root: str):
    """Sorted repo-relative paths of indexable files."""
    root = os.path.abspath(repo_root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            if not name.endswith(INDEXABLE_EXTENSIONS):
                continue
            full = os.path.join(dirpath, name)
            try:
                if not os.path.isfile(full):
                    continue
            except OSError:
                continue
            found.append(os.path.relpath(full, root))
    return found

@dataclass
class BM25State:  # pylint: disable=too-few-public-methods
    index: Any = None
    corpus_ids: List[str] = field(default_factory=list)
    corpus_docs: List[List[str]] = field(default_factory=list)


class VectorStore:
    def __init__(self, persist_directory: str = "artifacts/chroma_db", collection_name: str = "codebase"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embedding_fn = None
        self._bm25 = BM25State()
        self._cache: Dict[str, str] = self._load_cache()

    @property
    def cache_file(self) -> str:
        return os.path.join(self.persist_directory, "ast_hash_cache.json")

    def _load_cache(self) -> Dict[str, str]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            log_warn(f"vector_store: cache save failed for {self.cache_file}: {e}")

    @property
    def client(self):
        if self._client is None and self.is_available():
            import chromadb  # pylint: disable=import-error
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        return self._client

    @property
    def embedding_fn(self):
        if self._embedding_fn is None and self.is_available():
            from chromadb.utils import embedding_functions  # pylint: disable=import-error
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        return self._embedding_fn

    @property
    def collection(self):
        if self._collection is None:
            client = self.client
            embedding_fn = self.embedding_fn
            if client and embedding_fn:
                self._collection = client.get_or_create_collection(
                    name=self.collection_name, embedding_function=embedding_fn
                )
        return self._collection

    def is_available(self) -> bool:
        """Checks if ChromaDB and dependencies are available."""
        try:
            # pylint: disable=unused-import
            import chromadb  # pylint: disable=import-error
            import sentence_transformers  # pylint: disable=import-error
            return True
        except ImportError:
            return False

    def tokenize_text(self, text: str) -> List[str]:
        """Tokenize text into lowercased identifiers/symbols for BM25 search."""
        return [tok.lower() for tok in re.findall(r"[A-Za-z0-9_]+", text) if len(tok) > 1]

    def build_bm25_index(self, documents: List[str], ids: List[str]) -> None:
        """Build or update the BM25 index over documents."""
        try:
            from rank_bm25 import BM25Okapi  # pylint: disable=import-error
            tokenized_corpus = [self.tokenize_text(doc) for doc in documents]
            self._bm25.corpus_docs = tokenized_corpus
            self._bm25.corpus_ids = ids
            if tokenized_corpus:
                self._bm25.index = BM25Okapi(tokenized_corpus)
            else:
                self._bm25.index = None
        except ImportError:
            self._bm25.index = None

    def _collect_ast_nodes(self, tree, code_bytes: bytes) -> List[Any]:
        nodes_to_chunk = []

        def visit(node):
            ntype = node.type
            if ntype in (
                "interface_declaration",
                "function_declaration",
                "class_declaration",
                "type_alias_declaration",
                "enum_declaration",
                "method_definition",
            ):
                nodes_to_chunk.append(node)
            elif ntype in ("export_statement", "lexical_declaration"):
                code_snippet = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
                has_decl = any(kw in code_snippet for kw in ("function", "=>", "class", "interface"))
                if has_decl:
                    nodes_to_chunk.append(node)
                else:
                    for child in node.children:
                        visit(child)
            else:
                for child in node.children:
                    visit(child)

        visit(tree.root_node)

        selected_nodes: List[Any] = []
        for node_item in nodes_to_chunk:
            is_nested = any(
                parent.start_byte <= node_item.start_byte and parent.end_byte >= node_item.end_byte
                for parent in selected_nodes
                if parent != node_item
            )
            if not is_nested:
                selected_nodes.append(node_item)

        return selected_nodes

    def _chunk_ts_ast(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        try:
            import tree_sitter  # pylint: disable=import-error
            import tree_sitter_typescript as tsts  # pylint: disable=import-error

            ts_lang = tsts.language_tsx() if filepath.endswith("x") else tsts.language_typescript()
            lang = tree_sitter.Language(ts_lang)
            parser = tree_sitter.Parser(lang)
            code_bytes = code.encode("utf-8")
            tree = parser.parse(code_bytes)

            selected_nodes = self._collect_ast_nodes(tree, code_bytes)

            for idx, node in enumerate(selected_nodes):
                chunk_str = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore").strip()
                if chunk_str:
                    chunks.append({
                        "content": chunk_str,
                        "metadata": {
                            "filepath": filepath,
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "node_type": node.type,
                            "chunk_index": idx,
                        },
                    })
        except Exception:
            return []
        return chunks

    def _chunk_lines(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        lines = code.splitlines()
        chunk_size = 50
        for i in range(0, len(lines), chunk_size):
            chunk_lines = lines[i:i + chunk_size]
            chunk_str = "\n".join(chunk_lines).strip()
            if chunk_str:
                chunks.append({
                    "content": chunk_str,
                    "metadata": {
                        "filepath": filepath,
                        "start_line": i + 1,
                        "end_line": i + len(chunk_lines),
                        "node_type": "line_block",
                        "chunk_index": i // chunk_size,
                    },
                })
        return chunks

    def chunk_code_ast(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses TS/TSX file using tree-sitter to slice strictly at interface, function,
        component, method, class, and export boundaries.
        Falls back to line chunking if tree-sitter is unavailable or fails.
        """
        if filepath.endswith((".ts", ".tsx", ".js", ".jsx")):
            chunks = self._chunk_ts_ast(code, filepath)
            if chunks:
                return chunks
        return self._chunk_lines(code, filepath)

    def _chunk_markdown(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        """Split markdown on ATX headers into ~120-line sections."""
        chunks: List[Dict[str, Any]] = []
        section_lines: List[str] = []
        section_start = 1
        section_title = ""
        chunk_index = 0

        def flush(end_line: int) -> None:
            nonlocal chunk_index
            text = "\n".join(section_lines).strip()
            if text:
                chunks.append({
                    "content": text,
                    "metadata": {
                        "filepath": filepath,
                        "start_line": section_start,
                        "end_line": end_line,
                        "node_type": "md_section",
                        "chunk_index": chunk_index,
                        "section": section_title,
                    },
                })
                chunk_index += 1

        for lineno, line in enumerate(code.splitlines(), start=1):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match and section_lines and (
                    len(section_lines) >= 120 or section_title):
                flush(lineno - 1)
                section_lines = []
                section_start = lineno
            if match:
                section_title = match.group(2)
            section_lines.append(line)
            if len(section_lines) >= 150:
                flush(lineno)
                section_lines = []
                section_start = lineno + 1
        flush(len(code.splitlines()))
        return chunks or self._chunk_lines(code, filepath)

    def chunk_file(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        """Chunk by kind: AST for code, sections for markdown."""
        if filepath.endswith((".md", ".markdown")):
            return self._chunk_markdown(code, filepath)
        return self.chunk_code_ast(code, filepath)

    def delete_by_filepath(self, filepath: str) -> int:
        """Delete every chunk for a filepath; returns removed estimate."""
        removed = 0
        prefix = f"{filepath}:"
        for chunk_id in [cid for cid in self._cache if cid.startswith(prefix)]:
            del self._cache[chunk_id]
            removed += 1
        self._save_cache()
        collection = self.collection
        if collection is not None:
            try:
                collection.delete(where={"filepath": filepath})
            except Exception as e:
                log_warn(f"vector_store: vector delete failed for {filepath}: {e}")
        return removed

    def add_file_incremental(self, filepath: str, code: str, force_reembed: bool = False) -> List[str]:
        """
        AST chunks a file, hashes each node content, and only embeds/updates new or modified chunks.
        """
        chunks = self.chunk_file(code, filepath)
        ids_added = []
        documents_to_add = []
        metadatas_to_add = []
        ids_to_add = []

        for chunk in chunks:
            content = chunk["content"]
            meta = chunk["metadata"]
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk_id = f"{filepath}:{meta['start_line']}-{meta['end_line']}:{content_hash[:8]}"

            cached_hash = self._cache.get(chunk_id)
            if force_reembed or cached_hash != content_hash:
                documents_to_add.append(content)
                metadatas_to_add.append(meta)
                ids_to_add.append(chunk_id)
                self._cache[chunk_id] = content_hash
                # Count embedded chunks only: cache-skipped chunks are
                # visited, not added, and callers report this length
                # as added_chunks (issue #1167).
                ids_added.append(chunk_id)

        if documents_to_add:
            self.add_documents(documents=documents_to_add, metadatas=metadatas_to_add, ids=ids_to_add)
            self._save_cache()

        return ids_added

    def index_files(self, file_map: Dict[str, str], changed_files_only: Optional[List[str]] = None) -> None:
        """
        Indexes files in file_map (dict of filepath -> code content).
        If changed_files_only is supplied, only process files modified in git diff.
        Also initializes BM25 index over all indexed chunks.
        """
        all_docs = []
        all_ids = []

        files_to_process = changed_files_only if changed_files_only is not None else list(file_map.keys())

        for fp in files_to_process:
            if fp in file_map:
                code = file_map[fp]
                self.add_file_incremental(fp, code)

        # Populate BM25 index over collection if client exists
        col = self.collection
        if col:
            col_data = col.get()
            if col_data and col_data.get("documents"):
                all_docs = col_data["documents"]
                all_ids = col_data["ids"]
                self.build_bm25_index(all_docs, all_ids)

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """Adds documents to the collection."""
        collection = self.collection
        if collection:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)

    def query(self, query_text: str, n_results: int = 5, hybrid: bool = True) -> List[Dict[str, Any]]:
        """Queries the collection for similar documents, optionally using BM25 hybrid reranking."""
        collection = self.collection
        if not collection:
            return []

        vector_results = collection.query(query_texts=[query_text], n_results=n_results)

        formatted_results = []
        if vector_results["documents"] and vector_results["documents"][0]:
            for i in range(len(vector_results["documents"][0])):
                formatted_results.append(
                    {
                        "document": vector_results["documents"][0][i],
                        "metadata": vector_results["metadatas"][0][i],
                        "id": vector_results["ids"][0][i],
                        "distance": vector_results["distances"][0][i] if "distances" in vector_results else None,
                        "bm25_score": 0.0,
                    }
                )

        if hybrid and self._bm25.index and self._bm25.corpus_ids:
            query_tokens = self.tokenize_text(query_text)
            if query_tokens:
                bm25_scores = self._bm25.index.get_scores(query_tokens)
                score_dict = dict(zip(self._bm25.corpus_ids, bm25_scores))
                for item in formatted_results:
                    item["bm25_score"] = score_dict.get(item["id"], 0.0)

                formatted_results.sort(
                    key=lambda x: (x["bm25_score"], -x["distance"] if x["distance"] is not None else 0),
                    reverse=True
                )

        return formatted_results[:n_results]

    def reset(self):
        """Resets the collection and cache."""
        client = self.client
        embedding_fn = self.embedding_fn
        if not client or not embedding_fn:
            # Clear the hash cache unconditionally: a cache without
            # vectors is the poison — it makes later walks cache-skip
            # everything even when the collection was never rebuilt
            # (issue #1167, warm-cache + no-backend hole).
            self._cache = {}
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            self._bm25 = BM25State()
            return

        try:
            client.delete_collection(self.collection_name)
        except Exception as e:
            # Deleting a collection that was never created is an expected
            # no-op (first index), not a warning. Machine-output commands
            # (e.g. rag index --json) must stay parseable.
            if "does not exist" not in str(e).lower():
                log_warn(f"vector_store: collection delete failed for {self.collection_name}: {e}")
        self._collection = client.create_collection(name=self.collection_name, embedding_function=embedding_fn)
        # Only purge caches after the replacement collection exists,
        # so a failed create leaves the prior state intact.
        self._cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
        self._bm25 = BM25State()


def _is_indexable(path: str) -> bool:
    return path.endswith(INDEXABLE_EXTENSIONS)


def update_index(repo_root: str, incremental: bool = True,
                 persist_directory: str = "",
                 meta_file: str = "") -> Dict[str, Any]:
    """Incrementally update the vector index for a repo root.

    Full pass on first run (or incremental=False): walks indexable
    files, embeds new/modified chunks, deletes chunks for removed
    files, and records HEAD in meta. Incremental pass: diffs
    last_indexed_sha..HEAD, re-embeds A/C/M/T files, drops chunks for
    D/R files, and advances the SHA. Returns a status dict.
    """
    repo_root = os.path.abspath(repo_root)
    default_persist, default_meta = default_store_paths(repo_root)
    persist_directory = persist_directory or default_persist
    meta_file = meta_file or default_meta
    os.makedirs(persist_directory, exist_ok=True)
    store = VectorStore(persist_directory=persist_directory)
    head_sha = git_head_sha(repo_root)
    meta = read_meta(meta_file)
    last_sha = meta.get("last_indexed_sha", "") if incremental else ""

    updated_files: List[str] = []
    removed_files: List[str] = []
    added_chunks = 0

    if last_sha and head_sha and last_sha != head_sha:
        for status, path, old_path in git_name_status(
                repo_root, last_sha, head_sha):
            if old_path:
                removed_files.append(old_path)
                store.delete_by_filepath(old_path)
            if status == "D":
                removed_files.append(path)
                store.delete_by_filepath(path)
            elif _is_indexable(path):
                full = os.path.join(repo_root, path)
                if os.path.isfile(full):
                    try:
                        with open(full, encoding="utf-8",
                                  errors="ignore") as handle:
                            code = handle.read()
                    except OSError:
                        continue
                    ids = store.add_file_incremental(path, code)
                    if ids:
                        added_chunks += len(ids)
                    updated_files.append(path)
    elif not last_sha or not head_sha or last_sha != head_sha:
        # Full rebuild: drop collection + hash cache first so a
        # diverged cache (hashes recorded, vectors missing) cannot
        # skip files and report them as added (issue #1167).
        store.reset()
        for path in iter_repo_files(repo_root):
            full = os.path.join(repo_root, path)
            try:
                with open(full, encoding="utf-8",
                          errors="ignore") as handle:
                    code = handle.read()
            except OSError:
                continue
            ids = store.add_file_incremental(path, code)
            if ids:
                added_chunks += len(ids)
            updated_files.append(path)
        if head_sha:
            removed_files = []
        # Reconcile: after a reset rebuild the collection must hold
        # exactly what was embedded; a shortfall fails loud naming
        # the gap instead of exiting 0 on a thin index (issue #1167).
        collection = store.collection
        if collection is not None:
            actual = collection.count()
            if actual != added_chunks:
                raise RuntimeError(
                    f"rag index shortfall: embedded {added_chunks} "
                    f"chunks but collection holds {actual}")

    # Degraded-env hole (#1167): with no embedding backend the walk
    # above still counts chunks while persisting zero vectors. Fail
    # loud instead of reporting ready on an empty collection. Key on
    # visited files, not embedded-this-run: a warm cache with no
    # backend embeds nothing (added_chunks == 0) yet would still
    # stamp a SHA over an unverifiable index.
    if updated_files and store.collection is None:
        raise RuntimeError(
            f"rag index has no embedding backend: visited "
            f"{len(updated_files)} files but the collection is "
            "unavailable (install chromadb + sentence-transformers)")

    # Incremental-path emptiness guard (#1181): the changed-files
    # walk above never reconciles, so a diverged cache (hashes
    # recorded, vectors missing) embeds nothing while the stamp
    # below would launder the thin index. When indexable files
    # exist but the collection holds no vectors, fail loud
    # instead of advancing last_indexed_sha over an unverified
    # index; a full rebuild (rag index --full) repairs it.
    if incremental and last_sha and head_sha:
        _collection = store.collection
        if _collection is not None and _collection.count() == 0 \
                and iter_repo_files(repo_root):
            raise RuntimeError(
                "rag index unverified: collection holds 0 vectors "
                "but indexable files exist; refusing to advance "
                "last_indexed_sha (rebuild with rag index --full)")

    if head_sha and store.collection is not None:
        meta["last_indexed_sha"] = head_sha
        meta["updated_files"] = sorted(set(updated_files))
        write_meta(meta_file, meta)
    return {
        "status": "ready",
        "head_sha": head_sha,
        "last_indexed_sha": meta.get("last_indexed_sha", ""),
        "updated_files": sorted(set(updated_files)),
        "removed_files": sorted(set(removed_files)),
        "added_chunks": added_chunks,
        "index_available": store.is_available(),
    }


def query_index(repo_root: str, query: str, top_k: int = 8,
                persist_directory: str = "") -> List[Dict[str, Any]]:
    """Hybrid query over the repo index; [] when nothing is indexed.

    Fail-loud on exception (issue #1165): an empty index returns []
    via store.query itself, so anything raised here is a broken query
    the caller must see. Matches the fail-loud update_index behavior
    from #1094.
    """
    repo_root = os.path.abspath(repo_root)
    default_persist, _ = default_store_paths(repo_root)
    store = VectorStore(persist_directory=persist_directory or default_persist)
    results = store.query(query, n_results=top_k, hybrid=True)
    hits = []
    for item in results or []:
        meta = item.get("metadata") or {}
        hits.append({
            "content": item.get("document", ""),
            "filepath": meta.get("filepath", ""),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "score": item.get("bm25_score", 0.0),
            "distance": item.get("distance"),
        })
    return hits
