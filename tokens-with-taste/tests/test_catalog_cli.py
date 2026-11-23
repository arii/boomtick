import asyncio
import json

import httpx
import pytest
from test_gateway import reply, run, setup
from twt.catalog import OPENROUTER_URL, PRICE_URL, normalize, providers, sync
from twt.cli import main


def test_provider_policy():
    configuration = providers()
    assert [p["id"] for p in configuration] == [
        "google",
        "groq",
        "nvidia",
        "mistral",
        "openrouter",
        "sambanova",
        "cloudflare",
        "nebius",
    ]
    assert [p["id"] for p in configuration if p["strict"]] == ["groq", "cloudflare"]
    assert configuration[-1]["base_url"] == "https://api.tokenfactory.nebius.com/v1"
    assert all(
        p["verified"]["endpoint"]["checked"] == "2026-11-16" for p in configuration
    )
    assert configuration[0].get("rpm") is None
    assert configuration[-1]["models"] == {}


def test_normalize_free_does_not_mean_chat_or_tools():
    provider = next(p for p in providers() if p["id"] == "openrouter")
    row = {
        "id": "image:free",
        "pricing": {"prompt": "0", "completion": "0"},
        "architecture": {"output_modalities": ["image"]},
        "supported_parameters": [],
    }
    normalized = normalize(provider, row, {}, {})
    assert normalized["free"] and not normalized["chat"] and not normalized["tools"]
    assert normalized["rpm"] == 20
    row["id"] = "zero-priced"
    row["architecture"]["output_modalities"] = ["text"]
    row["supported_parameters"] = ["tools", "response_format", "structured_outputs"]
    normalized = normalize(provider, row, {}, {})
    assert (
        normalized["tools"]
        and normalized["json"]
        and normalized["json_schema"]
        and normalized["chat"]
    )
    assert normalized["rpm"] is None


def test_metadata_exact_match_and_unknowns():
    provider = {
        "id": "test",
        "base_url": "https://example.test/v1",
        "map_prefix": "test",
    }
    metadata = {
        "test/known": {
            "mode": "chat",
            "supports_function_calling": True,
            "supports_response_schema": True,
            "input_cost_per_token": 0.01,
            "output_cost_per_token": 0.02,
            "max_input_tokens": 100,
        }
    }
    known = normalize(provider, {"id": "known"}, metadata, {})
    assert known["tools"] and known["json"] and known["input_price"] == 0.01
    unknown = normalize(provider, {"id": "unknown"}, metadata, {})
    assert (
        unknown["input_price"] is None
        and unknown["rpm"] is None
        and not unknown["chat"]
    )
    explicit = normalize(
        provider, {"id": "known"}, metadata, {"known": {"supported_parameters": []}}
    )
    assert not explicit["tools"] and not explicit["json"]
    marketplace = {"known": {"pricing": {"prompt": "99", "completion": "99"}}}
    assert (
        normalize(provider, {"id": "known"}, metadata, marketplace)["input_price"]
        == 0.01
    )
    assert normalize(provider, {"id": "known"}, {}, marketplace)["input_price"] is None


def test_sync_public_and_skipped_providers(store):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        assert "Authorization" not in request.headers
        if str(request.url) == PRICE_URL:
            return httpx.Response(200, json={"nvidia_nim/chat": {"mode": "chat"}})
        if str(request.url) == OPENROUTER_URL:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "a:free",
                            "pricing": {"prompt": "0", "completion": "0"},
                            "supported_parameters": ["tools"],
                            "architecture": {"output_modalities": ["text"]},
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"data": [{"id": "chat"}]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client)

    messages = asyncio.run(scenario())
    assert len(requests) == 4
    assert len(store.models()) == 3
    for key in (
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "NEBIUS_API_KEY",
        "CLOUDFLARE_API_TOKEN",
    ):
        assert key in "\n".join(messages)
    assert "nvidia: inference SKIPPED missing NVIDIA_API_KEY" in messages


def test_google_sync_normalizes_listed_ids_for_tool_routing(store, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-token")
    google = next(provider for provider in providers() if provider["id"] == "google")
    model = "gemini-3.1-flash-lite"
    upstream = []

    def handler(request):
        if str(request.url) == PRICE_URL:
            return httpx.Response(
                200,
                json={
                    f"gemini/{model}": {
                        "mode": "chat",
                        "supports_function_calling": True,
                        "supports_response_schema": True,
                    }
                },
            )
        if str(request.url) == OPENROUTER_URL:
            return httpx.Response(200, json={"data": []})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": f"models/{model}"}]})
        upstream.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client, [google])

    assert "google: synced 1 models" in asyncio.run(scenario())
    (synced,) = store.models()
    assert synced["id"] == model
    assert (
        synced["free"] and synced["chat"] and synced["tools"] and synced["json_schema"]
    )
    _, status, headers = run(
        store,
        [google],
        handler,
        body={
            "model": "route:default",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
            "response_format": {"type": "json_schema"},
        },
    )
    assert status == 200 and headers["X-Provider-Used"] == "google"
    assert upstream == [model]


def test_cloudflare_static_models_sync(store, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "mock-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "mock-account")
    retired = "@cf/meta/llama-3.1-8b-instruct"
    store.replace_models("cloudflare", [{"id": retired, "provider": "cloudflare"}])

    def handler(request):
        if str(request.url) == PRICE_URL:
            return httpx.Response(200, json={})
        if str(request.url) == OPENROUTER_URL:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": []})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client)

    messages = asyncio.run(scenario())
    assert "cloudflare: synced 3 models" in messages
    cf_models = [m for m in store.models() if m["provider"] == "cloudflare"]
    assert len(cf_models) == 3
    assert retired not in {model["id"] for model in cf_models}
    assert "@cf/meta/llama-3.2-1b-instruct" not in {m["id"] for m in cf_models}
    assert all(
        m["free"] and m["chat"] and m["context_length"] == 8192 for m in cf_models
    )


def test_sync_keeps_410_retired_static_model_out_across_syncs(store, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "mock-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "mock-account")
    retired = "@cf/meta/llama-3.2-3b-instruct"

    def handler(request):
        if str(request.url) == PRICE_URL:
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"data": []})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await sync(store, client)
            store.retire_model("cloudflare", retired)
            return [await sync(store, client), await sync(store, client)]

    messages = asyncio.run(scenario())
    assert all("cloudflare: synced 2 models" in m for m in messages)
    ids = {m["id"] for m in store.models() if m["provider"] == "cloudflare"}
    assert retired not in ids and len(ids) == 2


def test_sync_reinstates_retired_model_only_when_provider_lists_it(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    configuration[0]["map_prefix"] = "p0"
    store.retire_model("p0", "m-old")
    listed = [{"id": "m-new"}]

    def handler(request):
        if str(request.url) == PRICE_URL:
            return httpx.Response(200, json={})
        if str(request.url) == OPENROUTER_URL:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": listed})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await sync(store, client, configuration)
            first = {m["id"] for m in store.models() if m["provider"] == "p0"}
            listed.append({"id": "m-old"})
            await sync(store, client, configuration)
            return first

    first = asyncio.run(scenario())
    assert first == {"m-new"}
    assert {m["id"] for m in store.models() if m["provider"] == "p0"} == {
        "m-new",
        "m-old",
    }


def test_sync_failure_retains_catalog_and_empty_list_clears(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    configuration[0]["map_prefix"] = "p0"

    async def scenario(status, data):
        def handler(request):
            if str(request.url) == PRICE_URL:
                return httpx.Response(200, json={})
            if str(request.url) == OPENROUTER_URL:
                return httpx.Response(200, json={"data": []})
            return httpx.Response(status, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await sync(store, client, configuration)

    assert "FAILED" in "".join(asyncio.run(scenario(500, {})))
    assert len(store.models()) == 1
    assert "FAILED" in "".join(asyncio.run(scenario(200, {"data": [None]})))
    assert len(store.models()) == 1
    asyncio.run(scenario(200, {"data": []}))
    assert store.models() == []


def test_cli_empty_error_and_since(store, capsys):
    db = str(store.path)
    main(["--db", db, "models", "--free", "--tools"])
    assert "0 models" in capsys.readouterr().out
    main(["--db", db, "audit", "--flagged"])
    assert capsys.readouterr().out == ""
    main(["--db", db, "report", "--since", "2026-01-01"])
    assert json.loads(capsys.readouterr().out)["groups"] == []
    with pytest.raises(SystemExit, match="1"):
        main(["--db", db, "inspect", "absent"])
    assert "Trace not found" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="2"):
        main(["--db", db, "report", "--since", "bad"])


def test_cli_report_inspect_flagged_and_models(store, monkeypatch, capsys):
    configuration = setup(store, monkeypatch)

    def handler(request):
        if request.url.host == "p0.test":
            return httpx.Response(500, json={"error": "test"})
        return httpx.Response(
            200,
            json=reply(
                prompt=33000,
                completion=100,
                reasoning=80,
                finish="length",
                tool={"name": "search", "arguments": '{"q": "x"}'},
            ),
        )

    run(store, configuration, handler, session="s")
    _, _, h = run(store, configuration, handler, session="s")
    db = str(store.path)
    main(["--db", db, "inspect", h["X-Trace-Id"]])
    text = capsys.readouterr().out
    for expected in (
        "# Trace",
        "## Prompt",
        "## Waterfall",
        "reasoning=80",
        "TOOL_CALL_LOOP",
        "upstream HTTP 500",
    ):
        assert expected in text
    main(["--db", db, "audit", "--flagged"])
    assert len(capsys.readouterr().out.strip().splitlines()) == 2
    main(["--db", db, "report"])
    result = json.loads(capsys.readouterr().out)
    successful = next(g for g in result["groups"] if g["provider"] == "p1")
    assert successful["calls"] == 2
    assert successful["prompt_tokens"] == 66000
    assert successful["spend_usd"] == pytest.approx(66.4)
    assert len(result["fixes"]) == 5 and "p0" in result["fixes"]["FALLBACK_CASCADE"]
    main(["--db", db, "report", "--since", "2999-01-01"])
    assert json.loads(capsys.readouterr().out)["groups"] == []
    model = store.models()[0]
    model["free"] = True
    store.replace_models("p0", [model])
    main(["--db", db, "models", "--free", "--tools"])
    assert "1 models" in capsys.readouterr().out


def test_cli_sync_failure(store, monkeypatch, capsys):
    async def failed(storage):
        raise httpx.ConnectError("DNS resolution failed")

    monkeypatch.setattr("twt.cli.sync", failed)
    with pytest.raises(SystemExit, match="1"):
        main(["--db", str(store.path), "sync"])
    assert (
        "Catalog sync failed (ConnectError: DNS resolution failed)"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-11-20", "2026-11-20T00:00:00+00:00"),
        ("2026-11-20T07:00:00Z", "2026-11-20T07:00:00+00:00"),
        ("2026-11-20T07:00:00-08:00", "2026-11-20T15:00:00+00:00"),
    ],
)
def test_since_date_preserves_utc_semantics(value, expected):
    from twt.cli import since_date

    assert since_date(value) == expected


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("offline"),
        ValueError("invalid catalog"),
        KeyError("data"),
        TypeError("bad row"),
        OSError("disk failed"),
    ],
)
def test_sync_expected_failures_are_reported(store, monkeypatch, capsys, error):
    async def failed(storage):
        raise error

    monkeypatch.setattr("twt.cli.sync", failed)
    with pytest.raises(SystemExit, match="1"):
        main(["--db", str(store.path), "sync"])
    assert "Catalog sync failed" in capsys.readouterr().err
