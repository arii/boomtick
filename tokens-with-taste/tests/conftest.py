import pytest

from twt.catalog import providers
from twt.store import Store


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for provider in providers():
        for name in [provider["key_env"], *provider.get("required_env", [])]:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("TWT_DAILY_BUDGET_USD", raising=False)
    monkeypatch.delenv("TWT_OLLAMA_MODEL", raising=False)


@pytest.fixture
def store(tmp_path):
    storage = Store(tmp_path / "test.sqlite3")
    yield storage
    storage.close()
