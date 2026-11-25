import asyncio
import json

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup
from twt.costs import cost_upper_bound
from twt.gateway import Gateway, create_app

TOOLS = [
    {
        "type": "function",
        "function": {"name": "read_file", "parameters": {"type": "object"}},
    }
]
BODY = {**REQUEST, "tools": TOOLS}
BAD = {"name": "search_repo", "arguments": "{}"}
GOOD = {"name": "read_file", "arguments": "{}"}
REASON = "upstream HTTP 200: model called a tool not in request.tools"
# setup() prices: 0.001 in, 0.002 out; reply() reports 10 in, 20 out.
COST = 10 * 0.001 + 20 * 0.002


def calls_to(host_tools):
    seen = []

    def handler(request):
        model = json.loads(request.content)["model"]
        seen.append((request.url.host, model))
        return httpx.Response(
            200, json=reply(tool=host_tools[(request.url.host, model)])
        )

    return handler, seen


@pytest.mark.parametrize("route", ["default", "route:default"])
def test_routed_unoffered_tool_fails_attempt_keeps_cost_and_falls_back(
    store, monkeypatch, route
):
    config = setup(store, monkeypatch)
    handler, seen = calls_to({("p0.test", "chat"): BAD, ("p1.test", "chat"): GOOD})
    payload, status, headers = run(store, config, handler, {**BODY, "model": route})
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 200
    assert seen == [("p0.test", "chat"), ("p1.test", "chat")]
    assert payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == (
        "read_file"
    )
    first, second = trace["attempts"]
    assert first["called"] and first["reason"] == REASON
    assert first["cost_usd"] == pytest.approx(COST)
    assert second["reason"] == "success"
    assert trace["provider"] == "p1"
    assert trace["cost_usd"] == pytest.approx(2 * COST)


def test_valid_tool_name_passes_on_the_first_model(store, monkeypatch):
    config = setup(store, monkeypatch)
    handler, seen = calls_to({("p0.test", "chat"): GOOD})
    _, status, headers = run(store, config, handler, BODY)
    assert status == 200 and seen == [("p0.test", "chat")]
    assert store.trace(headers["X-Trace-Id"])["attempts"][0]["reason"] == "success"


def test_explicit_model_request_is_returned_unchanged(store, monkeypatch):
    config = setup(store, monkeypatch)
    handler, seen = calls_to({("p0.test", "chat"): BAD})
    payload, status, headers = run(store, config, handler, {**BODY, "model": "p0/chat"})
    assert status == 200 and seen == [("p0.test", "chat")]
    assert payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == (
        "search_repo"
    )
    assert store.trace(headers["X-Trace-Id"])["attempts"][0]["reason"] == "success"


def test_only_the_bad_model_is_skipped_within_its_provider(store, monkeypatch):
    config = setup(store, monkeypatch)
    model = next(m for m in store.models() if m["provider"] == "p0")
    store.replace_models("p0", [model, {**model, "id": "chat2", "input_price": 0.0011}])
    handler, seen = calls_to({("p0.test", "chat"): BAD, ("p0.test", "chat2"): GOOD})
    _, status, headers = run(store, config, handler, BODY)
    assert status == 200
    assert seen == [("p0.test", "chat"), ("p0.test", "chat2")]
    assert store.trace(headers["X-Trace-Id"])["provider"] == "p0"


def test_every_model_unoffered_fails_with_reasons_and_known_cost(store, monkeypatch):
    config = setup(store, monkeypatch)
    handler, seen = calls_to({("p0.test", "chat"): BAD, ("p1.test", "chat"): BAD})
    payload, status, headers = run(store, config, handler, BODY)
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 502 and len(seen) == 2
    assert payload["error"]["message"].count("not in request.tools") == 2
    assert trace["cost_complete"] is True
    assert trace["cost_usd"] == pytest.approx(2 * COST)


def test_requests_without_tools_are_not_checked(store, monkeypatch):
    config = setup(store, monkeypatch)
    handler, seen = calls_to({("p0.test", "chat"): GOOD})
    _, status, headers = run(store, config, handler, REQUEST)
    assert status == 200 and seen == [("p0.test", "chat")]
    assert store.trace(headers["X-Trace-Id"])["attempts"][0]["reason"] == "success"


def test_route_strong_unoffered_tool_falls_back(store, monkeypatch):
    config = setup(store, monkeypatch)
    for provider in config:
        provider["strong_model"] = "chat"
    handler, seen = calls_to({("p0.test", "chat"): BAD, ("p1.test", "chat"): GOOD})
    _, status, headers = run(store, config, handler, {**BODY, "model": "route:strong"})
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 200 and trace["provider"] == "p1"
    assert trace["attempts"][0]["reason"] == REASON
    assert trace["cost_usd"] == pytest.approx(2 * COST)


def test_one_unoffered_call_rejects_the_whole_mixed_response(store, monkeypatch):
    config = setup(store, monkeypatch)
    mixed = reply(tool=GOOD)
    mixed["choices"][0]["message"]["tool_calls"].append(
        {"id": "call_2", "type": "function", "function": BAD}
    )
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(200, json=mixed)
        return httpx.Response(200, json=reply(tool=GOOD))

    payload, status, headers = run(store, config, handler, BODY)
    assert status == 200 and seen == ["p0.test", "p1.test"]
    calls = payload["choices"][0]["message"]["tool_calls"]
    assert [c["function"]["name"] for c in calls] == ["read_file"]
    assert store.trace(headers["X-Trace-Id"])["attempts"][0]["reason"] == REASON


def test_receipt_keeps_the_rejected_attempts_cost(store, monkeypatch):
    config = setup(store, monkeypatch)
    handler, _ = calls_to({("p0.test", "chat"): BAD, ("p1.test", "chat"): GOOD})

    async def scenario():
        upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app = create_app(store, client=upstream, configuration=config)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            response = await client.post("/v1/chat/completions", json=BODY)
            trace_id = response.headers["X-Trace-Id"]
            receipts = await client.post("/v1/receipts", json={"trace_ids": [trace_id]})
            return response, receipts.json()["receipts"][0]

    response, receipt = asyncio.run(scenario())
    assert response.status_code == 200
    assert receipt["cost_complete"] is True
    assert receipt["cost_usd"] == pytest.approx(2 * COST)
    assert receipt["prompt_tokens"] == 20 and receipt["completion_tokens"] == 40


def test_rejected_attempt_cost_counts_against_the_request_ceiling(store, monkeypatch):
    config = setup(store, monkeypatch)
    body = {**BODY, "max_tokens": 100}
    model = next(m for m in store.models() if m["provider"] == "p0")
    bound = cost_upper_bound({**body, "stream": False, "model": "chat"}, model)[
        "cost_upper_bound_usd"
    ]
    handler, seen = calls_to({("p0.test", "chat"): BAD, ("p1.test", "chat"): GOOD})

    async def scenario(ceiling):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Gateway(store, client, config).complete(body, max_cost=ceiling)

    # The bad reply's 0.05 plus p1's worst case no longer fits: p1 is never sent.
    _, status, headers = asyncio.run(scenario(bound + COST / 2))
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 502 and seen == [("p0.test", "chat")]
    assert trace["attempts"][1]["reason"].startswith("request cost ceiling")
    assert trace["cost_usd"] == pytest.approx(COST)
    seen.clear()
    _, status, _ = asyncio.run(scenario(bound + COST))
    assert status == 200 and seen == [("p0.test", "chat"), ("p1.test", "chat")]
