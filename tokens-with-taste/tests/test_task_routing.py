import asyncio
import json

import httpx
from test_gateway import reply, setup
from twt.gateway import bound_tool_calls, create_app


def test_models_advertises_task_routing_and_metadata(store, monkeypatch):
    config = setup(store, monkeypatch, 2)
    models = store.models()
    models[0].update(
        free=True,
        tools=True,
        context_length=32768,
        max_output_tokens=4096,
        input_price=0.0,
        output_price=0.0,
    )
    models[1].update(
        id="batch-model:batch",
        chat=False,
    )
    store.replace_models("p0", models)

    app = create_app(
        store,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/v1/models")
            assert resp.status_code == 200
            data = resp.json()
            assert "task_routing" in data["features"]
            assert "request_cost_ceiling" in data["features"]
            items = data["data"]
            # The batch model must be excluded from /v1/models
            assert not any(m["id"].endswith(":batch") for m in items)
            # Metadata fields are present
            first = next(m for m in items if m["provider"] == "p0")
            assert first["free"] is True
            assert first["tools"] is True
            assert first["context_length"] == 32768
            assert first["input_price"] == 0.0

            cat_resp = await client.get("/v1/catalog")
            assert cat_resp.status_code == 200
            cat_data = cat_resp.json()
            assert not any(m["id"].endswith(":batch") for m in cat_data["data"])

    asyncio.run(scenario())


def test_bound_tool_calls_dedupes_and_bounds_fanout():
    # Duplicate calls and large burst (20 calls)
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{i % 5}",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"file": f"f_{i % 5}.py"}),
                            },
                        }
                        for i in range(25)
                    ],
                }
            }
        ]
    }
    bound_tool_calls(payload, max_fanout=16)
    calls = payload["choices"][0]["message"]["tool_calls"]
    # 5 distinct files: duplicates must be eliminated, leaving exactly 5 calls
    assert len(calls) == 5
    args = [json.loads(c["function"]["arguments"])["file"] for c in calls]
    assert args == [f"f_{i}.py" for i in range(5)]


def test_trace_records_routing_decision(store, monkeypatch):
    from test_gateway import run

    config = setup(store, monkeypatch, 1)

    decision = {
        "rule": "rank:cheapest_meeting_floor",
        "tier": "strong",
        "features": {"file_count": 2},
    }

    _, status, headers = run(
        store,
        config,
        lambda _: httpx.Response(200, json=reply()),
        body={
            "model": "p0/chat",
            "messages": [{"role": "user", "content": "hi"}],
            "routing_decision": decision,
        },
    )
    assert status == 200
    trace_id = headers["X-Trace-Id"]
    trace = store.trace(trace_id)
    assert trace["routing_decision"] == decision
