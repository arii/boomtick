"""Nebius HTTP 529 overload (issue #1305): unknown paid cost stays unknown."""

import asyncio

import httpx
from test_gateway import reply, run, setup
from twt.gateway import create_app

# Payload observed in the #1359 proof (trace ccd938b2-91f3-4076-aa0d-cf93a9c71ba1).
OBSERVED_529 = {"error": {"type": "server_error", "message": "System is overloaded",
                          "param": None, "code": None},
                "detail": "System is overloaded"}


def test_529_is_unknown_paid_cost_not_zero_and_not_retried(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=1)
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(529, json=OBSERVED_529)

    payload, status, headers = run(store, configuration, handler)
    assert status == 502 and len(sent) == 1
    trace = store.trace(headers["X-Trace-Id"])
    attempt = trace["attempts"][0]
    assert attempt["response"] == OBSERVED_529 and attempt["cost_usd"] is None
    assert trace["cost_complete"] is False and trace["cost_usd"] is None
    assert headers["X-Cost-Usd"] == "unknown"
    assert headers["X-Billing-Status"] == "unknown_paid_attempt"
    assert payload["error"]["billing_status"] == "unknown_paid_attempt"
    assert payload["error"]["overloaded_attempts"] == [
        {"provider": "p0", "model": "chat", "http_status": 529, "cost_known": False}]
    assert store.spend_today() > 0  # upper bound still counts against budgets

    async def receipt():
        app = create_app(store=store, configuration=configuration)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as api:
            return (await api.post("/v1/receipts", json={"trace_ids": [trace["trace_id"]]})).json()["receipts"][0]

    exact = asyncio.run(receipt())
    assert exact["cost_complete"] is False and exact["cost_usd"] is None
    assert exact["billing_status"] == "unknown_paid_attempt"
    assert exact["overloaded_attempts"][0]["http_status"] == 529


def test_529_then_fallback_keeps_cost_incomplete_with_one_call_each(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(529, json=OBSERVED_529)
        return httpx.Response(200, json=reply())

    _, status, headers = run(store, configuration, handler)
    assert status == 200 and hosts == ["p0.test", "p1.test"]
    assert headers["X-Billing-Status"] == "unknown_paid_attempt"
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["cost_complete"] is False and trace["cost_usd"] is None
    assert [a["http_status"] for a in trace["overloaded_attempts"]] == [529]
