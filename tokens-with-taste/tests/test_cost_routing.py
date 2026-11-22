"""Cross-provider cost routing: free first, then cheapest paid by blended price, unknown price last."""

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup


def price(store, provider, input_price, output_price, free=False, **extra):
    model = next(m for m in store.models() if m["provider"] == provider)
    store.replace_models(
        provider,
        [
            {
                **model,
                "free": free,
                "input_price": input_price,
                "output_price": output_price,
                **extra,
            }
        ],
    )


def hosts_for(store, configuration, body=None, privacy="standard"):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(503, json={})

    status = run(store, configuration, handler, body or REQUEST, privacy)[1]
    return hosts, status


def test_free_model_on_later_provider_beats_paid_on_earlier(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=3)
    price(store, "p2", 0, 0, free=True)
    assert hosts_for(store, configuration)[0] == ["p2.test", "p0.test", "p1.test"]


def test_cheaper_paid_later_provider_goes_first_by_blended_price(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=3)
    price(store, "p0", 3e-6, 3e-6)
    price(store, "p1", 1e-6, 1e-6)
    price(store, "p2", 2e-6, 0.1e-6)  # blended 1.62e-6: beats p0 only
    assert hosts_for(store, configuration)[0] == ["p1.test", "p2.test", "p0.test"]


def test_blended_weighting_counts_output_price(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    price(store, "p0", 1e-6, 100e-6)  # blended 20.8e-6
    price(store, "p1", 5e-6, 5e-6)  # blended 5e-6, higher input price
    assert hosts_for(store, configuration)[0] == ["p1.test", "p0.test"]


def test_unknown_price_goes_last_and_ties_keep_provider_order(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=4)
    price(store, "p0", None, None)
    assert hosts_for(store, configuration)[0] == [
        "p1.test",
        "p2.test",
        "p3.test",
        "p0.test",
    ]


def test_free_providers_keep_configured_order(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=3)
    for provider in ("p1", "p2"):
        price(store, provider, 0, 0, free=True)
    assert hosts_for(store, configuration)[0] == ["p1.test", "p2.test", "p0.test"]


def test_tools_capability_filters_before_ranking(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    price(store, "p1", 0, 0, free=True, tools=False)
    body = {
        **REQUEST,
        "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}],
    }
    assert hosts_for(store, configuration, body)[0] == ["p0.test"]


def test_strict_privacy_excluded_provider_is_not_ranked_first(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    configuration[1]["strict"] = False
    price(store, "p1", 0, 0, free=True)
    hosts, _ = hosts_for(store, configuration, privacy="strict")
    assert hosts == ["p0.test"]


def test_budget_still_skips_paid_after_reorder(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    run(store, configuration, lambda r: httpx.Response(200, json=reply()))
    monkeypatch.setenv("TWT_DAILY_BUDGET_USD", "0.0001")
    hosts, status = hosts_for(store, configuration)
    assert hosts == [] and status == 503


@pytest.mark.parametrize("body", [{"model": "chat"}, {"model": "p1/chat"}])
def test_exact_model_unchanged(store, monkeypatch, body):
    configuration = setup(store, monkeypatch, count=2)
    price(store, "p0", 9e-6, 9e-6)
    price(store, "p1", 1e-6, 1e-6)
    hosts, _ = hosts_for(store, configuration, {**REQUEST, **body})
    assert hosts == (
        ["p1.test"] if body["model"] == "p1/chat" else ["p1.test", "p0.test"]
    )


def test_provider_models_restricts_ranking_to_selected_model(store, monkeypatch):
    configuration = setup(store, monkeypatch, count=2)
    p0 = next(m for m in store.models() if m["provider"] == "p0")
    store.replace_models(
        "p0",
        [
            {**p0, "input_price": 9e-6, "output_price": 9e-6},
            {**p0, "id": "cheap", "input_price": 1e-7, "output_price": 1e-7},
        ],
    )
    price(store, "p1", 1e-6, 1e-6)
    assert hosts_for(store, configuration)[0] == ["p0.test", "p1.test"]
    body = {**REQUEST, "provider_models": {"p0": "chat"}}
    assert hosts_for(store, configuration, body)[0] == ["p1.test", "p0.test"]
