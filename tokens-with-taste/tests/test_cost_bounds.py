import asyncio
import json
import math
from decimal import Decimal

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup
from twt.catalog import normalize
from twt.costs import cost_upper_bound
from twt.gateway import create_app

MODEL = {"input_price": 0.00000015, "output_price": 0.0000005, "max_output_tokens": 8192}
OVERLOAD = {"error": {"type": "server_error", "message": "System is overloaded", "param": None, "code": None},
            "detail": "System is overloaded"}


def test_conservative_text_tools_unicode_and_choice_estimate():
    request = {**REQUEST, "max_tokens": 400, "n": 2,
               "messages": [{"role": "user", "content": "你好" * 300}],
               "tools": [{"type": "function", "function": {"name": "a", "description": "x" * 2000}}]}
    bound = cost_upper_bound(request, MODEL)
    size = len(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode())
    assert bound["prompt_tokens_upper_bound"] >= 2 * (size + 320)
    assert bound["prompt_tokens_upper_bound"] % 1024 == 0
    assert bound["completion_tokens_upper_bound"] == 800
    expected = (Decimal(bound["prompt_tokens_upper_bound"]) * Decimal("0.00000015")
                + Decimal(800) * Decimal("0.0000005"))
    assert Decimal(str(bound["cost_upper_bound_usd"])) >= expected


def test_empty_messages_output_cap_alias_and_partial_usage():
    assert cost_upper_bound({"messages": []}, MODEL)["completion_tokens_upper_bound"] == 8192
    assert cost_upper_bound({"messages": [], "max_completion_tokens": 500}, MODEL)["completion_tokens_upper_bound"] == 500
    bound = cost_upper_bound({"messages": [], "max_tokens": 100}, MODEL,
                             {"prompt_tokens": 10000, "completion_tokens": 200})
    assert bound["prompt_tokens_upper_bound"] == 10000
    assert bound["completion_tokens_upper_bound"] == 200


@pytest.mark.parametrize("value", [None, -1, float("inf"), float("nan"), True])
def test_missing_or_invalid_prices_never_produce_a_bound(value):
    assert cost_upper_bound(REQUEST, {**MODEL, "input_price": value}) == {}
    assert cost_upper_bound(REQUEST, {**MODEL, "output_price": value}) == {}


@pytest.mark.parametrize("change", [
    {"max_tokens": None}, {"max_tokens": 0}, {"max_tokens": True}, {"n": -1},
    {"messages": None}, {"messages": [{"content": [{"type": "image_url", "image_url": {"url": "a"}}]}]},
])
def test_invalid_or_unbounded_requests_remain_unknown(change):
    assert cost_upper_bound({**REQUEST, **change}, MODEL) == {}
    assert cost_upper_bound(REQUEST, {**MODEL, "max_output_tokens": None}) == {}


def test_catalog_preserves_output_cap_from_metadata():
    model = normalize({"id": "nebius", "map_prefix": "nebius", "base_url": "https://example.test"},
                      {"id": "glm"}, {"nebius/glm": {"max_output_tokens": 16384}}, {})
    assert model["max_output_tokens"] == 16384


@pytest.mark.parametrize("status", [500, 529])
def test_nebius_shaped_failure_has_reserved_but_not_actual_cost(store, monkeypatch, status):
    config = setup(store, monkeypatch, count=1)
    _, code, headers = run(store, config, lambda _: httpx.Response(status, json=OVERLOAD),
                           {**REQUEST, "max_tokens": 8192})
    trace = store.trace(headers["X-Trace-Id"])
    assert code == 502
    assert trace["cost_complete"] is False and trace["cost_usd"] is None
    assert trace["cost_basis"] == "upper_bound"
    assert trace["cost_upper_bound_usd"] == pytest.approx(1024 * .001 + 8192 * .002)
    assert trace["attempts"][0]["prompt_tokens"] is None
    assert store.spend_today() == trace["cost_upper_bound_usd"]

    async def receipt():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(store, configuration=config)), base_url="http://localhost") as client:
            return (await client.post("/v1/receipts", json={"trace_ids": [trace["trace_id"]]})).json()["receipts"][0]

    result = asyncio.run(receipt())
    assert result["cost_upper_bound_usd"] == trace["cost_upper_bound_usd"]
    assert result["cost_basis"] == "upper_bound" and result["cost_complete"] is False


def test_bound_adds_failed_attempt_to_successful_fallback(store, monkeypatch):
    config = setup(store, monkeypatch)
    _, _, headers = run(store, config,
        lambda r: httpx.Response(529, json=OVERLOAD) if r.url.host == "p0.test" else httpx.Response(200, json=reply()),
        {**REQUEST, "max_tokens": 100})
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["cost_complete"] is False
    assert trace["known_cost_usd"] == .05
    assert trace["cost_upper_bound_usd"] == pytest.approx(1.224 + .05)


def test_missing_prices_or_output_cap_and_no_dispatch_do_not_invent_bounds(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    _, _, headers = run(store, config, lambda _: httpx.Response(529, json=OVERLOAD))
    assert store.trace(headers["X-Trace-Id"]).get("cost_upper_bound_usd") is None
    monkeypatch.delenv("TEST_KEY_0")
    _, _, headers = run(store, config, lambda _: pytest.fail("not dispatched"), {**REQUEST, "max_tokens": 100})
    assert store.trace(headers["X-Trace-Id"]).get("cost_upper_bound_usd") is None


def test_timeout_reservation_counts_against_daily_budget(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)

    def timeout(_):
        raise httpx.ReadTimeout("no usage delivered")

    _, _, headers = run(store, config, timeout, {**REQUEST, "max_tokens": 100})
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["cost_basis"] == "upper_bound"
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", ".5")
    _, status, _ = run(store, config, lambda _: pytest.fail("budget exceeded"), {**REQUEST, "max_tokens": 100})
    assert status == 503


def test_one_unbounded_attempt_prevents_aggregate_bound(store, monkeypatch):
    config = setup(store, monkeypatch)
    model = next(m for m in store.models() if m["provider"] == "p0")
    store.replace_models("p0", [{**model, "input_price": None}])
    _, _, headers = run(store, config, lambda _: httpx.Response(529, json=OVERLOAD), {**REQUEST, "max_tokens": 100})
    trace = store.trace(headers["X-Trace-Id"])
    # Unknown-price p0 is tried last, after priced p1.
    assert [a["provider"] for a in trace["attempts"]] == ["p1", "p0"]
    assert trace["attempts"][0]["cost_basis"] == "upper_bound"
    assert trace.get("cost_upper_bound_usd") is None


def test_error_with_reported_usage_keeps_actual_cost(store, monkeypatch):
    config = setup(store, monkeypatch, count=1)
    _, _, headers = run(store, config, lambda _: httpx.Response(529, json={**OVERLOAD, "usage": reply()["usage"]}),
                         {**REQUEST, "max_tokens": 100})
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["cost_complete"] is True
    assert trace["cost_usd"] == .05
    assert trace.get("cost_upper_bound_usd") is None


def test_daily_spend_blocks_when_a_trace_contains_an_unbounded_attempt(store, monkeypatch):
    config = setup(store, monkeypatch)
    model = next(m for m in store.models() if m["provider"] == "p0")
    store.replace_models("p0", [{**model, "max_output_tokens": 100}])
    _, _, headers = run(store, config, lambda _: httpx.Response(529, json=OVERLOAD))
    trace = store.trace(headers["X-Trace-Id"])
    assert trace["attempts"][0]["cost_upper_bound_usd"] > 0
    assert trace["attempts"][1].get("cost_upper_bound_usd") is None
    assert math.isinf(store.spend_today())
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "100")
    _, status, _ = run(store, config, lambda _: pytest.fail("unknown prior spend must block"))
    assert status == 503


def test_daily_spend_sums_attempt_bounds_instead_of_trace_aggregate(store, monkeypatch):
    config = setup(store, monkeypatch)
    _, _, headers = run(store, config, lambda _: httpx.Response(529, json=OVERLOAD), {**REQUEST, "max_tokens": 100})
    trace = store.trace(headers["X-Trace-Id"])
    expected = sum(a["cost_upper_bound_usd"] for a in trace["attempts"])
    trace.pop("cost_upper_bound_usd")
    trace.pop("cost_basis")
    monkeypatch.setattr(store, "traces", lambda _: [trace])
    assert store.spend_today() == expected


@pytest.mark.parametrize("provider_cap,router_cap", [(32768, 4096), (8192, 65536)])
def test_output_bound_uses_selected_provider_metadata(provider_cap, router_cap):
    provider = {"id": "nebius", "map_prefix": "nebius", "base_url": "https://example.test"}
    model = normalize(provider, {"id": "glm"}, {"nebius/glm": {**MODEL, "max_output_tokens": provider_cap}},
                      {"glm": {"top_provider": {"max_completion_tokens": router_cap}}})
    assert model["max_output_tokens"] == provider_cap
    assert cost_upper_bound(REQUEST, {**MODEL, "max_output_tokens": model["max_output_tokens"]})["completion_tokens_upper_bound"] == provider_cap


def test_unknown_provider_cap_uses_largest_exact_model_cap_or_none():
    provider = {"id": "nebius", "map_prefix": "nebius", "base_url": "https://example.test"}
    prices = {"other/glm": {"max_output_tokens": 32768}, "other/not-glm": {"max_output_tokens": 999999}}
    router = {"glm": {"top_provider": {"max_completion_tokens": 4096}}}
    assert normalize(provider, {"id": "glm"}, prices, router)["max_output_tokens"] == 32768
    assert normalize(provider, {"id": "glm"}, {}, {})["max_output_tokens"] is None
