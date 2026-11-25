import asyncio

import httpx
import pytest
from test_gateway import REQUEST
from twt.catalog import (
    OPENROUTER_URL,
    PRICE_URL,
    _all_providers,
    configured_providers,
    disabled_providers,
    providers,
    sync,
)
from twt.gateway import Gateway

RUNWARE_IDS = {"zai:glm@5.3-flash", "moonshotai:kimi@k3", "deepseek:v4@flash"}


def runware():
    return next(p for p in _all_providers() if p["id"] == "runware")


def public_catalogs(request):
    if str(request.url) == PRICE_URL:
        return httpx.Response(200, json={})
    if str(request.url) == OPENROUTER_URL:
        return httpx.Response(200, json={"data": []})
    return None


def run_sync(store, handler):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client)

    return asyncio.run(scenario())


def test_runware_is_off_unless_explicitly_enabled(monkeypatch):
    assert runware()["default_disabled"] is True
    assert "runware" not in {p["id"] for p in providers()}
    assert "runware" not in {p["id"] for p in configured_providers()}
    monkeypatch.setenv("TWT_ENABLED_PROVIDERS", "runware")
    assert "runware" in {p["id"] for p in providers()}


def test_enable_list_fails_closed_on_unknown_ids(monkeypatch):
    monkeypatch.setenv("TWT_ENABLED_PROVIDERS", "runwar")
    with pytest.raises(ValueError, match="Unknown TWT_ENABLED_PROVIDERS"):
        providers()


def test_runware_can_be_named_in_the_disabled_list_while_off(monkeypatch):
    monkeypatch.setenv("TWT_DISABLED_PROVIDERS", "runware")
    assert disabled_providers() == {"runware"}


def test_default_sync_never_contacts_runware(store, monkeypatch):
    monkeypatch.setenv("RUNWARE_API_KEY", "test-only-placeholder")
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        assert request.url.host != "api.runware.ai"
        return public_catalogs(request) or httpx.Response(200, json={"data": []})

    messages = run_sync(store, handler)
    assert "api.runware.ai" not in hosts
    assert not any(m.startswith("runware") for m in messages)
    assert not [m for m in store.models() if m["provider"] == "runware"]


def test_enabled_runware_lists_documented_ids_without_a_request(store, monkeypatch):
    monkeypatch.setenv("TWT_ENABLED_PROVIDERS", "runware")
    monkeypatch.setenv("RUNWARE_API_KEY", "test-only-placeholder")

    def handler(request):
        assert request.url.host != "api.runware.ai", "model listing is not verified"
        return public_catalogs(request) or httpx.Response(200, json={"data": []})

    run_sync(store, handler)
    models = [m for m in store.models() if m["provider"] == "runware"]
    assert {m["id"] for m in models} == RUNWARE_IDS
    # No verified Runware prices yet: paid, unpriced, so cost bounds stay unknown.
    assert all(
        m["input_price"] is None and m["output_price"] is None and not m["free"]
        for m in models
    )
    assert all(m["chat"] and not m["tools"] for m in models)


def test_unpriced_runware_is_never_dispatched_under_a_cost_ceiling(store, monkeypatch):
    monkeypatch.setenv("TWT_ENABLED_PROVIDERS", "runware")
    monkeypatch.setenv("RUNWARE_API_KEY", "test-only-placeholder")
    run_sync(
        store,
        lambda r: public_catalogs(r) or httpx.Response(200, json={"data": []}),
    )

    def forbidden(request):
        pytest.fail(f"unexpected upstream call to {request.url.host}")

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(forbidden)
        ) as client:
            return await Gateway(store, client, [runware()]).complete(
                {**REQUEST, "max_tokens": 100}, max_cost=1.0
            )

    _, status, headers = asyncio.run(scenario())
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 503
    assert not any(a["called"] for a in trace["attempts"])
    assert "cannot be bounded" in trace["attempts"][0]["reason"]
