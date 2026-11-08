"""Focused reset() tests: missing-collection delete is an idempotent no-op."""

from dev_tools.services.vector_store import VectorStore


class _FakeClient:
    def __init__(self, delete_error=None):
        self.delete_error = delete_error
        self.deleted = []
        self.created = []

    def delete_collection(self, name):
        self.deleted.append(name)
        if self.delete_error is not None:
            raise self.delete_error

    def create_collection(self, name, embedding_function=None):
        self.created.append(name)
        return object()


def _store(tmp_path, client):
    store = VectorStore(persist_directory=str(tmp_path))
    store._client = client
    store._embedding_fn = object()
    return store


def test_reset_missing_collection_is_silent(tmp_path, capsys):
    client = _FakeClient(delete_error=Exception("Collection [codebase] does not exist"))
    _store(tmp_path, client).reset()
    assert client.created == ["codebase"]
    assert capsys.readouterr().err == ""


def test_reset_unexpected_delete_error_warns(tmp_path, capsys):
    client = _FakeClient(delete_error=RuntimeError("boom"))
    _store(tmp_path, client).reset()
    assert "collection delete failed" in capsys.readouterr().err
