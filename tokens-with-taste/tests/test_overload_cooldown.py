"""Overload (5xx/503/529) cooldown: a paid model that just failed is not re-hit by the next request."""

import asyncio

import httpx
import pytest
from test_gateway import REQUEST, reply, setup
from test_overload_billing import OBSERVED_529

from twt.gateway import OVERLOAD_COOLDOWN_DEFAULT_SECONDS, OVERLOAD_COOLDOWN_MAX_SECONDS, Gateway


def session(store, configuration, handler, clock):
    """Run several requests against one Gateway; returns (gateway, results)."""
    results = []

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: clock[0])
            for _ in range(clock.requests):
                results.append(await gateway.complete(REQUEST))
                clock[0] += clock.step
            return gateway

    return asyncio.run(scenario()), results


class Clock(list):
    def __init__(self, requests, step=1):
        super().__init__([100.0])
        self.requests = requests
        self.step = step


def test_second_request_skips_overloaded_paid_model(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(529, json=OBSERVED_529)
        return httpx.Response(200, json=reply())

    _, results = session(store, configuration, handler, Clock(2))
    assert hosts == ["p0.test", "p1.test", "p1.test"]
    second = store.trace(results[1][2]["X-Trace-Id"])
    assert second["attempts"][0]["reason"] == "overload cooldown"
    assert second["attempts"][0]["called"] is False
    assert second["billing_status"] == "complete" and results[1][2]["X-Cost-Usd"] != "unknown"
    first = store.trace(results[0][2]["X-Trace-Id"])
    assert first["billing_status"] == "unknown_paid_attempt" and first["cost_usd"] is None


def test_cooldown_expires_after_default_window(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test" and len(hosts) == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=reply())

    clock = Clock(3, step=OVERLOAD_COOLDOWN_DEFAULT_SECONDS / 2 + 1)
    session(store, configuration, handler, clock)
    assert hosts == ["p0.test", "p1.test", "p1.test", "p0.test"]


@pytest.mark.parametrize("retry_after,window", [("120", 120), ("999999", OVERLOAD_COOLDOWN_MAX_SECONDS)])
def test_retry_after_is_honored_and_capped(store, monkeypatch, retry_after, window):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test" and len(hosts) == 1:
            return httpx.Response(529, json=OBSERVED_529, headers={"Retry-After": retry_after})
        return httpx.Response(200, json=reply())

    clock = Clock(3, step=window - 1)
    session(store, configuration, handler, clock)
    assert hosts == ["p0.test", "p1.test", "p1.test", "p0.test"]


def test_overload_does_not_make_paid_cost_zero_or_retry_in_request(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=1)
    sent = []

    def handler(request):
        sent.append(1)
        return httpx.Response(529, json=OBSERVED_529)

    _, results = session(store, configuration, handler, Clock(2))
    assert len(sent) == 1
    assert results[0][2]["X-Cost-Usd"] == "unknown"
    second = store.trace(results[1][2]["X-Trace-Id"])
    assert results[1][1] == 503 and second["billing_status"] == "none"
    assert "overload cooldown" in results[1][0]["error"]["message"]
