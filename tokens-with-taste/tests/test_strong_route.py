import asyncio
import json

import httpx
import pytest
from test_gateway import reply, run, setup
from twt.gateway import Gateway, create_app, eligible_models


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


def strong_row(provider, model, free):
    return {
        "id": model,
        "provider": provider,
        "chat": True,
        "free": free,
        "tools": True,
        "json": True,
        "json_schema": True,
        "input_price": 0 if free else 0.001,
        "output_price": 0 if free else 0.002,
        "context_length": 100000,
        "rpm": 30,
        "daily": None,
    }


def test_strong_route_http_order_models_and_receipt(store, monkeypatch):
    hosted = {"google": True, "groq": True, "nebius": False}
    models = {name: f"{name}-strong" for name in hosted}
    for name, free in hosted.items():
        store.replace_models(name, [strong_row(name, models[name], free)])
    store.replace_models("ollama", [strong_row("ollama", "local-strong", True)])
    for env in (
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "NVIDIA_API_KEY",
        "MISTRAL_API_KEY",
        "OPENROUTER_API_KEY",
        "SAMBANOVA_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "NEBIUS_API_KEY",
    ):
        monkeypatch.delenv(env, raising=False)
    for env in ("GOOGLE_API_KEY", "GROQ_API_KEY", "NEBIUS_API_KEY"):
        monkeypatch.setenv(env, "test-only-placeholder")
    monkeypatch.delenv("TWT_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("TWT_STRONG_MODELS", json.dumps(models))
    monkeypatch.setenv("TWT_OLLAMA_STRONG_MODEL", "local-strong")
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "5")
    sent = []

    def handler(request):
        if request.url.path == "/api/status":
            return httpx.Response(200, json={"cloud": {"disabled": True}})
        body = json.loads(request.content)
        sent.append((request.url.host, body["model"]))
        if body["model"] != "nebius-strong":
            return httpx.Response(500, json={"error": "fixture unavailable"})
        return httpx.Response(200, json=reply(prompt=100, completion=200))

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as upstream:
            app = create_app(store, upstream)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as api:
                response = await api.post(
                    "/v1/chat/completions",
                    json={
                        "model": "route:strong",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )
                trace_id = response.headers["X-Trace-Id"]
                receipts = await api.post(
                    "/v1/receipts", json={"trace_ids": [trace_id]}
                )
                return response, receipts.json()["receipts"]

    response, receipts = asyncio.run(scenario())
    assert response.status_code == 200
    assert [model for _, model in sent] == [
        "local-strong",
        "google-strong",
        "groq-strong",
        "nebius-strong",
    ]
    assert len(receipts) == 1
    receipt = receipts[0]
    expected = 100 * 0.001 + 200 * 0.002
    assert receipt["trace_id"] == response.headers["X-Trace-Id"]
    assert (receipt["provider"], receipt["model"]) == ("nebius", "nebius-strong")
    assert receipt["cost_usd"] == pytest.approx(expected)
    assert receipt["cost_complete"]
    assert receipt["http_status"] == 200
    assert receipt["billing_status"] == "complete"
    # The three failed attempts reported no usage, so totals stay unknown.
    assert (receipt["known_prompt_tokens"], receipt["known_completion_tokens"]) == (
        100,
        200,
    )
    assert not receipt["usage_complete"]
    assert receipt["prompt_tokens"] is None
    trace = store.trace(receipt["trace_id"])
    assert [(a["provider"], a["model"]) for a in trace["attempts"] if a["called"]] == [
        ("ollama", "local-strong"),
        ("google", "google-strong"),
        ("groq", "groq-strong"),
        ("nebius", "nebius-strong"),
    ]


def test_strong_route_replays_free_rate_limit_when_local_unavailable(
    store, monkeypatch
):
    config = setup(store, monkeypatch, 3)
    for provider, name, free in zip(
        config, ["nebius", "nvidia", "openrouter"], [False, True, True]
    ):
        old = provider["id"]
        provider["id"] = name
        provider["strong_model"] = f"{name}-strong"
        model = next(m for m in store.models() if m["provider"] == old)
        model.update(
            provider=name,
            id=f"{name}-strong",
            free=free,
            input_price=0 if free else 0.001,
            output_price=0 if free else 0.002,
        )
        store.replace_models(name, [model])
    store.replace_models(
        "ollama", [{**model, "provider": "ollama", "id": "local-strong"}]
    )
    monkeypatch.setenv("TWT_OLLAMA_STRONG_MODEL", "local-strong")
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "5")
    clock = [100.0]
    sleeps = []
    sent = []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def handler(request):
        if request.url.path == "/api/status":
            raise httpx.ConnectError("ollama down", request=request)
        model = json.loads(request.content)["model"]
        sent.append(model)
        if model == "nvidia-strong" and sent.count(model) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={})
        if model == "nvidia-strong":
            return httpx.Response(200, json=reply())
        return httpx.Response(429, headers={"Retry-After": "1"}, json={})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, config, clock=lambda: clock[0], sleep=sleep
            )
            return await gateway.complete(
                {
                    "model": "route:strong",
                    "messages": [{"role": "user", "content": "hello"}],
                }
            )

    _, status, headers = asyncio.run(scenario())
    assert status == 200
    assert headers["X-Provider-Used"] == "nvidia"
    assert sent.count("nvidia-strong") == 2
    assert sleeps == [1]
