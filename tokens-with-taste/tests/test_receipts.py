import asyncio
import uuid

import httpx
import pytest
from test_free_wait import free_first
from test_gateway import REQUEST, reply
from twt.gateway import Gateway, create_app


@pytest.mark.parametrize("during_wait", [False, True])
def test_disconnected_client_never_starts_paid_fallback(
    store, monkeypatch, during_wait
):
    configuration = free_first(store, monkeypatch)
    gone = [False]
    calls = []
    clock = [100.0]

    async def disconnected():
        return gone[0]

    async def sleep(delay):
        clock[0] += delay
        gone[0] = True

    def handler(request):
        calls.append(request.url.host)
        gone[0] = not during_wait
        return httpx.Response(429, headers={"Retry-After": "2"}, json={})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            _, status, headers = await gateway.complete(
                REQUEST, disconnected=disconnected
            )
            assert status == 499
            assert float(headers["X-Cost-Usd"]) == 0
            assert store.trace(headers["X-Trace-Id"])["cost_complete"]

    asyncio.run(scenario())
    assert calls == ["p0.test"]


def test_receipt_endpoint_correlates_cancels_and_hides_prompts(store, monkeypatch):
    configuration = free_first(store, monkeypatch)
    trace_id = str(uuid.uuid4())
    cancelled = str(uuid.uuid4())
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, json=reply())

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as upstream:
            app = create_app(store, upstream, configuration)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                response = await client.post(
                    "/v1/chat/completions",
                    json=REQUEST,
                    headers={"X-Trace-Id": trace_id},
                )
                assert response.headers["x-trace-id"] == trace_id
                receipt = await client.post(
                    "/v1/receipts",
                    json={"trace_ids": [trace_id, cancelled], "cancel": True},
                )
                assert receipt.json()["receipts"][0]["trace_id"] == trace_id
                assert "request" not in receipt.text
                assert "response" not in receipt.text
                response = await client.post(
                    "/v1/chat/completions",
                    json=REQUEST,
                    headers={"X-Trace-Id": cancelled},
                )
                assert response.status_code == 499
                for ids in (["invalid"], None, [None]):
                    response = await client.post(
                        "/v1/receipts", json={"trace_ids": ids}
                    )
                    assert response.status_code == 400
                response = await client.post(
                    "/v1/receipts",
                    json={"trace_ids": []},
                    headers={"Origin": "https://evil.example"},
                )
                assert response.status_code == 403

    asyncio.run(scenario())
    assert calls == ["p0.test"]
