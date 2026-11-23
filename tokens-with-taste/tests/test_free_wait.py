import asyncio

import httpx
import pytest
from test_gateway import REQUEST, reply, setup
from twt.gateway import Gateway, create_app, upstream_cooldown


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"error": "rate limited"},
        {
            "error": {
                "metadata": {
                    "limit_source": "openrouter_free_tier_daily",
                    "headers": {"X-RateLimit-Reset": "invalid"},
                }
            }
        },
    ],
)
def test_missing_or_invalid_daily_reset_preserves_retry_after(payload):
    assert (
        upstream_cooldown(httpx.Response(429, headers={"Retry-After": "2"}), payload)
        == 2
    )


def test_explicit_daily_exhaustion_waits_until_reset_not_each_request(
    store, monkeypatch
):
    configuration = free_first(store, monkeypatch)
    monkeypatch.setattr("twt.gateway.time.time", lambda: 1000)
    calls = []
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "p0.test":
            return httpx.Response(
                429,
                json={
                    "error": {
                        "metadata": {
                            "limit_source": "openrouter_free_tier_daily",
                            "headers": {"X-RateLimit-Reset": "2000000"},
                        }
                    }
                },
            )
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration, sleep=sleep)
            for _ in range(2):
                assert (await gateway.complete(REQUEST))[1] == 200

    asyncio.run(scenario())
    assert calls == ["p0.test", "p1.test", "p1.test"]
    assert sleeps == []


def free_first(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    model = store.models()[0]
    model.update(free=True, input_price=0, output_price=0, rpm=100)
    store.replace_models("p0", [model])
    return configuration


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
@pytest.mark.parametrize("free", [True, False])
@pytest.mark.parametrize("recovery_elapsed", [250, 301])
def test_free_transport_failure_cools_down_then_recovers(
    store, monkeypatch, error_type, free, recovery_elapsed
):
    configuration = (
        free_first(store, monkeypatch) if free else setup(store, monkeypatch)
    )
    clock = [100.0]
    calls = []
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def handler(request):
        calls.append(request.url.host)
        if len(calls) == 1:
            raise error_type("provider unavailable", request=request)
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            _, status, headers = await gateway.complete(REQUEST)
            assert status == 200 and headers["X-Provider-Used"] == "p1"
            first = store.trace(headers["X-Trace-Id"])
            assert first["cost_complete"] is free
            assert first["attempts"][0]["cost_usd"] == (0 if free else None)
            _, status, headers = await gateway.complete(REQUEST)
            assert status == 200
            assert headers["X-Provider-Used"] == ("p1" if free else "p0")
            if free:
                skipped = store.trace(headers["X-Trace-Id"])["attempts"][0]
                assert skipped["called"] is False
                assert skipped["reason"] == "transport failure cooldown"
            else:
                assert gateway.transport_cooldowns == {}
            clock[0] += recovery_elapsed
            _, status, headers = await gateway.complete(REQUEST)
            assert status == 200 and headers["X-Provider-Used"] == "p0"
            assert float(headers["X-Cost-Usd"]) == pytest.approx(0 if free else 0.05)

    asyncio.run(scenario())
    assert calls == ["p0.test", "p1.test", "p1.test" if free else "p0.test", "p0.test"]
    assert sleeps == ([50] if free and recovery_elapsed == 250 else [])


@pytest.mark.parametrize(
    "retry_after,failures,expected,waits",
    [
        ("2", 1, "p0", [2]),
        ("2", 2, "p1", [2]),
        ("120", 1, "p1", []),
        ("invalid", 1, "p0", [60]),
    ],
)
@pytest.mark.parametrize("model", ["chat", "route:default"])
def test_rate_limited_free_model_before_paid_fallback(
    store, monkeypatch, retry_after, failures, expected, waits, model
):
    configuration = free_first(store, monkeypatch)
    clock = [100.0]
    sleeps = []
    calls = []
    if model == "route:default":
        expected, waits = "p1", []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "p0.test" and calls.count("p0.test") <= failures:
            return httpx.Response(429, headers={"Retry-After": retry_after}, json={})
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            _, status, headers = await gateway.complete({**REQUEST, "model": model})
            assert status == 200
            assert headers["X-Provider-Used"] == expected
            trace = store.trace(headers["X-Trace-Id"])
            assert trace["cost_complete"]
            assert all(
                a["cost_usd"] == 0
                for a in trace["attempts"]
                if a["provider"] == "p0" and a["called"]
            )
            assert float(headers["X-Cost-Usd"]) == pytest.approx(
                0 if expected == "p0" else 0.05
            )

    asyncio.run(scenario())
    assert sleeps == waits


def test_local_free_rpm_wait_does_not_spend_paid(store, monkeypatch):
    configuration = free_first(store, monkeypatch)
    model = store.models()[0]
    model["rpm"] = 1
    store.replace_models("p0", [model])
    clock = [100.0]
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply()))
        ) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            await gateway.complete(REQUEST)
            _, _, headers = await gateway.complete(REQUEST)
            assert headers["X-Provider-Used"] == "p0"

    asyncio.run(scenario())
    assert sleeps == [60]


def test_502_retains_known_cost_header(store, monkeypatch):
    configuration = free_first(store, monkeypatch)

    def handler(request):
        if request.url.host == "p0.test":
            return httpx.Response(429, headers={"Retry-After": "120"}, json={})
        return httpx.Response(
            200,
            json={
                "choices": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as upstream:
            app = create_app(store, upstream, configuration)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                response = await client.post("/v1/chat/completions", json=REQUEST)
                assert response.status_code == 502
                assert float(response.headers["x-cost-usd"]) == pytest.approx(0.05)
                assert store.trace(response.headers["x-trace-id"])["cost_complete"]

    asyncio.run(scenario())
