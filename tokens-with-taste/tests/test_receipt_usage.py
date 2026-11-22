"""Exact receipts count rejected attempts without changing response usage."""

import asyncio
import json

import httpx
import pytest
from test_gateway import reply, run, setup

from twt.audit import report
from twt.gateway import create_app


@pytest.mark.parametrize("outcome", ["success", "fallback", "final_error"])
@pytest.mark.parametrize("missing_usage", [False, True])
def test_receipts_reconcile_all_dispatched_attempts(store, monkeypatch, outcome, missing_usage):
    configuration = setup(store, monkeypatch, count=1 if outcome == "success" else 2)

    def handler(request):
        payload = reply(prompt=8738, completion=8192) if request.url.host == "p0.test" else reply()
        rejected = outcome == "final_error" or (outcome == "fallback" and request.url.host == "p0.test")
        if rejected:
            payload["choices"][0]["message"]["content"] = ""
        if missing_usage and request.url.host == "p0.test":
            del payload["usage"]
        return httpx.Response(200, json=payload)

    _, status, headers = run(store, configuration, handler)
    trace = store.trace(headers["X-Trace-Id"])
    assert status == (502 if outcome == "final_error" else 200)

    async def receipt():
        app = create_app(store=store, configuration=configuration)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://localhost") as api:
            response = await api.post("/v1/receipts", json={"trace_ids": [trace["trace_id"], trace["trace_id"]]})
            data = response.json()["receipts"]
            assert len(data) == 1
            return data[0]

    exact = asyncio.run(receipt())
    rows = report([trace])["groups"]
    assert exact["usage_complete"] is not missing_usage
    for field in ("prompt_tokens", "completion_tokens"):
        total = sum(row[field] for row in rows)
        assert exact["known_" + field] == total
        assert exact[field] == (None if missing_usage else total)
    assert exact["cost_usd"] == trace["cost_usd"]
    assert exact["cost_complete"] == trace["cost_complete"]
    if outcome == "fallback":
        # Response-level diagnostics still describe the successful answer only.
        assert trace["prompt_tokens"] == 10
        assert exact["known_prompt_tokens"] == (10 if missing_usage else 8748)


def test_rejected_attempt_reconciles_with_attempt_ledger(store, monkeypatch):
    """Issue #1299 shape: empty reply with 8738/8192 tokens, top-level usage null."""
    configuration = setup(store, monkeypatch, count=1)

    def handler(request):
        payload = reply(prompt=8738, completion=8192)
        payload["choices"][0]["message"]["content"] = ""
        return httpx.Response(200, json=payload)

    _, status, headers = run(store, configuration, handler)
    trace = store.trace(headers["X-Trace-Id"])
    assert status == 502 and trace["prompt_tokens"] is None
    rows = [json.loads(r[0]) for r in store.db.execute(
        "SELECT data FROM attempts WHERE trace_id=?", (trace["trace_id"],))]
    assert len(rows) == 1
    assert (rows[0]["prompt_tokens"], rows[0]["completion_tokens"]) == (8738, 8192)
    assert trace["cost_complete"] is True
    assert trace["cost_usd"] == pytest.approx(8738 * .001 + 8192 * .002)
    assert store.spend_today() == pytest.approx(trace["cost_usd"])
    group = report([trace])["groups"][0]
    assert (group["prompt_tokens"], group["completion_tokens"]) == (8738, 8192)
