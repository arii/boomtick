"""Overload (5xx/503/529) cooldown: a paid model that just failed is not re-hit by the next request."""

import asyncio
import json

import httpx
import pytest
from test_gateway import REQUEST, reply, setup
from test_overload_billing import OBSERVED_529

from twt.gateway import (
    OVERLOAD_COOLDOWN_DEFAULT_SECONDS,
    OVERLOAD_COOLDOWN_MAX_SECONDS,
    Gateway,
)


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
    assert (
        second["billing_status"] == "complete"
        and results[1][2]["X-Cost-Usd"] != "unknown"
    )
    first = store.trace(results[0][2]["X-Trace-Id"])
    assert (
        first["billing_status"] == "unknown_paid_attempt" and first["cost_usd"] is None
    )


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


@pytest.mark.parametrize(
    "retry_after,window", [("120", 120), ("999999", OVERLOAD_COOLDOWN_MAX_SECONDS)]
)
def test_retry_after_is_honored_and_capped(store, monkeypatch, retry_after, window):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test" and len(hosts) == 1:
            return httpx.Response(
                529, json=OBSERVED_529, headers={"Retry-After": retry_after}
            )
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


@pytest.mark.parametrize("status", [500, 501])
def test_request_specific_5xx_sets_no_cooldown(store, monkeypatch, status):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(status, json={})
        return httpx.Response(200, json=reply())

    session(store, configuration, handler, Clock(2))
    assert hosts == ["p0.test", "p1.test", "p0.test", "p1.test"]


@pytest.mark.parametrize("status", [502, 504])
def test_gateway_unavailable_statuses_set_cooldown(store, monkeypatch, status):
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(status, json={})
        return httpx.Response(200, json=reply())

    session(store, configuration, handler, Clock(2))
    assert hosts == ["p0.test", "p1.test", "p1.test"]


GOOGLE_503 = {
    "error": {
        "code": 503,
        "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
        "status": "UNAVAILABLE",
    }
}


def google_setup(store, monkeypatch):
    return setup(store, monkeypatch, provider_ids=("google", "groq"))


def test_list_wrapped_google_503_keeps_error_and_is_overload(store, monkeypatch):
    """Behavior change: Google's [{"error": ...}] body is normalized to the error object."""
    configuration = google_setup(store, monkeypatch)

    def handler(request):
        if request.url.host == "google.test":
            return httpx.Response(503, json=[GOOGLE_503])
        return httpx.Response(200, json=reply())

    _, results = session(store, configuration, handler, Clock(1))
    trace = store.trace(results[0][2]["X-Trace-Id"])
    google = trace["attempts"][0]
    assert google["response"] == GOOGLE_503
    assert google["reason"] == "upstream HTTP 503"
    assert trace["overloaded_attempts"] == [
        {"provider": "google", "model": "chat", "http_status": 503, "cost_known": False}
    ]
    assert trace["billing_status"] == "unknown_paid_attempt"
    assert "non-object" not in json.dumps(trace)


def test_list_wrapped_google_503_cooldown_skips_next_request(store, monkeypatch):
    """Documents existing behavior (status-based cooldown) for the list-wrapped body."""
    configuration = google_setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "google.test":
            return httpx.Response(503, json=[GOOGLE_503])
        return httpx.Response(200, json=reply())

    _, results = session(store, configuration, handler, Clock(2))
    assert hosts == ["google.test", "groq.test", "groq.test"]
    second = store.trace(results[1][2]["X-Trace-Id"])["attempts"][0]
    assert second["reason"] == "overload cooldown" and second["called"] is False


def test_list_wrapped_google_503_retried_after_default_window(store, monkeypatch):
    """Documents existing behavior: the 30s default cooldown expires, then Google is retried."""
    configuration = google_setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "google.test":
            return httpx.Response(503, json=[GOOGLE_503])
        return httpx.Response(200, json=reply())

    clock = Clock(2, step=OVERLOAD_COOLDOWN_DEFAULT_SECONDS + 1)
    session(store, configuration, handler, clock)
    assert hosts == ["google.test", "groq.test", "google.test", "groq.test"]


@pytest.mark.parametrize(
    "body", [[], [1, 2], [{"detail": "x"}], [GOOGLE_503, 7], "text", 5]
)
def test_other_non_object_payloads_keep_non_object_wrapping(store, monkeypatch, body):
    """Guard: only a list of {"error": ...} objects is normalized."""
    configuration = setup(store, monkeypatch)

    def handler(request):
        if request.url.host == "p0.test":
            return httpx.Response(503, json=body)
        return httpx.Response(200, json=reply())

    _, results = session(store, configuration, handler, Clock(1))
    attempt = store.trace(results[0][2]["X-Trace-Id"])["attempts"][0]
    assert attempt["response"] == {
        "error": {"message": "Upstream returned a non-object response"},
        "raw_payload": body,
    }


def test_list_success_payload_is_never_a_completion(store, monkeypatch):
    """Guard: a 200 list body, even an error list, is not accepted as success."""
    configuration = setup(store, monkeypatch, count=1)

    def handler(request):
        return httpx.Response(200, json=[reply()])

    payload, status, _ = session(store, configuration, handler, Clock(1))[1][0]
    assert status != 200 and "choices" not in payload


def test_other_provider_503_cooldown_unchanged_with_list_body(store, monkeypatch):
    """Guard: a generic parse leaves another provider's 503 routing and cooldown as before."""
    configuration = setup(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(503, json=[GOOGLE_503])
        return httpx.Response(200, json=reply())

    session(store, configuration, handler, Clock(2))
    assert hosts == ["p0.test", "p1.test", "p1.test"]


def test_concurrent_requests_in_flight_before_first_503_both_call_model(
    store, monkeypatch
):
    """Documents existing behavior: the cooldown is recorded when the 503 returns, so
    requests already in flight are not skipped; the next sequential request is."""
    configuration = google_setup(store, monkeypatch)
    hosts = []

    async def scenario():
        gate = asyncio.Event()

        async def handler(request):
            hosts.append(request.url.host)
            if request.url.host == "google.test":
                await gate.wait()
                return httpx.Response(503, json=[GOOGLE_503])
            return httpx.Response(200, json=reply())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, clock=lambda: 100.0)
            both = asyncio.gather(gateway.complete(REQUEST), gateway.complete(REQUEST))
            await asyncio.sleep(0.05)
            gate.set()
            await both
            await gateway.complete(REQUEST)

    asyncio.run(scenario())
    assert hosts.count("google.test") == 2
