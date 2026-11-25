import json

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup

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
