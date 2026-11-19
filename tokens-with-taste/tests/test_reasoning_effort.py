import json

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup


@pytest.mark.parametrize("tools", [False, True])
@pytest.mark.parametrize("nvidia_status,expected", [(200, ["google", "nvidia"]), (503, ["google", "nvidia", "nebius"]), (429, ["google", "nvidia", "nebius"])])
def test_glm_effort_and_free_nvidia_order_on_upstream_wire(store, monkeypatch, tools, nvidia_status, expected):
    config = setup(store, monkeypatch, count=3)
    models = store.models()
    ids = ("google", "nvidia", "nebius")
    names = ("chat", "z-ai/glm-5.3-flash", "zai-org/GLM-5.3-Flash")
    for index, (provider, model) in enumerate(zip(config, models)):
        store.replace_models(provider["id"], [])
        provider.update(id=ids[index], free_only=index < 2)
        model.update(provider=ids[index], id=names[index], free=index < 2,
                     input_price=0 if index < 2 else .001, output_price=0 if index < 2 else .002)
        store.replace_models(ids[index], [model])
    body = {**REQUEST, "max_tokens": 8192,
            "provider_models": dict(zip(ids[1:], names[1:])),
            "provider_reasoning_effort": {"nvidia": "low", "nebius": "low"}}
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]
    sent = []

    def handler(request):
        index = int(request.url.host[1])
        provider = ids[index]
        sent.append(provider)
        payload = json.loads(request.content)
        assert "provider_models" not in payload
        assert "provider_reasoning_effort" not in payload
        assert payload["model"] == names[index]
        assert payload["max_tokens"] == 8192
        if provider == "google":
            assert "reasoning_effort" not in payload
            assert "chat_template_kwargs" not in payload
        else:
            assert payload["reasoning_effort"] == "low"
            assert payload["chat_template_kwargs"] == {"reasoning_effort": "low", "clear_thinking": True}
        status = 503 if provider == "google" else nvidia_status if provider == "nvidia" else 200
        return httpx.Response(status, json=reply(), headers={"Retry-After": "120"})

    assert run(store, config, handler, body=body)[1] == 200
    assert sent == expected


@pytest.mark.parametrize("efforts", [None, [], {"unknown": "low"}, {"p0": "none"}, {"p0": {}}, {"p0": 1}])
def test_invalid_effort_fails_without_dispatch(store, monkeypatch, efforts):
    config = setup(store, monkeypatch)

    def handler(request):
        pytest.fail("invalid effort must not dispatch")

    _, status, headers = run(store, config, handler, body={**REQUEST, "provider_reasoning_effort": efforts})
    assert status == 400
    assert headers["X-Cost-Usd"] == "0"


def test_empty_effort_preserves_ordinary_request(store, monkeypatch):
    config = setup(store, monkeypatch)

    def handler(request):
        body = json.loads(request.content)
        assert "provider_reasoning_effort" not in body
        assert "reasoning_effort" not in body
        assert "chat_template_kwargs" not in body
        return httpx.Response(200, json=reply())

    assert run(store, config, handler, body={**REQUEST, "provider_reasoning_effort": {}})[1] == 200
