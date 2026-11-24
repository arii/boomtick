import asyncio
import random

import httpx
import pytest
from test_gateway import REQUEST, reply, setup
from twt.gateway import Gateway, create_app

OVERLOAD = {"error": {"message": "System is overloaded"}}
# setup() prices: 0.001 in, 0.002 out. With max_tokens 100 the prompt rounds to
# 1024 tokens, so one attempt reserves 1024 * 0.001 + 100 * 0.002 = 1.224.
BOUND = 1.224
BODY = {**REQUEST, "max_tokens": 100}


def run(store, config, handler, max_cost, body=BODY):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Gateway(store, client, config).complete(
                body, max_cost=max_cost
            )

    return asyncio.run(scenario())


def worst_case(trace):
    return sum(
        a["cost_usd"] if a["cost_usd"] is not None else a["cost_upper_bound_usd"]
        for a in trace["attempts"]
        if a["called"]
    )


def test_ceiling_below_worst_case_never_dispatches(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    _, status, headers = run(
        store, config, lambda _: pytest.fail("dispatched over the ceiling"), 1.2
    )
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 503
    assert not any(a["called"] for a in trace["attempts"])
    assert trace["attempts"][0]["reason"].startswith("request cost ceiling: worst case")
    assert trace["attempts"][0]["request"] is None
    assert trace["billing_status"] == "none"
    assert trace["provider"] is None


def test_ceiling_at_worst_case_dispatches(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    _, status, headers = run(
        store, config, lambda _: httpx.Response(200, json=reply()), BOUND
    )
    assert status == 200
    assert store.trace(headers["X-Trace-Id"])["cost_usd"] == pytest.approx(0.05)


def test_failed_attempt_reservation_counts_before_fallback(store, monkeypatch):
    config = setup(store, monkeypatch)
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(529, json=OVERLOAD)

    _, _, headers = run(store, config, handler, 2 * BOUND - 0.001)
    trace = store.trace(headers["X-Trace-Id"])
    assert len(calls) == 1
    assert trace["cost_upper_bound_usd"] == pytest.approx(BOUND)
    assert trace["attempts"][1]["reason"].startswith("request cost ceiling")

    calls.clear()
    _, _, headers = run(store, config, handler, 2 * BOUND)
    assert len(calls) == 2
    assert store.trace(headers["X-Trace-Id"])["cost_upper_bound_usd"] == pytest.approx(
        2 * BOUND
    )


def test_zero_ceiling_still_allows_zero_priced_free_models(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    model = store.models()[0]
    store.replace_models(
        "p0", [{**model, "free": True, "input_price": 0, "output_price": 0}]
    )
    _, status, headers = run(
        store, config, lambda _: httpx.Response(200, json=reply()), 0
    )
    assert status == 200
    assert store.trace(headers["X-Trace-Id"])["cost_usd"] == 0


def test_unboundable_paid_attempt_is_refused_under_a_ceiling(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    # No max_tokens in the request and no catalog output cap: no finite worst case.
    _, status, headers = run(
        store, config, lambda _: pytest.fail("unbounded dispatch"), 100.0, REQUEST
    )
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 503
    assert trace["attempts"][0]["reason"] == (
        "request cost ceiling: paid attempt cost cannot be bounded"
    )


def test_no_ceiling_keeps_existing_behavior(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    _, status, _ = run(store, config, lambda _: httpx.Response(200, json=reply()), None)
    assert status == 200


def test_randomized_fallbacks_never_exceed_the_ceiling(store, monkeypatch):
    config = setup(store, monkeypatch, count=4)
    rng = random.Random(1464)
    for _ in range(60):
        ceiling = rng.uniform(0, 5 * BOUND)
        outcomes = iter(rng.choice([200, 500, 529, "timeout"]) for _ in range(8))

        def handler(_, outcomes=outcomes):
            outcome = next(outcomes)
            if outcome == "timeout":
                raise httpx.ReadTimeout("no usage delivered")
            if outcome == 200:
                return httpx.Response(200, json=reply(prompt=900, completion=100))
            return httpx.Response(outcome, json=OVERLOAD)

        _, _, headers = run(store, config, handler, ceiling)
        assert worst_case(store.trace(headers["X-Trace-Id"])) <= ceiling + 1e-12


def asgi(store, config, handler, call):
    async def scenario():
        upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        app = create_app(store, client=upstream, configuration=config)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            return await call(client)

    return asyncio.run(scenario())


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "abc", ""])
def test_http_rejects_invalid_ceiling(store, monkeypatch, value):
    config = setup(store, monkeypatch, count=1)
    response = asgi(
        store,
        config,
        lambda _: pytest.fail("dispatched"),
        lambda c: c.post(
            "/v1/chat/completions", json=BODY, headers={"X-Max-Cost-Usd": value}
        ),
    )
    assert response.status_code == 400


def test_http_passes_ceiling_and_advertises_feature(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    response = asgi(
        store,
        config,
        lambda _: pytest.fail("dispatched over the ceiling"),
        lambda c: c.post(
            "/v1/chat/completions", json=BODY, headers={"X-Max-Cost-Usd": "0.5"}
        ),
    )
    assert response.status_code == 503
    models = asgi(store, config, lambda _: None, lambda c: c.get("/v1/models"))
    assert "request_cost_ceiling" in models.json()["features"]
