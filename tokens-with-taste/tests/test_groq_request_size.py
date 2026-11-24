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


TPM_413 = (
    "Request too large for model `openai/gpt-oss-120b` in organization `org_x` "
    "service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 8734, "
    "please reduce your message size and try again."
)
TPM_429 = (
    "Rate limit reached for model `openai/gpt-oss-120b` in organization `org_x` "
    "service tier `on_demand` on tokens per minute (TPM): Limit 8000, Used 5845, "
    "Requested 6776. Please try again in 34.6575s."
)


def groq_error(status, message):
    return httpx.Response(status, json={"error": {"message": message}})


def test_413_body_limit_skips_larger_requests_before_sending(store, monkeypatch):
    configuration = groq_first(store, monkeypatch, tpm=None)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "groq.test":
            return groq_error(413, TPM_413)
        return httpx.Response(200, json=reply())

    # The first request is rejected with "Limit 8000"; a larger one is then
    # skipped without being sent, and one within the limit is still sent.
    _, bigger, _ = run_all(
        store, configuration, handler, [big(36000), big(80000), big(28000)]
    )
    assert hosts == ["groq.test", "other.test", "other.test", "groq.test", "other.test"]
    skipped = store.trace(bigger[2]["X-Trace-Id"])["attempts"][0]
    assert skipped["called"] is False and "8000 TPM" in skipped["reason"]


def test_413_body_limit_skips_size_below_first_rejection(store, monkeypatch):
    configuration = groq_first(store, monkeypatch, tpm=None)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "groq.test":
            return groq_error(413, TPM_413)
        return httpx.Response(200, json=reply())

    # Rejected at ~20000 tokens (estimate), but Groq said the limit is 8000:
    # a ~12000 token request is below the first 413 yet must be skipped.
    run_all(store, configuration, handler, [big(80000), big(48000)])
    assert hosts == ["groq.test", "other.test", "other.test"]


def test_tpm_429_cools_groq_for_stated_wait(store, monkeypatch):
    configuration = groq_first(store, monkeypatch, tpm=None)
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.host == "groq.test":
            return groq_error(429, TPM_429)
        return httpx.Response(200, json=reply())

    first, _ = run_all(store, configuration, handler, [big(40), big(40)])
    attempt = store.trace(first[2]["X-Trace-Id"])["attempts"][0]
    assert attempt["reason"] == "upstream HTTP 429; cooldown 35s"
    assert hosts == ["groq.test", "other.test", "other.test"]


def test_tpm_429_within_limit_keeps_default_cooldown(store, monkeypatch):
    configuration = groq_first(store, monkeypatch, tpm=None)
    message = TPM_429.replace("Used 5845", "Used 100").replace(
        "Requested 6776", "Requested 200"
    )

    def handler(request):
        if request.url.host == "groq.test":
            return groq_error(429, message)
        return httpx.Response(200, json=reply())

    [(_, _, headers)] = run_all(store, configuration, handler, [big(40)])
    attempt = store.trace(headers["X-Trace-Id"])["attempts"][0]
    assert attempt["reason"] == "upstream HTTP 429; cooldown 60s"
