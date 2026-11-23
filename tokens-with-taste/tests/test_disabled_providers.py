import asyncio

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup
from twt.catalog import (
    OPENROUTER_URL,
    PRICE_URL,
    catalog_models,
    disabled_providers,
    sync,
)
from twt.gateway import Gateway, create_app


def configure(store, monkeypatch):
    config = setup(store, monkeypatch)
    old = store.models()
    for index, name in enumerate(("mistral", "groq")):
        config[index]["id"] = name
        store.replace_models(
            name,
            [
                {
                    **old[index],
                    "provider": name,
                    "free": True,
                    "input_price": 0,
                    "output_price": 0,
                }
            ],
        )
    monkeypatch.setenv("TWT_DISABLED_PROVIDERS", " MISTRAL, mistral, ")
    return config


@pytest.mark.parametrize("selection", ["default", "mistral/chat", "pinned"])
def test_exclusion_beats_stale_key_cached_model_and_explicit_selection(
    store, monkeypatch, selection
):
    config = configure(store, monkeypatch)
    sent = []

    def handler(request):
        sent.append(request.url.host)
        assert request.url.host != "p0.test"
        return httpx.Response(200, json=reply())

    body = {**REQUEST, "model": selection}
    if selection == "pinned":
        body = {**REQUEST, "provider_models": {"mistral": "chat"}}
    _, status, headers = run(store, config, handler, body=body)
    assert sent == (["p1.test"] if selection in ("default", "pinned") else [])
    assert status == (200 if selection in ("default", "pinned") else 503)
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["attempts"][0]["reason"] == "disabled by account policy"
    assert trace["attempts"][0]["called"] is False
    assert any(
        m["provider"] == "mistral" for m in store.models()
    )  # No destructive cache edit.
    assert all(m["provider"] != "mistral" for m in catalog_models(store, config))


def test_sync_does_not_contact_disabled_provider_even_with_key(store, monkeypatch):
    config = configure(store, monkeypatch)
    for p in config:
        p["map_prefix"] = p["id"]
    sent = []

    def handler(request):
        sent.append(str(request.url))
        assert request.url.host != "p0.test"
        return httpx.Response(
            200, json={} if str(request.url) == PRICE_URL else {"data": []}
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client, config)

    messages = asyncio.run(scenario())
    assert "mistral: DISABLED by account policy" in messages
    assert len(sent) == 3  # Two public metadata sources, then Groq listing.
    assert OPENROUTER_URL in sent


def test_models_endpoint_hides_disabled_cached_provider(store, monkeypatch):
    config = configure(store, monkeypatch)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: pytest.fail("no upstream"))
        ) as upstream:
            app = create_app(store, upstream, config)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://local.test"
            ) as client:
                return (await client.get("/v1/models")).json()

    assert not any(m["owned_by"] == "mistral" for m in asyncio.run(scenario())["data"])


def test_unknown_exclusion_fails_closed(store, monkeypatch):
    monkeypatch.setenv("TWT_DISABLED_PROVIDERS", "mistrall")
    with pytest.raises(ValueError, match="Unknown TWT_DISABLED_PROVIDERS"):
        disabled_providers()
    with pytest.raises(ValueError, match="Unknown TWT_DISABLED_PROVIDERS"):
        Gateway(store, None)
