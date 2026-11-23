"""Groq 413s: skip requests over the model TPM limit and never retry a size Groq rejected."""

import asyncio

import httpx
from test_gateway import REQUEST, reply, setup
from twt.gateway import Gateway, estimate_request_tokens


def groq_first(store, monkeypatch, tpm=8000):
    configuration = setup(store, monkeypatch, provider_ids=("groq", "other"))
    models = store.models()
    for m in models:
        if m["provider"] == "groq":
            m["tpm"] = tpm
    store.replace_models("groq", [m for m in models if m["provider"] == "groq"])
    return configuration


def big(chars):
    return {**REQUEST, "messages": [{"role": "user", "content": "x" * chars}]}


def run_all(store, configuration, handler, bodies):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = Gateway(store, client, configuration)
            return [await gateway.complete(body) for body in bodies]

    return asyncio.run(scenario())


def test_oversized_request_skips_groq_without_sending(store, monkeypatch):
    configuration = groq_first(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json=reply())

    [(_, status, headers)] = run_all(store, configuration, handler, [big(40000)])
    assert status == 200 and headers["X-Provider-Used"] == "other"
    assert hosts == ["other.test"]
    groq = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert groq["called"] is False
    assert (
        groq["reason"].startswith("request too large") and "8000 TPM" in groq["reason"]
    )


def test_request_within_limit_still_goes_to_groq(store, monkeypatch):
    configuration = groq_first(store, monkeypatch)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json=reply())

    [(_, status, _)] = run_all(store, configuration, handler, [big(4000)])
    assert status == 200 and hosts == ["groq.test"]


def test_max_tokens_counts_toward_size():
    assert estimate_request_tokens({**big(400), "max_tokens": 500}) > 500


def test_actual_413_is_not_retried_for_that_size(store, monkeypatch):
    configuration = groq_first(store, monkeypatch, tpm=None)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "groq.test":
            return httpx.Response(
                413,
                json={
                    "error": {
                        "message": "Request too large",
                        "code": "rate_limit_exceeded",
                    }
                },
            )
        return httpx.Response(200, json=reply())

    first, second, small = run_all(
        store, configuration, handler, [big(40000), big(40000), big(40)]
    )
    assert first[1] == 200 and first[2]["X-Provider-Used"] == "other"
    attempts = store.trace(first[2]["X-Trace-Id"])["attempts"]
    assert (
        attempts[0]["called"]
        and attempts[0]["reason"] == "upstream HTTP 413 request too large"
    )
    # Same size: Groq is not called again. Smaller request: Groq is tried again.
    assert hosts == ["groq.test", "other.test", "other.test", "groq.test", "other.test"]
    skipped = store.trace(second[2]["X-Trace-Id"])["attempts"][0]
    assert skipped["called"] is False and "HTTP 413" in skipped["reason"]
    assert small[2]["X-Provider-Used"] == "other"
