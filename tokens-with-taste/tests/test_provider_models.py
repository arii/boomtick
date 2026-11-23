import json

import httpx
import pytest
from test_gateway import REQUEST, reply, run, setup


@pytest.mark.parametrize(
    "free_status,expected",
    [(200, ["chat"]), (503, ["chat", "glm"]), (429, ["chat", "glm"])],
)
def test_provider_selection_preserves_free_first(
    store, monkeypatch, free_status, expected
):
    config = setup(store, monkeypatch)
    free, paid = store.models()
    free.update(free=True, input_price=0, output_price=0)
    config[0]["free_only"] = True
    store.replace_models("p0", [free])
    store.replace_models("p1", [paid, {**paid, "id": "glm"}])
    sent = []

    def handler(request):
        body = json.loads(request.content)
        assert "provider_models" not in body
        sent.append(body["model"])
        if request.url.host == "p0.test":
            return httpx.Response(
                free_status, headers={"Retry-After": "120"}, json=reply()
            )
        return httpx.Response(200, json=reply())

    _, status, headers = run(
        store, config, handler, body={**REQUEST, "provider_models": {"p1": "glm"}}
    )
    assert status == 200
    assert sent == expected
    assert store.trace(headers["X-Trace-Id"])["request"]["provider_models"] == {
        "p1": "glm"
    }


@pytest.mark.parametrize("selection", [{}, {"p1": "missing"}])
def test_empty_or_unavailable_selection(store, monkeypatch, selection):
    config = setup(store, monkeypatch)
    sent = []

    def handler(request):
        sent.append(request.url.host)
        return httpx.Response(503, json={})

    _, status, headers = run(
        store, config, handler, body={**REQUEST, "provider_models": selection}
    )
    assert status == 502
    assert sent == (["p0.test", "p1.test"] if not selection else ["p0.test"])
    assert store.trace(headers["X-Trace-Id"])["attempts"][-1]["called"] is (
        not selection
    )


@pytest.mark.parametrize(
    "selection", [None, [], "glm", {"unknown": "glm"}, {"p1": ""}, {"p1": 3}]
)
def test_invalid_provider_selection_is_rejected(store, monkeypatch, selection):
    config = setup(store, monkeypatch)

    def handler(request):
        pytest.fail("invalid selection must not dispatch upstream")

    _, status, headers = run(
        store, config, handler, body={**REQUEST, "provider_models": selection}
    )
    assert status == 400
    assert headers["X-Cost-Usd"] == "0"
