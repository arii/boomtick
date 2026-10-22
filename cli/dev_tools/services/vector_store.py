# pylint: disable=missing-docstring,try-except-raise,import-outside-toplevel
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

class VectorStore:
    def __init__(self, persist_directory: str = "artifacts/chroma_db", collection_name: str = "codebase"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.cache_file = os.path.join(persist_directory, "ast_hash_cache.json")
        self._client = None
        self._collection = None
        self._embedding_fn = None
        self._bm25_index = None
        self._bm25_corpus_ids: List[str] = []
        self._bm25_corpus_docs: List[List[str]] = []
        self._cache: Dict[str, str] = self._load_cache()

    # pylint: disable=too-many-instance-attributes

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
        except Exception:
            pass

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
            self._bm25_corpus_docs = tokenized_corpus
            self._bm25_corpus_ids = ids
            if tokenized_corpus:
                self._bm25_index = BM25Okapi(tokenized_corpus)
            else:
                self._bm25_index = None
        except ImportError:
            self._bm25_index = None

    def chunk_code_ast(self, code: str, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses TS/TSX file using tree-sitter to slice strictly at interface, function,
        component, method, class, and export boundaries.
        Falls back to line chunking if tree-sitter is unavailable or fails.
        """
        chunks: List[Dict[str, Any]] = []

        is_ts_file = filepath.endswith(".ts") or filepath.endswith(".tsx") or filepath.endswith(".js") or filepath.endswith(".jsx")

        if is_ts_file:
            try:
                import tree_sitter  # pylint: disable=import-error
                import tree_sitter_typescript as tsts  # pylint: disable=import-error

                lang = tree_sitter.Language(tsts.language_tsx() if filepath.endswith("x") else tsts.language_typescript())
                parser = tree_sitter.Parser(lang)
                code_bytes = code.encode("utf-8")
                tree = parser.parse(code_bytes)

                nodes_to_chunk = []

                def visit(node):
                    ntype = node.type
                    # Capture top-level declarations, components, interfaces, classes, methods
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
                        # Check if export or lexical decl wraps a function/component
                        code_snippet = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")
                        if "function" in code_snippet or "=>" in code_snippet or "class" in code_snippet or "interface" in code_snippet:
                            nodes_to_chunk.append(node)
                        else:
                            for child in node.children:
                                visit(child)
                    else:
                        for child in node.children:
                            visit(child)

                visit(tree.root_node)

                # Deduplicate overlapping nodes (prefer parent nodes)
                selected_nodes: List[Any] = []
                for node_item in nodes_to_chunk:
                    # Check if node is inside another selected node
                    is_nested = any(
                        parent.start_byte <= node_item.start_byte and parent.end_byte >= node_item.end_byte
                        for parent in selected_nodes
                        if parent != node_item
                    )
                    if not is_nested:
                        selected_nodes.append(node_item)

                for idx, node in enumerate(selected_nodes):
                    chunk_str = code_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore").strip()
                    if chunk_str:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        node_type = node.type
                        chunks.append({
                            "content": chunk_str,
                            "metadata": {
                                "filepath": filepath,
                                "start_line": start_line,
                                "end_line": end_line,
                                "node_type": node_type,
                                "chunk_index": idx
                            }
                        })
            except Exception:
                chunks = []

        # Fallback line chunking if tree-sitter not used/failed or 0 chunks generated
        if not chunks:
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
                            "chunk_index": i // chunk_size
                        }
                    })

        return chunks

    def add_file_incremental(self, filepath: str, code: str, force_reembed: bool = False) -> List[str]:
        """
        AST chunks a file, hashes each node content, and only embeds/updates new or modified chunks.
        """
        chunks = self.chunk_code_ast(code, filepath)
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

        if hybrid and self._bm25_index and self._bm25_corpus_ids:
            query_tokens = self.tokenize_text(query_text)
            if query_tokens:
                bm25_scores = self._bm25_index.get_scores(query_tokens)
                score_dict = dict(zip(self._bm25_corpus_ids, bm25_scores))
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
            return

        client.delete_collection(self.collection_name)
        self._collection = client.create_collection(name=self.collection_name, embedding_function=embedding_fn)
        self._cache = {}
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
        self._bm25_index = None
        self._bm25_corpus_ids = []
        self._bm25_corpus_docs = []
