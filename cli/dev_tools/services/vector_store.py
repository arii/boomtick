import os
from typing import List, Dict, Any, Optional

class VectorStore:
    def __init__(self, persist_directory: str = "artifacts/chroma_db", collection_name: str = "codebase"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embedding_fn = None

    @property
    def client(self):
        if self._client is None and self.is_available():
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_directory)
        return self._client

    @property
    def embedding_fn(self):
        if self._embedding_fn is None and self.is_available():
            from chromadb.utils import embedding_functions
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        return self._embedding_fn

    @property
    def collection(self):
        if self._collection is None:
            client = self.client
            embedding_fn = self.embedding_fn
            if client and embedding_fn:
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=embedding_fn
                )
        return self._collection

    def is_available(self) -> bool:
        """Checks if ChromaDB and dependencies are available."""
        try:
            import chromadb
            return True
        except ImportError:
            return False

    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """Adds documents to the collection."""
        collection = self.collection
        if collection:
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

    def query(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Queries the collection for similar documents."""
        collection = self.collection
        if not collection:
            return []

        results = collection.query(
            query_texts=[query_text],
            n_results=n_results
        )

        # Format results for easier consumption
        formatted_results = []
        if results['documents']:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "id": results['ids'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results else None
                })
        return formatted_results

    def reset(self):
        """Resets the collection."""
        client = self.client
        embedding_fn = self.embedding_fn
        if not client or not embedding_fn:
            return

        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = client.create_collection(
            name=self.collection_name,
            embedding_function=embedding_fn
        )
