import asyncio
import uuid

import httpx
import pytest
from test_free_wait import free_first
from test_gateway import REQUEST, reply, setup
from twt.gateway import Gateway, create_app
from twt.store import Store


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, RuntimeError])
@pytest.mark.parametrize("phase", ["disconnect", "reserve"])
def test_abandoned_predispatch_trace_can_be_retried(
    store, monkeypatch, error_type, phase
):
    configuration = setup(store, monkeypatch)
    trace_id = str(uuid.uuid4())
    calls = []

    async def fail(*args):
        raise error_type()

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: (
                    calls.append(request.url.host) or httpx.Response(200, json=reply())
                )
            )
        ) as client:
            gateway = Gateway(store, client, configuration)
            with monkeypatch.context() as patch:
                if phase == "reserve":
                    patch.setattr(gateway, "reserve", fail)
                with pytest.raises(error_type):
                    await gateway.complete(
                        REQUEST,
                        trace_id=trace_id,
                        disconnected=fail if phase == "disconnect" else None,
                    )
            assert store.trace(trace_id) is None
            assert calls == []
            assert (await gateway.complete(REQUEST, trace_id=trace_id))[1] == 200
            assert len(calls) == 1

    asyncio.run(scenario())


def test_cancellation_after_dispatch_retains_trace_reservation(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    trace_id = str(uuid.uuid4())

    async def handler(request):
        raise asyncio.CancelledError()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            with pytest.raises(asyncio.CancelledError):
                await gateway.complete(REQUEST, trace_id=trace_id)
            assert (await gateway.complete(REQUEST, trace_id=trace_id))[1] == 409

    asyncio.run(scenario())


def test_concurrent_trace_id_is_reserved_before_upstream_dispatch(store, monkeypatch):
    configuration = setup(store, monkeypatch)
    other = Store(store.path)
    trace_id = str(uuid.uuid4())
    calls = []

    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def handler(request):
            calls.append(request.url.host)
            entered.set()
            if len(calls) > 1:
                release.set()
            await release.wait()
            return httpx.Response(200, json=reply())

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as upstream:
            apps = [create_app(db, upstream, configuration) for db in (store, other)]
            async with (
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(
                        app=apps[0], raise_app_exceptions=False
                    ),
                    base_url="http://localhost",
                ) as client,
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(
                        app=apps[1], raise_app_exceptions=False
                    ),
                    base_url="http://localhost",
                ) as second_client,
            ):
                first = asyncio.create_task(
                    client.post(
                        "/v1/chat/completions",
                        json=REQUEST,
                        headers={"X-Trace-Id": trace_id},
                    )
                )
                await entered.wait()
                try:
                    second = await second_client.post(
                        "/v1/chat/completions",
                        json=REQUEST,
                        headers={"X-Trace-Id": trace_id},
                    )
                finally:
                    release.set()
                    original = await first
                assert calls == ["p0.test"]
                assert original.status_code == 200
                assert second.status_code == 409
                reused = await second_client.post(
                    "/v1/chat/completions",
                    json=REQUEST,
                    headers={"X-Trace-Id": trace_id},
                )
                assert reused.status_code == 409
                assert len(store.traces()) == 1
                assert store.trace(trace_id)["cost_usd"] == pytest.approx(0.05)

    try:
        asyncio.run(scenario())
    finally:
        other.close()


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


@pytest.mark.parametrize(
    "cancellation", ["disconnect", "receipt_cancel", "task_cancel"]
)
def test_cancelled_free_wait_refunds_reserved_rpm_slot(
    store, monkeypatch, cancellation
):
    configuration = free_first(store, monkeypatch)
    model = store.models()[0]
    model["rpm"] = 1
    store.replace_models("p0", [model])
    clock = [100.0]
    calls = []
    trace_id = str(uuid.uuid4())

    async def sleep(delay):
        clock[0] += delay
        if cancellation == "receipt_cancel":
            gateway.cancelled.add(trace_id)

    async def disconnected():
        if clock[0] >= 160 and cancellation == "task_cancel":
            raise asyncio.CancelledError
        return clock[0] >= 160 and cancellation == "disconnect"

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200, json=reply())

    async def scenario():
        nonlocal gateway
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(
                store, client, configuration, clock=lambda: clock[0], sleep=sleep
            )
            assert (await gateway.complete(REQUEST))[1] == 200
            if cancellation == "task_cancel":
                with pytest.raises(asyncio.CancelledError):
                    await gateway.complete(
                        REQUEST, trace_id=trace_id, disconnected=disconnected
                    )
            else:
                _, status, headers = await gateway.complete(
                    REQUEST, trace_id=trace_id, disconnected=disconnected
                )
                assert status == 499
                assert float(headers["X-Cost-Usd"]) == 0
            gateway.free_wait_seconds = 0
            _, status, headers = await gateway.complete(REQUEST)
            assert status == 200
            assert headers["X-Provider-Used"] == "p0"
            assert float(headers["X-Cost-Usd"]) == 0

    gateway = None
    asyncio.run(scenario())
    assert calls == ["p0.test", "p0.test"]


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
