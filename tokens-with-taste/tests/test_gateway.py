import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from twt.catalog import providers
from twt.gateway import Gateway, create_app, retry_seconds

REQUEST = {
    "model": "default",
    "messages": [{"role": "user", "content": "hello"}],
    "stream": True,
}


def reply(prompt=10, completion=20, reasoning=0, finish="stop", tool=None):
    message = {"role": "assistant", "content": "answer"}
    if tool:
        message["tool_calls"] = [{"id": "call_1", "type": "function", "function": tool}]
    return {
        "id": "test",
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "completion_tokens_details": {"reasoning_tokens": reasoning},
        },
    }


def setup(store, monkeypatch, count=2, provider_ids=None):
    configuration = []
    for i in range(count):
        provider_id = provider_ids[i] if provider_ids else f"p{i}"
        p = {
            "id": provider_id,
            "base_url": f"https://{provider_id}.test/v1",
            "key_env": f"TEST_KEY_{i}",
            "strict": True,
            "trains_on_free_tier": False,
        }
        configuration.append(p)
        monkeypatch.setenv(p["key_env"], "test-only-placeholder")
        store.replace_models(
            p["id"],
            [
                {
                    "id": "chat",
                    "provider": p["id"],
                    "chat": True,
                    "free": False,
                    "tools": True,
                    "json": True,
                    "json_schema": True,
                    "input_price": 0.001,
                    "output_price": 0.002,
                    "context_length": 100000,
                    "rpm": 30,
                    "daily": None,
                }
            ],
        )
    return configuration


def run(store, configuration, handler, body=None, privacy="standard", session=None):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Gateway(store, client, configuration).complete(
                body or REQUEST, privacy, session
            )

    return asyncio.run(scenario())


def tool_history(response):
    message = {"role": "assistant", **response["choices"][0]["message"]}
    results = [
        {"role": "tool", "tool_call_id": call["id"], "content": "found"}
        for call in message["tool_calls"]
    ]
    return [*REQUEST["messages"], message, *results]


CONVERTED_CALL = "[tool call call_1: lookup({})]"
CONVERSION = {
    "assistant_turns": 1,
    "tool_results": 1,
    "reason": "unsigned tool calls from other providers sent to Google as text",
}


def assert_text_only(messages):
    assert messages[1] == {
        "role": "assistant",
        "content": "answer\n" + CONVERTED_CALL,
    }
    assert messages[2] == {"role": "user", "content": "[tool result call_1]: found"}


def test_google_converts_unsigned_tool_history_from_groq(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    tool_reply = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    sent = []

    def handler(request):
        sent.append((request.url.host, json.loads(request.content)["messages"]))
        if len(sent) == 1:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json=tool_reply if len(sent) == 2 else reply())

    first, status, headers = run(store, configuration, handler, session="spec")
    assert status == 200 and headers["X-Provider-Used"] == "groq"
    history = tool_history(first)
    original = json.loads(json.dumps(history))
    body = {**REQUEST, "messages": history}
    _, status, headers = run(store, configuration, handler, body, session="spec")
    assert status == 200 and headers["X-Provider-Used"] == "google"
    assert [host for host, _ in sent] == ["google.test", "groq.test", "google.test"]
    assert_text_only(sent[2][1])
    assert history == original
    google = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert google["called"] and google["reason"] == "success"
    assert google["tool_history_conversion"] == CONVERSION


def test_google_mixed_tool_history_keeps_signed_turn_structured(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    signed = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    signed_call = signed["choices"][0]["message"]["tool_calls"][0]
    signed_call["extra_content"] = {"google": {"thought_signature": "native"}}
    foreign = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    foreign["choices"][0]["message"]["tool_calls"][0]["id"] = "call_9"
    signed_turn = tool_history(signed)
    foreign_turn = tool_history(foreign)[1:]
    foreign_turn[1]["content"] = "other"
    messages = [*signed_turn, *foreign_turn, {"role": "user", "content": "next"}]
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store, configuration, handler, {**REQUEST, "messages": messages}
    )
    assert status == 200 and headers["X-Provider-Used"] == "google"
    sent = seen[0]
    assert sent[1]["tool_calls"] == [signed_call]
    assert sent[2] == {"role": "tool", "tool_call_id": "call_1", "content": "found"}
    assert sent[3] == {
        "role": "assistant",
        "content": "answer\n[tool call call_9: lookup({})]",
    }
    assert sent[4] == {"role": "user", "content": "[tool result call_9]: other"}
    assert sent[5] == messages[-1]
    google = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert google["tool_history_conversion"] == CONVERSION


def test_google_signed_history_records_no_conversion(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    signed = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    signed["choices"][0]["message"]["tool_calls"][0]["extra_content"] = {
        "google": {"thought_signature": "native"}
    }
    _, _, headers = run(
        store,
        configuration,
        lambda request: httpx.Response(200, json=reply()),
        {**REQUEST, "messages": tool_history(signed)},
    )
    google = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert "tool_history_conversion" not in google


def test_other_provider_gets_original_history_after_google_fails(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    tool_reply = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    history = tool_history(tool_reply)
    seen = {}

    def handler(request):
        seen[request.url.host] = json.loads(request.content)["messages"]
        if request.url.host == "google.test":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store, configuration, handler, {**REQUEST, "messages": history}
    )
    assert status == 200 and headers["X-Provider-Used"] == "groq"
    assert_text_only(seen["google.test"])
    assert seen["groq.test"] == history
    assert seen["groq.test"][1]["tool_calls"] and seen["groq.test"][2]["role"] == "tool"
    google, groq = store.trace(headers["X-Trace-Id"])["attempts"]
    assert google["tool_history_conversion"] == CONVERSION
    assert "tool_history_conversion" not in groq


@pytest.mark.parametrize("client_preserves_signature", [True, False])
def test_google_reuses_its_tool_signature(
    store, monkeypatch, client_preserves_signature
):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    tool_reply = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    calls = tool_reply["choices"][0]["message"]["tool_calls"]
    extra = {"google": {"thought_signature": "native-signature"}}
    calls[0]["extra_content"] = extra
    calls.append({**calls[0], "id": "call_2"})
    del calls[1]["extra_content"]
    sent = []

    def handler(request):
        sent.append(request.url.host)
        if len(sent) == 1:
            return httpx.Response(200, json=tool_reply)
        history = json.loads(request.content)["messages"]
        if client_preserves_signature or len(sent) == 2:
            assert history[1]["tool_calls"] == calls
            assert [m["tool_call_id"] for m in history[2:]] == ["call_1", "call_2"]
        else:
            assert "tool_calls" not in history[1]
            assert [m["role"] for m in history[2:]] == ["user", "user"]
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            first, status, headers = await gateway.complete(REQUEST, session="spec")
            assert status == 200 and headers["X-Provider-Used"] == "google"
            assert (
                first["choices"][0]["message"]["tool_calls"][0]["extra_content"]
                == extra
            )
            history = tool_history(first)
            if not client_preserves_signature:
                del history[1]["tool_calls"][0]["extra_content"]
            body = {**REQUEST, "messages": history}
            _, status, headers = await gateway.complete(body, session="spec")
            assert status == 200 and headers["X-Provider-Used"] == "google"
            if not client_preserves_signature:
                assert "extra_content" not in body["messages"][1]["tool_calls"][0]
                _, status, headers = await gateway.complete(body, session="other")
                assert status == 200 and headers["X-Provider-Used"] == "google"

    asyncio.run(scenario())
    assert sent == ["google.test"] * (2 if client_preserves_signature else 3)


def test_google_reuses_signature_without_session(store, monkeypatch):
    # X-Session-Id is optional, so clients that send none and drop
    # extra_content must still get Google's own signature restored.
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    tool_reply = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    tool_reply["choices"][0]["message"]["tool_calls"][0]["extra_content"] = {
        "google": {"thought_signature": "native-signature"}
    }
    sent = []

    def handler(request):
        sent.append(request.url.host)
        if len(sent) == 1:
            return httpx.Response(200, json=tool_reply)
        history = json.loads(request.content)["messages"]
        assert history[1]["tool_calls"][0]["extra_content"] == {
            "google": {"thought_signature": "native-signature"}
        }
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            first, status, headers = await gateway.complete(REQUEST)
            assert status == 200 and headers["X-Provider-Used"] == "google"
            history = tool_history(first)
            del history[1]["tool_calls"][0]["extra_content"]
            body = {**REQUEST, "messages": history}
            _, status, headers = await gateway.complete(body)
            assert status == 200 and headers["X-Provider-Used"] == "google"

    asyncio.run(scenario())
    assert sent == ["google.test", "google.test"]


def test_google_sessionless_unsigned_history_is_sent_as_text(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))
    tool_reply = reply(tool={"name": "lookup", "arguments": "{}"}, finish="tool_calls")
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)["messages"])
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store,
        configuration,
        handler,
        {**REQUEST, "messages": tool_history(tool_reply)},
    )
    assert status == 200 and headers["X-Provider-Used"] == "google"
    assert_text_only(seen[0])
    google = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert google["called"] and google["tool_history_conversion"] == CONVERSION


@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"message": "Missing thought_signature"}},
        [
            {
                "error": {
                    "message": "Missing thought_signature",
                    "status": "INVALID_ARGUMENT",
                }
            }
        ],
    ],
)
def test_google_thought_signature_400_falls_through(store, monkeypatch, payload):
    configuration = setup(store, monkeypatch, provider_ids=("google", "groq"))

    def handler(request):
        if request.url.host == "google.test":
            return httpx.Response(400, json=payload)
        return httpx.Response(200, json=reply())

    result, status, headers = run(store, configuration, handler)
    assert status == 200 and result == reply() and headers["X-Provider-Used"] == "groq"
    google, groq = store.trace(headers["X-Trace-Id"])["attempts"]
    assert google["called"] and google["http_status"] == 400
    assert google["reason"] == "upstream Google HTTP 400: thought_signature"
    assert groq["reason"] == "success"


@pytest.mark.parametrize(
    "failure", [402, 404, 410, 429, 500, 503, "timeout", "connection"]
)
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
    assert trace["known_cost_usd"] == pytest.approx(0.05)
    assert trace["cost_complete"] is False
    assert trace["attempts"][0]["called"]
    assert trace["attempts"][1]["response"] == payload
    assert trace["request"]["stream"] is True
    assert trace["attempts"][1]["request"]["stream"] is False
    assert trace["prompt_tokens"] == 10 and trace["completion_tokens"] == 20
    assert store.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 2
    assert "test-only-placeholder" not in json.dumps(trace)


def test_410_retires_model_so_it_stops_routing(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    sent = []
    clock = 1000

    def handler(request):
        sent.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(410, json={"error": {"message": "Model retired"}})
        return httpx.Response(200, json=reply())

    async def scenario():
        nonlocal clock
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock)
            await gateway.complete(REQUEST)
            # Past the in-memory cooldown: only the retirement keeps it out.
            clock += 301
            return await gateway.complete(REQUEST)

    _, status, headers = asyncio.run(scenario())
    assert status == 200 and headers["X-Provider-Used"] == "p1"
    assert sent == ["p0.test", "p1.test", "p1.test"]
    assert "p0" not in {m["provider"] for m in store.models()}
    assert store.retired_models("p0")


@pytest.mark.parametrize("upstream_status", [404])
def test_unavailable_model_is_temporarily_skipped(store, monkeypatch, upstream_status):
    configuration = setup(store, monkeypatch)
    sent = []
    clock = 1000
    error = {"error": {"message": "Model unavailable"}}

    def handler(request):
        sent.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(upstream_status, json=error)
        return httpx.Response(200, json=reply())

    async def scenario():
        nonlocal clock
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock)
            first = await gateway.complete(REQUEST)
            second = await gateway.complete(REQUEST)
            clock += 301
            third = await gateway.complete(REQUEST)
            return first, second, third

    first, second, third = asyncio.run(scenario())
    assert sent == ["p0.test", "p1.test", "p1.test", "p0.test", "p1.test"]
    for _, status, headers in (first, second, third):
        assert status == 200
        assert headers["X-Provider-Used"] == "p1"
    trace = store.trace(first[2]["X-Trace-Id"])
    failed, succeeded = trace["attempts"]
    assert failed["called"] and failed["http_status"] == upstream_status
    assert failed["response"] == error
    assert succeeded["reason"] == "success"
    skipped = store.trace(second[2]["X-Trace-Id"])["attempts"][0]
    assert not skipped["called"]
    assert skipped["reason"] == "model unavailable cooldown"


def two_free_models(store, monkeypatch, overrides=None):
    overrides = overrides or {}
    configuration = setup(store, monkeypatch, count=1)
    store.replace_models(
        "p0",
        [
            {
                "id": model_id,
                "provider": "p0",
                "chat": True,
                "free": True,
                "tools": True,
                "json": True,
                "json_schema": True,
                "input_price": 0,
                "output_price": 0,
                "context_length": 100000,
                "rpm": 30,
                "daily": None,
                **overrides.get(model_id, {}),
            }
            for model_id in ("alpha", "beta")
        ],
    )
    return configuration


def test_provider_falls_back_to_next_model_when_top_model_is_unavailable(
    store, monkeypatch
):
    configuration = two_free_models(store, monkeypatch)
    sent = []

    def handler(request):
        model = json.loads(request.content)["model"]
        sent.append(model)
        if model == "alpha":
            return httpx.Response(404, json={"error": {"message": "gone"}})
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            return await gateway.complete(REQUEST), await gateway.complete(REQUEST)

    _, second = asyncio.run(scenario())
    assert sent == ["alpha", "beta"]
    assert second[1] == 200 and second[2]["X-Provider-Used"] == "p0"


def test_error_names_every_blocked_model(store, monkeypatch):
    configuration = two_free_models(store, monkeypatch)

    def handler(request):
        return httpx.Response(404, json={"error": {"message": "gone"}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            await gateway.complete(REQUEST)
            await gateway.complete(REQUEST)
            return await gateway.complete(REQUEST)

    payload, status, _ = asyncio.run(scenario())
    assert status == 503
    assert (
        "p0: alpha: model unavailable cooldown; beta: model unavailable cooldown"
        in (payload["error"]["message"])
    )


def test_provider_falls_back_past_model_with_small_tpm(store, monkeypatch):
    configuration = two_free_models(store, monkeypatch, {"alpha": {"tpm": 1}})
    sent = []

    def handler(request):
        sent.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=reply())

    _, status, _ = run(store, configuration, handler)
    assert status == 200 and sent == ["beta"]


def test_provider_falls_back_past_model_with_http_413_memory(store, monkeypatch):
    configuration = two_free_models(store, monkeypatch)
    configuration[0]["id"] = "groq"
    store.replace_models("groq", [{**m, "provider": "groq"} for m in store.models()])
    sent = []

    def handler(request):
        model = json.loads(request.content)["model"]
        sent.append(model)
        if model == "alpha":
            return httpx.Response(413, json={"error": {"message": "big"}})
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            await gateway.complete(REQUEST)
            return await gateway.complete(REQUEST)

    _, status, _ = asyncio.run(scenario())
    assert status == 200 and sent[-1] == "beta" and sent.count("alpha") == 1


def test_provider_falls_back_past_overloaded_model(store, monkeypatch):
    configuration = two_free_models(store, monkeypatch)
    sent = []

    def handler(request):
        model = json.loads(request.content)["model"]
        sent.append(model)
        if model == "alpha":
            return httpx.Response(529, json={"error": {"message": "busy"}})
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            await gateway.complete(REQUEST)
            return await gateway.complete(REQUEST)

    _, status, _ = asyncio.run(scenario())
    assert status == 200 and sent.count("alpha") == 1 and sent[-1] == "beta"


def test_fallback_does_not_leave_the_free_class(store, monkeypatch):
    configuration = two_free_models(
        store, monkeypatch, {"beta": {"free": False, "input_price": 0.001}}
    )

    def handler(request):
        return httpx.Response(404, json={"error": {"message": "gone"}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            await gateway.complete(REQUEST)
            return await gateway.complete(REQUEST)

    payload, status, _ = asyncio.run(scenario())
    assert status == 503
    assert "p0 (alpha): model unavailable cooldown" in payload["error"]["message"]


def test_single_blocked_model_message_appends_model_name(store, monkeypatch):
    configuration = two_free_models(store, monkeypatch, {"alpha": {"tpm": 1}})
    configuration[0]["strong_model"] = "alpha"

    def handler(request):
        return httpx.Response(200, json=reply())

    body = {**REQUEST, "model": "route:strong"}
    payload, status, _ = run(store, configuration, handler, body)
    assert status == 503
    assert "p0 (alpha): request too large" in payload["error"]["message"]


def test_model_id_inside_reason_still_gets_named(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=1)
    store.replace_models(
        "p0",
        [{**m, "id": "request", "tpm": 1} for m in store.models()],
    )

    def handler(request):
        return httpx.Response(200, json=reply())

    payload, status, _ = run(store, configuration, handler)
    assert status == 503
    assert "p0 (request): request too large" in payload["error"]["message"]


def test_empty_message_truncated_by_length_names_the_token_budget(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    truncated = {
        **reply(),
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "thinking that used the whole budget",
                },
            }
        ],
    }

    def handler(request):
        return httpx.Response(
            200, json=truncated if request.url.host == "p0.test" else reply()
        )

    payload, status, headers = run(store, configuration, handler)
    assert status == 200 and payload == reply()
    first, second = store.trace(headers["X-Trace-Id"])["attempts"]
    assert first["reason"].startswith(
        "upstream assistant message has no content, tool_calls or function_call"
    )
    assert "finish_reason length" in first["reason"]
    assert "max_tokens" in first["reason"]
    assert second["reason"] == "success"


@pytest.mark.parametrize(
    "prompt,context,cap,budget,finish,expected,recover",
    [
        (3740, 262144, 262144, "5", "length", 16384, True),
        (6863, 262144, 262144, "5", "length", 16384, False),
        (6863, 16863, 12000, "5", "length", 10000, True),
        (3740, 262144, 10000, "5", "length", 10000, True),
        (6863, 15055, 262144, "5", "length", None, False),
        (3740, 262144, 262144, "0.005", "length", None, False),
        (3740, 262144, 262144, "5", "stop", None, False),
    ],
)
def test_nebius_empty_length_retry(
    store, monkeypatch, prompt, context, cap, budget, finish, expected, recover
):
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", budget)
    configuration = setup(store, monkeypatch, count=1, provider_ids=("nebius",))
    model = store.models()[0]
    model.update(
        id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        input_price=0.00000006,
        output_price=0.00000024,
        context_length=context,
        max_output_tokens=cap,
    )
    store.replace_models("nebius", [model])
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        if recover and len(sent) == 2:
            return httpx.Response(
                200, json=reply(tool={"name": "edit", "arguments": "{}"})
            )
        payload = reply(prompt=prompt, completion=sent[-1]["max_tokens"], finish=finish)
        payload["choices"][0]["message"]["content"] = ""
        return httpx.Response(200, json=payload)

    payload, status, headers = run(
        store,
        configuration,
        handler,
        {**REQUEST, "model": "route:strong", "max_tokens": 8192},
    )
    assert [r["max_tokens"] for r in sent] == ([8192, expected] if expected else [8192])
    assert {r["model"] for r in sent} == {model["id"]}
    assert status == (200 if recover else 502)
    if recover:
        assert payload["choices"][0]["message"]["tool_calls"]
    trace = store.trace(headers["X-Trace-Id"])
    called = [a for a in trace["attempts"] if a["called"]]
    assert len(called) == len(sent)
    assert trace["cost_usd"] == pytest.approx(sum(a["cost_usd"] for a in called))
    assert called[0]["cost_usd"] == pytest.approx(
        prompt * 0.00000006 + 8192 * 0.00000024
    )
    if budget == "0.005":
        assert (
            trace["attempts"][-1]["reason"]
            == "daily budget reached or paid model price unknown"
        )


@pytest.mark.parametrize("upstream_status", [200, 400, 403])
def test_payment_required_error_body_falls_through(store, monkeypatch, upstream_status):
    configuration = setup(store, monkeypatch)
    error = {
        "error": {"code": "PAYMENT_METHOD_REQUIRED", "message": "Billing required"}
    }

    def handler(request):
        if request.url.host == "p0.test":
            return httpx.Response(upstream_status, json=error)
        return httpx.Response(200, json=reply())

    payload, status, headers = run(store, configuration, handler)
    assert status == 200 and payload == reply()
    failed, succeeded = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["called"] and failed["http_status"] == upstream_status
    assert failed["response"] == error
    assert "payment required" in failed["reason"]
    assert succeeded["provider"] == "p1" and succeeded["reason"] == "success"


@pytest.mark.parametrize(
    "choices",
    [
        [],
        [{"message": {}}],
        [{"message": {"role": "assistant"}}],
        [{"message": {"role": "assistant", "content": None, "tool_calls": []}}],
        [{"message": {"role": "assistant", "content": ""}}],
        [{"message": {"role": "assistant", "content": " \n"}}],
        [{"message": {"role": "assistant", "content": 42, "tool_calls": {}}}],
        [{"message": {"role": "assistant", "content": None, "function_call": {}}}],
    ],
)
@pytest.mark.parametrize("later_succeeds", [True, False])
def test_empty_assistant_response_falls_through(
    store, monkeypatch, choices, later_succeeds
):
    configuration = setup(store, monkeypatch)
    invalid = {**reply(), "choices": choices}
    sent = []

    def handler(request):
        sent.append(request.url.host)
        valid = request.url.host == "p1.test" and later_succeeds
        return httpx.Response(200, json=reply() if valid else invalid)

    payload, status, headers = run(store, configuration, handler)
    assert sent == ["p0.test", "p1.test"]
    trace = store.trace(headers["X-Trace-Id"])
    reason = (
        "upstream assistant message has no content, tool_calls or function_call"
        if choices
        else "invalid upstream chat response"
    )
    assert trace["attempts"][0]["reason"] == reason
    assert trace["attempts"][0]["response"] == invalid
    assert all(a["called"] and a["http_status"] == 200 for a in trace["attempts"])
    assert trace["cost_complete"] is True
    assert trace["cost_usd"] == pytest.approx(0.10)
    if later_succeeds:
        assert status == 200 and payload == reply()
        assert headers["X-Provider-Used"] == "p1"
        assert trace["attempts"][1]["reason"] == "success"
    else:
        assert status == 502
        assert payload["error"]["type"] == "no_provider_available"
        assert reason in payload["error"]["message"]
        assert trace["attempts"][1]["reason"] == reason


@pytest.mark.parametrize("content", [None, "", " \n"])
def test_tool_only_assistant_response_succeeds(store, monkeypatch, content):
    configuration = setup(store, monkeypatch)
    expected = reply(tool={"name": "lookup", "arguments": "{}"})
    expected["choices"][0]["message"]["content"] = content
    payload, status, headers = run(
        store, configuration, lambda r: httpx.Response(200, json=expected)
    )
    assert status == 200 and payload == expected
    attempts = store.trace(headers["X-Trace-Id"])["attempts"]
    assert len(attempts) == 1 and attempts[0]["reason"] == "success"


@pytest.mark.parametrize("content", [None, "", " \n"])
def test_legacy_function_call_response_succeeds(store, monkeypatch, content):
    configuration = setup(store, monkeypatch)
    expected = reply(finish="function_call")
    expected["choices"][0]["message"] = {
        "role": "assistant",
        "content": content,
        "function_call": {"name": "lookup", "arguments": "{}"},
    }
    payload, status, headers = run(
        store, configuration, lambda r: httpx.Response(200, json=expected)
    )
    assert status == 200 and payload == expected
    assert headers["X-Provider-Used"] == "p0"
    attempts = store.trace(headers["X-Trace-Id"])["attempts"]
    assert len(attempts) == 1 and attempts[0]["reason"] == "success"


@pytest.mark.parametrize("status", [400, 401, 403])
def test_pinned_model_non_retryable_error(store, monkeypatch, status):
    configuration = setup(store, monkeypatch)
    _, actual, headers = run(
        store,
        configuration,
        lambda r: httpx.Response(status, json={"error": "bad"}),
        {**REQUEST, "model": "chat"},
    )
    assert actual == status
    assert len(store.trace(headers["X-Trace-Id"])["attempts"]) == 1


@pytest.mark.parametrize("route", ["default", "route:default", "route:strong"])
@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_route_continues_after_upstream_4xx(store, monkeypatch, route, status):
    configuration = setup(store, monkeypatch)

    def handler(request):
        if request.url.host == "p0.test":
            return httpx.Response(status, json={"error": {"message": "bad"}})
        return httpx.Response(200, json=reply())

    payload, actual, headers = run(
        store, configuration, handler, {**REQUEST, "model": route}
    )
    assert actual == 200 and payload == reply()
    failed, succeeded = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["called"] and failed["http_status"] == status
    assert failed["reason"] == f"upstream HTTP {status}"
    assert succeeded["provider"] == "p1" and succeeded["reason"] == "success"


def test_route_continues_after_groq_rejects_unknown_tool(store, monkeypatch):
    configuration = setup(store, monkeypatch, provider_ids=("groq", "cloudflare"))
    error = {
        "error": {
            "code": "tool_use_failed",
            "message": "Tool call validation failed: attempted to call tool 'search_repo' which was not in request.tools",
        }
    }

    def handler(request):
        if request.url.host == "groq.test":
            return httpx.Response(400, json=error)
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store, configuration, handler, {**REQUEST, "model": "route:default"}
    )
    assert status == 200 and headers["X-Provider-Used"] == "cloudflare"
    failed, succeeded = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["called"] and failed["http_status"] == 400
    assert failed["response"] == error
    assert succeeded["reason"] == "success"


HALLUCINATED_TOOL = {
    "error": {
        "message": "Tool call validation failed: attempted to call tool 'repo_browser.search' which was not in request.tools",
        "type": "invalid_request_error",
        "code": "tool_use_failed",
        "failed_generation": "<tool_call>",
    }
}
HALLUCINATION_REASON = (
    "upstream Groq HTTP 400: model called a tool not in request.tools"
)


def groq_models(
    store, monkeypatch, provider_ids=("groq",), model_ids=("alpha", "beta")
):
    configuration = setup(
        store, monkeypatch, count=len(provider_ids), provider_ids=provider_ids
    )
    base = store.models()[0]
    store.replace_models(
        "groq",
        [
            {
                **base,
                "provider": "groq",
                "id": model_id,
                "free": True,
                "input_price": 0,
                "output_price": 0,
            }
            for model_id in model_ids
        ],
    )
    return configuration


def sent_models(sent, handler_for):
    def handler(request):
        model = json.loads(request.content)["model"]
        sent.append((request.url.host, model))
        return handler_for(request.url.host, model)

    return handler


def test_groq_tool_hallucination_moves_to_next_groq_model(store, monkeypatch):
    configuration = groq_models(store, monkeypatch, ("groq", "cloudflare"))
    sent = []
    handler = sent_models(
        sent,
        lambda host, model: (
            httpx.Response(400, json=HALLUCINATED_TOOL)
            if model == "alpha"
            else httpx.Response(200, json=reply())
        ),
    )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            first = await gateway.complete({**REQUEST, "model": "route:default"})
            second = await gateway.complete({**REQUEST, "model": "route:default"})
            return gateway, first, second

    gateway, (_, status, headers), (_, second_status, _) = asyncio.run(scenario())
    assert status == 200 and second_status == 200
    assert sent == [("groq.test", "alpha"), ("groq.test", "beta")] + [
        ("groq.test", "alpha"),
        ("groq.test", "beta"),
    ]
    failed, succeeded = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["model"] == "alpha" and failed["reason"] == HALLUCINATION_REASON
    assert failed["response"] == HALLUCINATED_TOOL and failed["cost_usd"] == 0.0
    assert succeeded["model"] == "beta" and succeeded["reason"] == "success"
    assert headers["X-Provider-Used"] == "groq"
    assert not any(
        [
            gateway.cooldowns,
            gateway.overload_cooldowns,
            gateway.unavailable_cooldowns,
            gateway.transport_cooldowns,
        ]
    )


def test_groq_tool_hallucination_list_wrapped_body_is_classified_the_same(
    store, monkeypatch
):
    configuration = groq_models(store, monkeypatch, ("groq", "cloudflare"))
    sent = []
    handler = sent_models(
        sent,
        lambda host, model: (
            httpx.Response(400, json=[HALLUCINATED_TOOL])
            if model == "alpha"
            else httpx.Response(200, json=reply())
        ),
    )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            result = await gateway.complete({**REQUEST, "model": "route:default"})
            return gateway, result

    gateway, (_, status, headers) = asyncio.run(scenario())
    assert status == 200 and headers["X-Provider-Used"] == "groq"
    assert sent == [("groq.test", "alpha"), ("groq.test", "beta")]
    failed, succeeded = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["model"] == "alpha" and failed["reason"] == HALLUCINATION_REASON
    assert failed["response"] == HALLUCINATED_TOOL
    assert succeeded["model"] == "beta" and succeeded["reason"] == "success"
    assert not any(
        [
            gateway.cooldowns,
            gateway.overload_cooldowns,
            gateway.unavailable_cooldowns,
            gateway.transport_cooldowns,
        ]
    )


def test_groq_tool_hallucination_after_a_blocked_sibling_reaches_third_model(
    store, monkeypatch
):
    configuration = groq_models(
        store, monkeypatch, ("groq",), ("alpha", "beta", "gamma")
    )
    sent = []
    handler = sent_models(
        sent,
        lambda host, model: (
            httpx.Response(400, json=HALLUCINATED_TOOL)
            if model == "beta"
            else httpx.Response(200, json=reply())
        ),
    )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            blocked_until = float("inf")
            gateway.overload_cooldowns[("groq", "alpha")] = blocked_until
            result = await gateway.complete({**REQUEST, "model": "route:default"})
            return gateway, blocked_until, result

    gateway, blocked_until, (_, status, headers) = asyncio.run(scenario())
    assert status == 200 and headers["X-Provider-Used"] == "groq"
    assert sent == [("groq.test", "beta"), ("groq.test", "gamma")]
    attempts = store.trace(headers["X-Trace-Id"])["attempts"]
    # A pre-dispatch block of one sibling is skipped without its own attempt row.
    assert [(a["model"], a["reason"]) for a in attempts] == [
        ("beta", HALLUCINATION_REASON),
        ("gamma", "success"),
    ]
    assert gateway.overload_cooldowns == {("groq", "alpha"): blocked_until}
    assert not any(
        [
            gateway.cooldowns,
            gateway.unavailable_cooldowns,
            gateway.transport_cooldowns,
        ]
    )


def test_groq_tool_hallucination_on_only_model_routes_to_next_provider(
    store, monkeypatch
):
    configuration = groq_models(store, monkeypatch, ("groq", "cloudflare"), ("alpha",))
    sent = []
    handler = sent_models(
        sent,
        lambda host, model: (
            httpx.Response(400, json=HALLUCINATED_TOOL)
            if host == "groq.test"
            else httpx.Response(200, json=reply())
        ),
    )
    _, status, headers = run(
        store, configuration, handler, {**REQUEST, "model": "route:default"}
    )
    assert status == 200 and headers["X-Provider-Used"] == "cloudflare"
    assert [host for host, _ in sent] == ["groq.test", "cloudflare.test"]
    failed, _ = store.trace(headers["X-Trace-Id"])["attempts"]
    assert failed["reason"] == HALLUCINATION_REASON


def test_groq_tool_hallucination_on_every_model_is_hard_failure(store, monkeypatch):
    configuration = groq_models(store, monkeypatch)
    sent = []
    handler = sent_models(
        sent, lambda host, model: httpx.Response(400, json=HALLUCINATED_TOOL)
    )
    payload, status, _ = run(
        store, configuration, handler, {**REQUEST, "model": "route:default"}
    )
    assert status == 502 and [model for _, model in sent] == ["alpha", "beta"]
    assert payload["error"]["rate_limited_only"] is False
    assert [a["reason"] for a in payload["error"]["attempts"]] == [
        HALLUCINATION_REASON
    ] * 2


@pytest.mark.parametrize(
    ("host", "body"),
    [
        ("groq", {"error": {"message": "bad", "type": "invalid_request_error"}}),
        ("groq", {"error": {"code": "tool_use_failed", "message": "bad json"}}),
        ("cloudflare", HALLUCINATED_TOOL),
    ],
)
def test_other_400s_keep_generic_route_behavior(store, monkeypatch, host, body):
    configuration = groq_models(store, monkeypatch, (host,), ("alpha", "beta"))
    if host != "groq":
        store.replace_models(host, [{**store.models()[0], "free": True}])
    sent = []
    handler = sent_models(sent, lambda h, model: httpx.Response(400, json=body))
    payload, status, _ = run(
        store, configuration, handler, {**REQUEST, "model": "route:default"}
    )
    assert status == 502 and len(sent) == 1
    assert [a["reason"] for a in payload["error"]["attempts"]] == ["upstream HTTP 400"]


def test_exact_model_groq_tool_hallucination_stays_non_retryable(store, monkeypatch):
    configuration = groq_models(store, monkeypatch)
    sent = []
    handler = sent_models(
        sent, lambda host, model: httpx.Response(400, json=HALLUCINATED_TOOL)
    )
    payload, status, headers = run(
        store, configuration, handler, {**REQUEST, "model": "alpha"}
    )
    assert (
        status == 400
        and payload == HALLUCINATED_TOOL
        and sent == [("groq.test", "alpha")]
    )
    (attempt,) = store.trace(headers["X-Trace-Id"])["attempts"]
    assert attempt["reason"] == "non-retryable upstream HTTP 400"


def test_exhausted_route_returns_attempt_list(store, monkeypatch):
    configuration = setup(store, monkeypatch)

    def handler(request):
        status = 400 if request.url.host == "p0.test" else 422
        return httpx.Response(status, json={"error": {"message": "bad"}})

    payload, status, headers = run(store, configuration, handler)
    assert status == 502 and payload["error"]["type"] == "no_provider_available"
    attempts = payload["error"]["attempts"]
    assert [
        (a["provider"], a["model"], a["called"], a["http_status"], a["reason"])
        for a in attempts
    ] == [
        ("p0", "chat", True, 400, "upstream HTTP 400"),
        ("p1", "chat", True, 422, "upstream HTTP 422"),
    ]
    assert store.trace(headers["X-Trace-Id"])["response"] == payload


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
            assert (
                store.trace(h["X-Trace-Id"])["attempts"][0]["reason"]
                == "local RPM limit"
            )
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
        return (
            httpx.Response(429, headers={"Retry-After": "120"}, json={})
            if request.url.host == "p0.test"
            else httpx.Response(200, json=reply())
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock[0])
            await gateway.complete(REQUEST)
            clock[0] = 170
            _, _, h = await gateway.complete(REQUEST)
            assert (
                store.trace(h["X-Trace-Id"])["attempts"][0]["reason"]
                == "Retry-After cooldown"
            )
            clock[0] = 221
            await gateway.complete(REQUEST)

    asyncio.run(scenario())
    assert sent == ["p0.test", "p1.test", "p1.test", "p0.test", "p1.test"]


def test_retry_after_values():
    assert retry_seconds(None) == 60
    assert retry_seconds("nonsense") == 60
    assert retry_seconds("-2") == 0
    assert retry_seconds("inf") == 60
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=90), usegmt=True)
    assert 88 < retry_seconds(future) <= 90


@pytest.mark.parametrize("first_status", [429, 410])
def test_routed_429_replays_only_after_rate_limit_only_exhaustion(
    store, monkeypatch, first_status
):
    configuration = setup(store, monkeypatch, count=3)
    monkeypatch.delenv("TEST_KEY_2")
    clock = [100.0]
    sleeps = []
    calls = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    def handler(request):
        host = request.url.host
        calls.append(host)
        if host == "p0.test":
            return httpx.Response(first_status, headers={"Retry-After": "12"}, json={})
        if clock[0] < 103:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={})
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            return await gateway.complete(REQUEST)

    payload, status, headers = asyncio.run(scenario())
    if first_status == 429:
        assert sleeps == [3]
        assert calls == ["p0.test", "p1.test", "p1.test"]
        assert status == 200 and headers["X-Provider-Used"] == "p1"
    else:
        assert sleeps == []
        assert calls == ["p0.test", "p1.test"]
        assert status == 502 and payload["error"]["rate_limited_only"] is False


@pytest.mark.parametrize("retry_after,expected_calls", [("2", 2), ("120", 1)])
def test_routed_429_replays_at_most_once_with_configured_wait(
    store, monkeypatch, retry_after, expected_calls
):
    configuration = setup(store, monkeypatch, count=1)
    monkeypatch.setenv("TWT_FREE_WAIT_SECONDS", "2")
    clock = [100.0]
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    429, headers={"Retry-After": retry_after}, json={}
                )
            ),
        ) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            return await gateway.complete(REQUEST)

    payload, status, _ = asyncio.run(scenario())
    assert status == 502 and payload["error"]["rate_limited_only"] is True
    assert sleeps == [2]
    assert len(payload["error"]["attempts"]) == 2
    assert sum(a["called"] for a in payload["error"]["attempts"]) == expected_calls


@pytest.mark.parametrize(
    "mode", ["privacy", "trains", "tools", "json", "json_schema", "chat", "model"]
)
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
        body["response_format"] = {
            "type": "json_schema" if mode == "json_schema" else "json_object"
        }
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
    assert len(store.trace(headers["X-Trace-Id"])["attempts"]) == len(providers())


@pytest.mark.parametrize(
    "prompt,completion,reasoning,finish,expected",
    [
        (10, 20, 0, "stop", []),
        (10, 100, 76, "stop", ["EXCESSIVE_REASONING"]),
        (10, 100, 75, "stop", []),
        (32001, 20, 0, "stop", ["CONTEXT_BLOAT"]),
        (32000, 20, 0, "stop", []),
        (10, 20, 0, "length", ["TRUNCATED_MAX_TOKENS"]),
    ],
)
def test_audit_thresholds(
    store, monkeypatch, prompt, completion, reasoning, finish, expected
):
    configuration = setup(store, monkeypatch, 1)
    payload = reply(prompt, completion, reasoning, finish)
    _, _, headers = run(
        store, configuration, lambda r: httpx.Response(200, json=payload)
    )
    assert store.trace(headers["X-Trace-Id"])["flags"] == expected


def test_context_window(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    model = store.models()[0]
    model["context_length"] = 100
    store.replace_models("p0", [model])
    _, _, headers = run(
        store, configuration, lambda r: httpx.Response(200, json=reply(prompt=81))
    )
    assert headers["X-Audit-Flags"] == "CONTEXT_BLOAT"


def test_tool_loop_session_and_canonical_arguments(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)

    def call(session, arguments):
        payload = reply(tool={"name": "search", "arguments": arguments})
        return run(
            store,
            configuration,
            lambda r: httpx.Response(200, json=payload),
            session=session,
        )[2]

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
    _, status, h = run(
        store, configuration, lambda r: httpx.Response(200, json=reply())
    )
    assert status == 200 and h["X-Provider-Used"] == "p1"
    assert (
        store.trace(h["X-Trace-Id"])["attempts"][0]["reason"] == "success"
    )  # free p1 is ordered before paid p0
    store.replace_models("p1", [])
    payload, status, _ = run(
        store, configuration, lambda r: pytest.fail("budget must skip")
    )
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
    _, status, h = run(
        store, configuration, lambda r: httpx.Response(200 if invalid else 500, json={})
    )
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
    _, status, h = run(
        store, configuration, lambda r: httpx.Response(200, json=payload)
    )
    assert status == 200 and h["X-Cost-Usd"] == "unknown"
    assert store.trace(h["X-Trace-Id"])["prompt_tokens"] is None


def test_default_requires_verified_free_eligibility(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)
    configuration[0]["free_only"] = True
    assert run(store, configuration, lambda r: pytest.fail("not free"))[1] == 503
    explicit = {**REQUEST, "model": "p0/chat"}
    assert (
        run(
            store, configuration, lambda r: httpx.Response(200, json=reply()), explicit
        )[1]
        == 200
    )


@pytest.mark.parametrize("payload", [[], {"choices": None}, {"choices": [None]}])
@pytest.mark.parametrize(("model", "expected"), [("default", 502), ("chat", 400)])
def test_malformed_error_payloads_are_traced(
    store, monkeypatch, payload, model, expected
):
    configuration = setup(store, monkeypatch, 1)
    _, status, h = run(
        store,
        configuration,
        lambda r: httpx.Response(400, json=payload),
        {**REQUEST, "model": model},
    )
    assert status == expected and store.trace(h["X-Trace-Id"])
    assert store.trace(h["X-Trace-Id"])["attempts"][0]["http_status"] == 400


def test_api_validation_and_models(store, monkeypatch):
    configuration = setup(store, monkeypatch, 1)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply()))
        ) as upstream:
            app = create_app(store, upstream, configuration)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as api:
                listing = await api.get("/v1/models")
                assert listing.json()["data"][0]["id"] == "p0/chat"
                for body in [
                    [],
                    {},
                    {"messages": []},
                    {"messages": [1], "response_format": []},
                ]:
                    assert (
                        await api.post("/v1/chat/completions", json=body)
                    ).status_code == 400
                assert (
                    await api.post(
                        "/v1/chat/completions",
                        content="invalid",
                        headers={"Content-Type": "application/json"},
                    )
                ).status_code == 400
                assert (
                    await api.post(
                        "/v1/chat/completions",
                        json=REQUEST,
                        headers={"X-Privacy": "typo"},
                    )
                ).status_code == 400
                response = await api.post(
                    "/v1/chat/completions",
                    json=REQUEST,
                    headers={"X-Privacy": "strict"},
                )
                assert response.status_code == 200 and response.headers["X-Trace-Id"]

    asyncio.run(scenario())


def test_double_encoded_tool_arguments_unwrapped(store, monkeypatch):
    # Cloudflare Granite returns function.arguments as a JSON string that
    # decodes to another JSON string; the gateway must emit single encoding.
    configuration = setup(store, monkeypatch, count=1)

    def handler(request):
        arguments = json.dumps('{"pattern": "now header"}')
        return httpx.Response(
            200,
            json=reply(
                tool={"name": "grep_repo", "arguments": arguments},
                finish="tool_calls",
            ),
        )

    payload, status, _ = run(store, configuration, handler)
    assert status == 200
    arguments = payload["choices"][0]["message"]["tool_calls"][0]["function"][
        "arguments"
    ]
    assert json.loads(arguments) == {"pattern": "now header"}


def test_tool_arguments_passthrough_shapes(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=1)
    cases = [
        ('{"a": 1}', {"a": 1}),  # already single-encoded
        ("plain text", "plain text"),  # not JSON: untouched
        ('"plain"', "plain"),  # intended string arg: untouched
        ({"a": 1}, {"a": 1}),  # dict shape: dumped to a string
    ]
    responses = []
    for raw, _ in cases:
        responses.append(
            httpx.Response(
                200,
                json=reply(
                    tool={"name": "lookup", "arguments": raw}, finish="tool_calls"
                ),
            )
        )
    calls = iter(responses)

    def handler(request):
        return next(calls)

    for raw, want in cases:
        payload, status, _ = run(store, configuration, handler)
        assert status == 200
        arguments = payload["choices"][0]["message"]["tool_calls"][0]["function"][
            "arguments"
        ]
        try:
            decoded = json.loads(arguments)
        except ValueError:
            decoded = arguments
        assert decoded == want
