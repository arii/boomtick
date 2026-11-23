import json

import httpx
from test_gateway import reply, run, setup
from twt.gateway import eligible_models


def test_strong_local_free_nebius_order_and_receipt(store, monkeypatch):
    config = setup(store, monkeypatch, 3)
    for provider, name, free in zip(
        config, ["nebius", "nvidia", "openrouter"], [False, True, True]
    ):
        old = provider["id"]
        provider["id"] = name
        provider["strong_model"] = f"{name}-strong"
        rows = store.models()
        model = next(m for m in rows if m["provider"] == old)
        model.update(
            provider=name,
            id=f"{name}-strong",
            free=free,
            input_price=0 if free else 0.001,
            output_price=0 if free else 0.002,
        )
        store.replace_models(name, [model])
    local = {
        **model,
        "provider": "ollama",
        "id": "local-strong",
        "free": True,
        "input_price": 0,
        "output_price": 0,
    }
    store.replace_models("ollama", [local])
    monkeypatch.setenv("TWT_OLLAMA_STRONG_MODEL", "local-strong")
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "5")
    sent = []

    def handler(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        body = json.loads(request.content)
        sent.append(body["model"])
        if body["model"] != "nebius-strong":
            return httpx.Response(500, json={"error": "fixture unavailable"})
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store,
        config,
        handler,
        body={
            "model": "route:strong",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status == 200
    assert sent == [
        "local-strong",
        "nvidia-strong",
        "openrouter-strong",
        "nebius-strong",
    ]
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["route"] == "route:strong"
    assert [a["model"] for a in trace["attempts"] if a["called"]] == sent
    assert trace["provider"] == "nebius"
    assert trace["known_cost_usd"] == 0.05


def test_strong_missing_selected_model_does_not_substitute():
    model = {"provider": "nvidia", "id": "weak", "chat": True, "free": True}
    provider = {"id": "nvidia", "strong_model": "strong", "free_only": True}
    assert eligible_models([model], provider, {"model": "route:strong"}) == []
    assert eligible_models([model], provider, {"model": "default"}) == [model]


def test_strong_paid_fallback_still_obeys_budget(store, monkeypatch):
    config = setup(store, monkeypatch, 1)
    config[0]["strong_model"] = "chat"
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "0")
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store,
        config,
        handler,
        body={
            "model": "route:strong",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status != 200
    assert sent == []
    trace = store.trace(headers["X-Trace-Id"])
    assert not any(a["called"] for a in trace["attempts"])


def test_strong_environment_selection_and_invalid_configuration(store, monkeypatch):
    config = setup(store, monkeypatch, 1)
    monkeypatch.setenv("TWT_STRONG_MODELS", '{"p0":"chat"}')
    _, status, headers = run(
        store,
        config,
        lambda request: httpx.Response(200, json=reply()),
        body={
            "model": "route:strong",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status == 200
    assert store.trace(headers["X-Trace-Id"])["model"] == "chat"
    monkeypatch.setenv("TWT_STRONG_MODELS", '{"unknown":"chat"}')
    _, status, headers = run(
        store,
        config,
        lambda request: httpx.Response(200, json=reply()),
        body={
            "model": "route:strong",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status == 400
    assert store.trace(headers["X-Trace-Id"])["attempts"] == []


def test_local_only_mode_never_adopts_hosted_strong_providers(store, monkeypatch):
    from twt.gateway import Gateway, create_app

    monkeypatch.setenv("TWT_OLLAMA_MODEL", "local-only")
    async_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    assert [p["id"] for p in Gateway(store, async_client).strong_providers] == [
        "ollama"
    ]
    # Constructing an app must preserve the same local-only boundary.
    create_app(store, async_client)
    import asyncio

    asyncio.run(async_client.aclose())
