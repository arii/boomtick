import asyncio
import json

import httpx
import pytest

from twt.catalog import sync
from twt.gateway import create_app
from test_gateway import reply


MODEL = "test-chat:latest"
REQUEST = {"model": "default", "messages": [{"role": "user", "content": "Hello"}]}


@pytest.mark.parametrize("runtime_available", [True, False])
def test_ollama_local_only(store, monkeypatch, runtime_available):
    monkeypatch.setenv("TWT_OLLAMA_MODEL", MODEL)
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "0")
    monkeypatch.setenv("GROQ_API_KEY", "not-used")
    seen = []
    cloud_disabled = True

    def handler(request):
        assert request.url.host == "127.0.0.1" and request.url.port == 11434
        assert "Authorization" not in request.headers
        seen.append(request.url.path)
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": cloud_disabled}})
        if request.url.path == "/api/ps":
            if not runtime_available:
                return httpx.Response(503)
            return httpx.Response(200, json={"models": [
                {"model": "unrelated:latest", "context_length": 128},
                {"model": "registry.ollama.ai/library/test-chat", "context_length": 1024},
            ]})
        body = json.loads(request.content)
        assert body["model"] == MODEL
        if request.url.path == "/api/show":
            return httpx.Response(200, json={
                "capabilities": ["completion", "tools"],
                "model_info": {"general.architecture": "test_arch", "test_arch.context_length": 4096},
            })
        assert body["stream"] is False
        return httpx.Response(200, json=reply(prompt=900))

    async def scenario():
        nonlocal cloud_disabled
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            assert "ollama: synced 1 model" in await sync(store, upstream)
            assert store.models()[0]["tools"]
            app = create_app(store, upstream)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
                advertised = (await api.get("/v1/models")).json()["data"]
                assert [row["id"] for row in advertised] == [f"ollama/{MODEL}"]
                response = await api.post("/v1/chat/completions", json=REQUEST, headers={"X-Privacy": "strict"})
                assert response.status_code == 200
                assert response.headers["X-Provider-Used"] == "ollama"
                assert response.headers["X-Cost-Usd"] == "0.0"
                assert response.headers["X-Audit-Flags"] == ("CONTEXT_BLOAT" if runtime_available else "")
                trace = store.trace(response.headers["X-Trace-Id"])
                assert trace["model"] == MODEL and trace["cost_complete"]
                rejected = await api.post("/v1/chat/completions", json={**REQUEST, "model": "other:latest"})
                assert rejected.status_code == 503
                cloud_disabled = False
                rejected = await api.post("/v1/chat/completions", json=REQUEST)
                assert rejected.status_code == 503
                trace = store.trace(rejected.headers["X-Trace-Id"])
                assert len(trace["attempts"]) == 1 and not trace["attempts"][0]["called"]

    asyncio.run(scenario())
    assert seen == ["/api/status", "/api/show", "/api/status", "/v1/chat/completions", "/api/ps", "/api/status"]


@pytest.mark.parametrize("details", [
    {"capabilities": ["embedding"]},
    {"capabilities": ["completion"], "remote_model": "hosted"},
    {"capabilities": ["completion"], "remote_host": "https://ollama.com"},
    {"capabilities": "completion"},
])
def test_ollama_rejects_unsupported_models(store, monkeypatch, details):
    monkeypatch.setenv("TWT_OLLAMA_MODEL", MODEL)

    def handler(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        return httpx.Response(200, json=details)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            with pytest.raises(ValueError, match="local chat model"):
                await sync(store, upstream)
    asyncio.run(scenario())
    assert not store.models()


@pytest.mark.parametrize("status", [{"cloud": {"disabled": False}}, {}])
def test_ollama_sync_requires_confirmed_cloud_setting(store, monkeypatch, status):
    monkeypatch.setenv("TWT_OLLAMA_MODEL", MODEL)

    def handler(request):
        assert request.url.path == "/api/status"
        return httpx.Response(200, json=status)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
            with pytest.raises(ValueError, match="cloud must be disabled"):
                await sync(store, upstream)
    asyncio.run(scenario())
    assert not store.models()
