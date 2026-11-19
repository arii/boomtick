import asyncio
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from twt.catalog import providers
from twt.gateway import Gateway, create_app, retry_seconds


REQUEST = {"model": "default", "messages": [{"role": "user", "content": "hello"}], "stream": True}


def reply(prompt=10, completion=20, reasoning=0, finish="stop", tool=None):
    message = {"role": "assistant", "content": "answer"}
    if tool:
        message["tool_calls"] = [{"id": "call_1", "type": "function", "function": tool}]
    return {"id": "test", "choices": [{"message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                      "completion_tokens_details": {"reasoning_tokens": reasoning}}}


def setup(store, monkeypatch, count=2):
    configuration = []
    for i in range(count):
        p = {"id": f"p{i}", "base_url": f"https://p{i}.test/v1", "key_env": f"TEST_KEY_{i}",
             "strict": True, "trains_on_free_tier": False}
        configuration.append(p)
        monkeypatch.setenv(p["key_env"], "test-only-placeholder")
        store.replace_models(p["id"], [{"id": "chat", "provider": p["id"], "chat": True,
                             "free": False, "tools": True, "json": True, "json_schema": True,
                             "input_price": .001, "output_price": .002, "context_length": 100000,
                             "rpm": 30, "daily": None}])
    return configuration


def run(store, configuration, handler, body=None, privacy="standard", session=None):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Gateway(store, client, configuration).complete(body or REQUEST, privacy, session)
    return asyncio.run(scenario())


@pytest.mark.parametrize("failure", [429, 500, 503, "timeout", "connection"])
def test_failover(store, monkeypatch, failure):
    configuration = setup(store, monkeypatch)
    sent = []

    def handler(request):
        sent.append(request)
        assert json.loads(request.content)["stream"] is False
        if request.url.host == "p0.test":
            if failure == "timeout":
                raise httpx.ReadTimeout("test", request=request)
            if failure == "connection":
                raise httpx.ConnectError("test", request=request)
            return httpx.Response(failure, json={"error": "test"})
        return httpx.Response(200, json=reply())

    payload, status, headers = run(store, configuration, handler)
    assert status == 200 and payload["choices"]
    assert len(sent) == 2
    assert headers["X-Provider-Used"] == "p1"
    assert headers["X-Cost-Usd"] == "unknown"
    assert headers["X-Audit-Flags"] == "FALLBACK_CASCADE"
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["known_cost_usd"] == pytest.approx(.05)
    assert trace["cost_complete"] is False
    assert trace["attempts"][0]["called"]
    assert trace["attempts"][1]["response"] == payload
    assert trace["request"]["stream"] is True
    assert trace["attempts"][1]["request"]["stream"] is False
    assert trace["prompt_tokens"] == 10 and trace["completion_tokens"] == 20
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 2
    assert "test-only-placeholder" not in json.dumps(trace)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_non_retryable_error(store, monkeypatch, status):
    configuration = setup(store, monkeypatch)
    _, actual, headers = run(store, configuration, lambda r: httpx.Response(status, json={"error": "bad"}))
    assert actual == status
    assert len(store.trace(headers["X-Trace-Id"])["attempts"]) == 1


def test_rpm_window_and_cooldown(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    models = store.models()
    models[0]["rpm"] = 1
    store.replace_models("p0", [models[0]])
    clock = [100.0]
    sent = []

    def handler(request):
        sent.append(request.url.host)
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock[0])
            await gateway.complete(REQUEST)
            _, _, h = await gateway.complete(REQUEST)
            assert store.trace(h["X-Trace-Id"])["attempts"][0]["reason"] == "local RPM limit"
            clock[0] = 160
            await gateway.complete(REQUEST)
    asyncio.run(scenario())
    assert sent == ["p0.test", "p1.test", "p0.test"]


def test_retry_after_precheck(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    clock = [100.0]
    sent = []

    def handler(request):
        sent.append(request.url.host)
        return httpx.Response(429, headers={"Retry-After": "120"}, json={}) if request.url.host == "p0.test" else httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock[0])
            await gateway.complete(REQUEST)
            clock[0] = 170
            _, _, h = await gateway.complete(REQUEST)
            assert store.trace(h["X-Trace-Id"])["attempts"][0]["reason"] == "Retry-After cooldown"
            clock[0] = 221
            await gateway.complete(REQUEST)
    asyncio.run(scenario())
    assert sent == ["p0.test", "p1.test", "p1.test", "p0.test", "p1.test"]


def test_retry_after_values():
    assert retry_seconds(None) == 60
    assert retry_seconds("nonsense") == 60
    assert retry_seconds("-2") == 0
    assert retry_seconds("inf") == 60
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=90), usegmt=True)
    assert 88 < retry_seconds(future) <= 90


@pytest.mark.parametrize("mode", ["privacy", "trains", "tools", "json", "json_schema", "chat", "model"])
def test_filters(store, monkeypatch, mode):
    configuration = setup(store, monkeypatch)
    body = dict(REQUEST)
    privacy = "standard"
    model = store.models()[0]
    if mode == "privacy":
        configuration[0]["strict"] = False
        privacy = "strict"
    elif mode == "trains":
        configuration[0]["trains_on_free_tier"] = True
        privacy = "strict"
    elif mode == "model":
        model["id"] = "other"
        body["model"] = "chat"
    elif mode == "tools":
        model["tools"] = False
        body["tools"] = [{"type": "function", "function": {"name": "search"}}]
    elif mode in ("json", "json_schema"):
        model[mode] = False
        body["response_format"] = {"type": "json_schema" if mode == "json_schema" else "json_object"}
    else:
        model["chat"] = False
    store.replace_models("p0", [model])
    called = []

    def handler(request):
        called.append(request.url.host)
        return httpx.Response(200, json=reply())
    _, status, headers = run(store, configuration, handler, body, privacy)
    assert status == 200 and called == ["p1.test"]
    assert "FALLBACK_CASCADE" not in headers["X-Audit-Flags"]


def test_missing_credentials_empty_catalog(store):
    def forbidden(request):
        pytest.fail("must not make an upstream call without credentials")
    payload, status, headers = run(store, providers(), forbidden)
    assert status == 503
    for provider in providers():
        assert provider["key_env"] in payload["error"]["message"]
    assert "CLOUDFLARE_ACCOUNT_ID" in payload["error"]["message"]
    assert len(store.trace(headers["X-Trace-Id"])["attempts"]) == 8


@pytest.mark.parametrize("prompt,completion,reasoning,finish,expected", [
    (10, 20, 0, "stop", []),
    (10, 100, 76, "stop", ["EXCESSIVE_REASONING"]),
    (10, 100, 75, "stop", []),
    (32001, 20, 0, "stop", ["CONTEXT_BLOAT"]),
    (32000, 20, 0, "stop", []),
    (10, 20, 0, "length", ["TRUNCATED_MAX_TOKENS"]),
])
def test_audit_thresholds(store, monkeypatch, prompt, completion, reasoning, finish, expected):
    configuration = setup(store, monkeypatch, 1)
    payload = reply(prompt, completion, reasoning, finish)
    _, _, headers = run(store, configuration, lambda r: httpx.Response(200, json=payload))
    assert store.trace(headers["X-Trace-Id"])["flags"] == expected


def test_context_window(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    model = store.models()[0]
    model["context_length"] = 100
    store.replace_models("p0", [model])
    _, _, headers = run(store, configuration, lambda r: httpx.Response(200, json=reply(prompt=81)))
    assert headers["X-Audit-Flags"] == "CONTEXT_BLOAT"


def test_tool_loop_session_and_canonical_arguments(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)

    def call(session, arguments):
        payload = reply(tool={"name": "search", "arguments": arguments})
        return run(store, configuration, lambda r: httpx.Response(200, json=payload), session=session)[2]
    assert call("a", '{"a":1,"b":2}')["X-Audit-Flags"] == ""
    assert call("a", '{"b": 2, "a": 1}')["X-Audit-Flags"] == "TOOL_CALL_LOOP"
    assert call("b", '{"a":1,"b":2}')["X-Audit-Flags"] == ""
    assert call(None, '{"a":1}')["X-Audit-Flags"] == ""
    assert call(None, '{"a":1}')["X-Audit-Flags"] == ""


def test_budget_reached_free_fallback_and_unknown_price(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    run(store, configuration, lambda r: httpx.Response(200, json=reply()))
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "0.05")
    models = store.models()
    models[1].update(free=True, input_price=0, output_price=0)
    store.replace_models("p1", [models[1]])
    _, status, h = run(store, configuration, lambda r: httpx.Response(200, json=reply()))
    assert status == 200 and h["X-Provider-Used"] == "p1"
    assert "budget" in store.trace(h["X-Trace-Id"])["attempts"][0]["reason"]
    store.replace_models("p1", [])
    payload, status, _ = run(store, configuration, lambda r: pytest.fail("budget must skip"))
    assert status == 503 and "budget" in payload["error"]["message"]
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "100")
    models[0]["input_price"] = None
    store.replace_models("p0", [models[0]])
    assert run(store, configuration, lambda r: pytest.fail("unknown price"))[1] == 503


@pytest.mark.parametrize("budget", ["bad", "-1", "nan", "inf"])
def test_invalid_budget(store, monkeypatch, budget):
    configuration = setup(store, monkeypatch)
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", budget)
    _, status, h = run(store, configuration, lambda r: pytest.fail("invalid config"))
    assert status == 500 and store.trace(h["X-Trace-Id"])


@pytest.mark.parametrize("invalid", [False, True])
def test_exhausted_upstreams_and_invalid_responses(store, monkeypatch, invalid):
    configuration = setup(store, monkeypatch)
    _, status, h = run(store, configuration, lambda r: httpx.Response(200 if invalid else 500, json={}))
    assert status == 502
    assert len(store.trace(h["X-Trace-Id"])["attempts"]) == 2


def test_unknown_cost_not_zero(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    model = store.models()[0]
    model["input_price"] = None
    store.replace_models("p0", [model])
    _, _, h = run(store, configuration, lambda r: httpx.Response(200, json=reply()))
    assert h["X-Cost-Usd"] == "unknown"


def test_omitted_usage_is_unknown(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    payload = reply()
    del payload["usage"]
    _, status, h = run(store, configuration, lambda r: httpx.Response(200, json=payload))
    assert status == 200 and h["X-Cost-Usd"] == "unknown"
    assert store.trace(h["X-Trace-Id"])["prompt_tokens"] is None


def test_default_requires_verified_free_eligibility(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    configuration[0]["free_only"] = True
    assert run(store, configuration, lambda r: pytest.fail("not free"))[1] == 503
    explicit = {**REQUEST, "model": "p0/chat"}
    assert run(store, configuration, lambda r: httpx.Response(200, json=reply()), explicit)[1] == 200


@pytest.mark.parametrize("payload", [[], {"choices": None}, {"choices": [None]}])
def test_malformed_error_payloads_are_traced(store, monkeypatch, payload):
    configuration = setup(store, monkeypatch, 1)
    _, status, h = run(store, configuration, lambda r: httpx.Response(400, json=payload))
    assert status == 400 and store.trace(h["X-Trace-Id"])


def test_api_validation_and_models(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply()))) as upstream:
            app = create_app(store, upstream, configuration)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
                listing = await api.get("/v1/models")
                assert listing.json()["data"][0]["id"] == "p0/chat"
                for body in [[], {}, {"messages": []}, {"messages": [1], "response_format": []}]:
                    assert (await api.post("/v1/chat/completions", json=body)).status_code == 400
                assert (await api.post("/v1/chat/completions", content="invalid", headers={"Content-Type": "application/json"})).status_code == 400
                assert (await api.post("/v1/chat/completions", json=REQUEST, headers={"X-Privacy": "typo"})).status_code == 400
                response = await api.post("/v1/chat/completions", json=REQUEST, headers={"X-Privacy": "strict"})
                assert response.status_code == 200 and response.headers["X-Trace-Id"]
    asyncio.run(scenario())
