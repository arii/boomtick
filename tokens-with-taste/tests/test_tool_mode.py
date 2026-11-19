import json

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup


@pytest.mark.parametrize("tools,explicit,thinking", [(True, None, False), (True, True, True), (False, None, None)])
def test_nemotron_tools_use_documented_non_reasoning_mode(store, monkeypatch, tools, explicit, thinking):
    configuration = setup(store, monkeypatch, count=1)
    provider = configuration[0]
    provider["id"] = "nebius"
    monkeypatch.setenv("NEBIUS_API_KEY", "test")
    model = store.models()[0]
    model.update(provider="nebius", id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    store.replace_models("p0", [])
    store.replace_models("nebius", [model])
    body = dict(REQUEST)
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]
    if explicit is not None:
        body["chat_template_kwargs"] = {"enable_thinking": explicit, "other": True}

    def handler(request):
        payload = json.loads(request.content)
        assert payload.get("chat_template_kwargs", {}).get("enable_thinking") is thinking
        if explicit is not None:
            assert payload["chat_template_kwargs"]["other"] is True
        return httpx.Response(200, json=reply())

    assert run(store, configuration, handler, body=body)[1] == 200
