import asyncio
import json
import os
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .audit import flags_for, usage
from .catalog import (
    base_url,
    catalog_models,
    configured_providers,
    disabled_providers,
    headers,
    missing,
    ollama_running_context,
    require_local_ollama,
    providers as hosted_providers,
    OLLAMA_URL,
)
from .costs import cost_upper_bound
from .store import Store, now


def loopback_origin(origin):
    try:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return False
        if parsed.port == 0:
            return False
        return parsed.hostname == "localhost" or ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def retry_seconds(value):
    try:
        seconds = float(value)
        return max(0, seconds) if seconds < float("inf") else 60
    except (TypeError, ValueError):
        try:
            return max(
                0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            )
        except (TypeError, ValueError, OverflowError):
            return 60


OVERLOAD_STATUSES = (503, 529)
# 5xx statuses that signal provider unavailability. A 500 or 501 can come from one bad request, so it sets no cooldown.
OVERLOAD_COOLDOWN_STATUSES = (502, 503, 504, 529)
OVERLOAD_COOLDOWN_DEFAULT_SECONDS = 30
OVERLOAD_COOLDOWN_MAX_SECONDS = 300
MODEL_UNAVAILABLE_STATUSES = (404, 410)
MODEL_UNAVAILABLE_COOLDOWN_SECONDS = 300
GOOGLE_SIGNATURE_CACHE_SIZE = 1024
# Blended USD per token used only to order paid models: input-heavy agent traffic.
BLENDED_INPUT_WEIGHT = 0.8
BLENDED_OUTPUT_WEIGHT = 0.2


def blended_price(model):
    if model["input_price"] is None or model["output_price"] is None:
        return float("inf")
    return (
        BLENDED_INPUT_WEIGHT * model["input_price"]
        + BLENDED_OUTPUT_WEIGHT * model["output_price"]
    )


def model_rank(model):
    return (
        not model["free"],
        blended_price(model),
        model["input_price"] if model["input_price"] is not None else float("inf"),
        model["id"],
    )


def overload_cooldown(response):
    """Bounded cooldown seconds after an overload status: Retry-After when sent, else a short default, capped."""
    if response.headers.get("Retry-After") is None:
        return OVERLOAD_COOLDOWN_DEFAULT_SECONDS
    return min(
        OVERLOAD_COOLDOWN_MAX_SECONDS, retry_seconds(response.headers["Retry-After"])
    )


def order_providers(providers, catalog, body, privacy):
    """Free models first across providers, then paid by blended price, unknown price last.
    Ties keep configured provider order. Providers skipped without a call (disabled, missing
    credentials, strict privacy, no eligible model) keep their configured position."""

    def callable_provider(provider):
        return (
            bool(eligible_models(catalog, provider, body))
            and provider["id"] not in disabled_providers()
            and not missing(provider)
            and not (
                privacy == "strict"
                and (
                    not provider["strict"]
                    or provider["trains_on_free_tier"] is not False
                )
            )
        )

    def rank(provider):
        best = model_rank(min(eligible_models(catalog, provider, body), key=model_rank))
        return (
            (0, 0)
            if best[0] is False
            else ((1, best[1]) if best[1] != float("inf") else (2, 0))
        )

    ranked = iter(sorted([p for p in providers if callable_provider(p)], key=rank))
    return [next(ranked) if callable_provider(p) else p for p in providers]


def trace_headers(trace):
    return {
        "X-Trace-Id": trace["trace_id"],
        "X-Provider-Used": trace["provider"] or "none",
        "X-Cost-Usd": str(trace["cost_usd"])
        if trace["cost_usd"] is not None
        else "unknown",
        "X-Audit-Flags": ",".join(trace["flags"]),
        "X-Billing-Status": trace.get("billing_status", "unknown"),
    }


def _reset_delay(value):
    """Seconds until an epoch-milliseconds reset time, or None if the value is missing or malformed."""
    try:
        return int(value) / 1000 - time.time()
    except (ValueError, TypeError, OverflowError):
        return None


MAX_RESET_HEADER_SECONDS = 86400


def upstream_cooldown(response, payload, openrouter=False):
    delay = retry_seconds(response.headers.get("Retry-After"))
    if openrouter:
        # OpenRouter's own free-model 429 reports its quota reset in headers only.
        reset = _reset_delay(response.headers.get("X-RateLimit-Reset"))
        if reset is not None and reset > 0:
            delay = max(delay, min(reset, MAX_RESET_HEADER_SECONDS))
    error = payload.get("error")
    metadata = error.get("metadata") if isinstance(error, dict) else None
    if (
        isinstance(metadata, dict)
        and metadata.get("limit_source") == "openrouter_free_tier_daily"
    ):
        fields = metadata.get("headers")
        if isinstance(fields, dict):
            reset = _reset_delay(fields.get("X-RateLimit-Reset"))
            if reset is not None:
                delay = max(delay, reset)
    return delay


TPM_LIMIT = re.compile(
    r"tokens per minute \(TPM\): Limit (\d+)(?:, Used (\d+), Requested (\d+))?"
)
TRY_AGAIN = re.compile(r"try again in (?:(\d+)m)?(?:(\d+(?:\.\d+)?)(ms|s))?")


def tpm_details(payload):
    """(limit, used, requested, wait seconds) from a Groq TPM error body; None when absent."""
    error = payload.get("error")
    message = error.get("message") if isinstance(error, dict) else None
    match = TPM_LIMIT.search(message) if isinstance(message, str) else None
    if not match:
        return None
    limit, used, requested = (int(g) if g else None for g in match.groups())
    wait = 0.0
    again = TRY_AGAIN.search(message)
    if again:
        minutes, amount, unit = again.groups()
        wait = int(minutes or 0) * 60 + float(amount or 0) / (
            1000 if unit == "ms" else 1
        )
    return limit, used, requested, wait


def error_response(message, status):
    return JSONResponse({"error": {"message": message}}, status_code=status)


def estimate_request_tokens(body):
    """Rough upper-ish token count of what a provider bills against its TPM limit.

    Uses ~4 characters per token over the serialized prompt fields plus the
    requested output cap, which Groq counts toward the request size.
    """
    prompt = {k: body[k] for k in ("messages", "tools", "response_format") if k in body}
    chars = len(json.dumps(prompt, default=str, ensure_ascii=False))
    output = max(
        (
            v
            for v in (body.get("max_tokens"), body.get("max_completion_tokens"))
            if type(v) is int
        ),
        default=0,
    )
    return -(-chars // 4) + output


def eligible_models(catalog, provider, body):
    candidates = [m for m in catalog if m["provider"] == provider["id"] and m["chat"]]
    requested = body.get("model", "default")
    strong_route = requested == "route:strong"
    default_route = requested in ("default", "route:default") or strong_route
    if strong_route:
        requested = (
            provider.get("strong_model") or provider.get("local_model") or "default"
        )
    elif default_route:
        requested = body.get("provider_models", {}).get(provider["id"], requested)
    if requested not in ("default", "route:default"):
        candidates = [
            m
            for m in candidates
            if requested in (m["id"], f"{provider['id']}/{m['id']}")
        ]
    if default_route and provider.get("free_only"):
        candidates = [m for m in candidates if m["free"]]
    if body.get("tools"):
        candidates = [m for m in candidates if m["tools"]]
    if body.get("response_format") and body["response_format"].get("type") != "text":
        capability = (
            "json_schema"
            if body["response_format"].get("type") == "json_schema"
            else "json"
        )
        candidates = [m for m in candidates if m.get(capability)]
    return candidates


def payment_required(payload):
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    return any(
        isinstance(value := error.get(field), str)
        and value.upper() in {"PAYMENT_REQUIRED", "PAYMENT_METHOD_REQUIRED"}
        for field in ("code", "type")
    )


def google_tool_signature(call):
    extra = call.get("extra_content")
    google = extra.get("google") if isinstance(extra, dict) else None
    signature = google.get("thought_signature") if isinstance(google, dict) else None
    return signature if isinstance(signature, str) and signature.strip() else None


def google_signature_error(payload):
    raw = payload.get("raw_payload")
    for row in raw if isinstance(raw, list) else [payload]:
        if not isinstance(row, dict):
            continue
        error = row.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        if any(
            isinstance(value, str) and "thought_signature" in value.casefold()
            for value in (message, row.get("raw_text"))
        ):
            return True
    return False


class Gateway:
    def __init__(
        self,
        store,
        client,
        configuration=None,
        clock=time.monotonic,
        sleep=asyncio.sleep,
        free_wait_seconds=None,
    ):
        disabled_providers()  # Reject misspelled exclusions before serving requests.
        self.store = store
        self.client = client
        self.providers = (
            configuration if configuration is not None else configured_providers()
        )
        # The strong profile can mix local and hosted models without changing
        # the existing local-only/default route configuration.
        self.strong_providers = (
            configuration
            if configuration is not None
            else self.providers
            if os.environ.get("TWT_OLLAMA_MODEL")
            else hosted_providers()
        )
        self.clock = clock
        self.calls = defaultdict(deque)
        self.cooldowns = {}
        self.transport_cooldowns = {}
        self.overload_cooldowns = {}
        self.unavailable_cooldowns = {}
        # (provider, model) -> smallest estimated size upstream rejected with HTTP 413.
        self.too_large = {}
        # (provider, model) -> TPM limit Groq stated in an error body.
        self.tpm_limits = {}
        self.google_signatures = {}
        self.lock = asyncio.Lock()
        self.sleep = sleep
        if free_wait_seconds is None:
            free_wait_seconds = float(os.environ.get("TWT_FREE_WAIT_SECONDS", "60"))
            if not 0 <= free_wait_seconds <= 60:
                raise ValueError("TWT_FREE_WAIT_SECONDS must be between 0 and 60")
        self.free_wait_seconds = max(0, min(60, free_wait_seconds))
        self.cancelled = set()

    def google_tool_history(self, messages, session):
        # Gemini requires a signature on the first call of each parallel batch.
        # Restore Google's metadata that OpenAI clients may drop; skip Google
        # rather than passing through foreign or unverifiable tool history.
        history = []
        for message in messages:
            calls = (
                message.get("tool_calls")
                if isinstance(message, dict) and message.get("role") == "assistant"
                else None
            )
            if not isinstance(calls, list) or not calls:
                history.append(message)
                continue
            restored = []
            for call in calls:
                call_id = call.get("id") if isinstance(call, dict) else None
                if (
                    session
                    and isinstance(call_id, str)
                    and not google_tool_signature(call)
                    and (signature := self.google_signatures.get((session, call_id)))
                ):
                    extra = call.get("extra_content")
                    extra = dict(extra) if isinstance(extra, dict) else {}
                    google = extra.get("google")
                    google = dict(google) if isinstance(google, dict) else {}
                    extra["google"] = {**google, "thought_signature": signature}
                    call = {**call, "extra_content": extra}
                restored.append(call)
            if not isinstance(restored[0], dict) or not google_tool_signature(
                restored[0]
            ):
                return None
            history.append({**message, "tool_calls": restored})
        return history

    def remember_google_signatures(self, payload, session):
        if not session:
            return
        for choice in payload["choices"]:
            calls = choice["message"].get("tool_calls")
            for call in calls if isinstance(calls, list) else []:
                call_id = call.get("id") if isinstance(call, dict) else None
                if isinstance(call_id, str) and (
                    signature := google_tool_signature(call)
                ):
                    self.google_signatures[session, call_id] = signature
                    if len(self.google_signatures) > GOOGLE_SIGNATURE_CACHE_SIZE:
                        self.google_signatures.pop(next(iter(self.google_signatures)))

    def model_block(self, provider, model, size):
        """Return (reason, hard) when per-model state rules the model out, else None.

        Read-only. Rate waits (RPM, Retry-After, transport) stay with reserve().
        """
        key = (provider["id"], model["id"])
        limit = self.tpm_limits.get(key, model.get("tpm"))
        if limit is not None and size > limit:
            return (
                f"request too large: ~{size} tokens exceeds {limit} TPM limit",
                False,
            )
        if key in self.too_large and size >= self.too_large[key]:
            return (
                f"request too large: HTTP 413 seen at ~{self.too_large[key]} tokens",
                False,
            )
        current = self.clock()
        if self.unavailable_cooldowns.get(key, 0) > current:
            return "model unavailable cooldown", True
        if self.overload_cooldowns.get(key, 0) > current:
            return "overload cooldown", True
        return None

    async def reserve(self, model, key, budget, remaining, *, defer_retry_after=False):
        waited = 0
        while True:
            async with self.lock:
                if (
                    budget is not None
                    and not model["free"]
                    and (
                        self.store.spend_today() >= budget
                        or model["input_price"] is None
                        or model["output_price"] is None
                    )
                ):
                    return (
                        "daily budget reached or paid model price unknown",
                        waited,
                        None,
                    )
                current = self.clock()
                if self.unavailable_cooldowns.get(key, 0) > current:
                    return "model unavailable cooldown", waited, None
                window = self.calls[key]
                while window and window[0] <= current - 60:
                    window.popleft()
                if self.overload_cooldowns.get(key, 0) > current:
                    return "overload cooldown", waited, None
                transport_until = self.transport_cooldowns.get(key, 0)
                retry_until = self.cooldowns.get(key, 0)
                if defer_retry_after and retry_until > current:
                    reason = (
                        "transport failure cooldown"
                        if transport_until > current
                        else "Retry-After cooldown"
                    )
                    return reason, waited, None
                delay = max(0, retry_until - current, transport_until - current)
                reason = (
                    "transport failure cooldown"
                    if transport_until > retry_until
                    else "Retry-After cooldown"
                )
                if model.get("rpm") is not None and len(window) >= model["rpm"]:
                    delay = (
                        max(delay, window[0] + 60 - current) if window else float("inf")
                    )
                    reason = "local RPM limit"
                if not delay:
                    window.append(current)
                    return None, waited, current
            if not model["free"] or delay > remaining - waited:
                return reason, waited, None
            await self.sleep(delay)
            waited += delay

    async def complete(
        self, body, privacy="standard", session=None, trace_id=None, disconnected=None
    ):
        trace_id = trace_id or str(uuid.uuid4())
        if not self.store.reserve_trace(trace_id):
            return (
                {"error": {"message": "Trace ID already used"}},
                409,
                {"X-Cost-Usd": "0"},
            )
        dispatch = {"started": False}
        try:
            return await self._complete(
                body, privacy, session, trace_id, disconnected, dispatch
            )
        except BaseException:
            if not dispatch["started"]:
                self.store.release_trace(trace_id)
            raise

    async def _complete(self, body, privacy, session, trace_id, disconnected, dispatch):
        started = self.clock()
        original_body = dict(body)
        body = {**body, "stream": False}
        body.pop("stream_options", None)
        trace = {
            "trace_id": trace_id or str(uuid.uuid4()),
            "timestamp": now(),
            "route": body.get("model", "default"),
            "privacy": privacy,
            "session_id": session,
            "provider": None,
            "model": None,
            "attempts": [],
            "http_status": 503,
            "latency_ms": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "visible_tokens": None,
            "cost_usd": None,
            "known_cost_usd": 0,
            "cost_complete": False,
            "flags": [],
            "request": original_body,
            "response": None,
        }
        selections = body.get("provider_models", {})
        if (
            not isinstance(selections, dict)
            or any(
                key not in {p["id"] for p in self.providers}
                or not isinstance(value, str)
                or not value.strip()
                for key, value in selections.items()
            )
            or (
                selections
                and body.get("model", "default") not in ("default", "route:default")
            )
        ):
            trace.update(
                http_status=400,
                cost_usd=0,
                cost_complete=True,
                response={
                    "error": {
                        "message": "provider_models must map configured providers to nonempty model IDs on the default route"
                    }
                },
            )
            self.store.save_trace(trace)
            return trace["response"], 400, trace_headers(trace)
        efforts = body.get("provider_reasoning_effort", {})
        if (
            not isinstance(efforts, dict)
            or any(
                key not in {p["id"] for p in self.providers}
                or value not in ("low", "high", "max")
                for key, value in efforts.items()
            )
            or (
                efforts
                and body.get("model", "default") not in ("default", "route:default")
            )
        ):
            trace.update(
                http_status=400,
                cost_usd=0,
                cost_complete=True,
                response={
                    "error": {
                        "message": "provider_reasoning_effort must map configured providers to low/high/max on the default route"
                    }
                },
            )
            self.store.save_trace(trace)
            return trace["response"], 400, trace_headers(trace)
        route_providers = self.providers
        if body.get("model") == "route:strong":
            try:
                selections = json.loads(os.environ.get("TWT_STRONG_MODELS", "{}"))
                if not isinstance(selections, dict) or any(
                    key not in {p["id"] for p in self.strong_providers}
                    or not isinstance(value, str)
                    or not value.strip()
                    for key, value in selections.items()
                ):
                    raise ValueError(
                        "expected configured provider IDs and nonempty model IDs"
                    )
                route_providers = [
                    {
                        **provider,
                        "strong_model": selections.get(
                            provider["id"], provider.get("strong_model")
                        ),
                    }
                    for provider in self.strong_providers
                ]
                local_model = os.environ.get("TWT_OLLAMA_STRONG_MODEL")
                if local_model:
                    route_providers = [
                        {
                            "id": "ollama",
                            "base_url": f"{OLLAMA_URL}/v1",
                            "local_model": local_model,
                            "strong_model": local_model,
                            "strict": True,
                            "trains_on_free_tier": False,
                        }
                    ] + [p for p in route_providers if p["id"] != "ollama"]
            except (ValueError, TypeError) as error:
                trace.update(
                    http_status=400,
                    cost_usd=0,
                    cost_complete=True,
                    response={
                        "error": {
                            "message": f"Invalid strong routing configuration: {error}"
                        }
                    },
                )
                self.store.save_trace(trace)
                return trace["response"], 400, trace_headers(trace)
            allowed = {p["id"] for p in route_providers} - disabled_providers()
            catalog = [m for m in self.store.models() if m["provider"] in allowed]
        else:
            catalog = catalog_models(self.store, self.providers)
        absent = set()
        routed = trace["route"] in ("default", "route:default", "route:strong")
        response_payload = None
        context = None
        budget = os.environ.get("TWT_DAILY_BUDGET_USD")
        if budget is not None:
            try:
                budget = float(budget)
                if not 0 <= budget < float("inf"):
                    raise ValueError
            except ValueError:
                trace["response"] = {
                    "error": {
                        "message": "TWT_DAILY_BUDGET_USD must be a finite nonnegative number"
                    }
                }
                trace["http_status"] = 500
                self.store.save_trace(trace)
                return trace["response"], 500, trace_headers(trace)
        ordered = order_providers(route_providers, catalog, body, privacy)
        if body.get("model") == "route:strong":
            # Preserve free-provider order and all existing admission/budget checks.
            # Local is first, Nebius is last, even when price ranking ties.
            ordered.sort(
                key=lambda provider: (
                    0
                    if "local_model" in provider
                    else 3
                    if provider["id"] == "nebius"
                    else 1
                    if any(m["free"] for m in eligible_models(catalog, provider, body))
                    else 2
                )
            )
        pending = deque(ordered)
        retried = set()
        rate_deadlines = []
        hard_failure = False
        names_models = set()
        replayed = False
        waited = 0
        while pending or (
            routed and rate_deadlines and not hard_failure and not replayed
        ):
            if trace["trace_id"] in self.cancelled or (
                disconnected and await disconnected()
            ):
                response_payload = {
                    "error": {
                        "message": "Client disconnected",
                        "type": "client_disconnected",
                    }
                }
                trace["http_status"] = 499
                break
            if not pending:
                delay = min(
                    max(0, min(rate_deadlines) - self.clock()),
                    self.free_wait_seconds - waited,
                )
                if delay > 0:
                    await self.sleep(delay)
                    waited += delay
                pending.extend(ordered)
                replayed = True
                continue
            provider = pending.popleft()
            attempt = {
                "provider": provider["id"],
                "model": None,
                "called": False,
                "timestamp": now(),
                "reason": "",
                "http_status": None,
                "latency_ms": 0,
                "request": None,
                "response": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "reasoning_tokens": None,
                "cost_usd": None,
            }
            trace["attempts"].append(attempt)
            if provider["id"] in disabled_providers():
                attempt["reason"] = "disabled by account policy"
                continue
            missing_keys = missing(provider)
            if missing_keys:
                absent.update(missing_keys)
                attempt["reason"] = "missing credentials: " + ", ".join(missing_keys)
                continue
            if privacy == "strict" and (
                not provider["strict"] or provider["trains_on_free_tier"] is not False
            ):
                attempt["reason"] = "strict privacy excluded"
                continue
            candidates = eligible_models(catalog, provider, body)
            if not candidates:
                attempt["reason"] = (
                    "no synced eligible chat model matching requested model/free-tier/tools/JSON capabilities; run twt sync"
                )
                continue
            size = estimate_request_tokens(body)
            ranked = sorted(candidates, key=model_rank)
            # Fall back only within the top model's free/paid class so a provider
            # ordered as free never reaches a paid model ahead of other free providers.
            ranked = [m for m in ranked if m["free"] == ranked[0]["free"]]
            attempt["model"] = ranked[0]["id"]
            google_history = None
            if provider["id"] == "google":
                google_history = self.google_tool_history(
                    body.get("messages", []), session
                )
                if google_history is None:
                    attempt["reason"] = "Google tool history missing thought_signature"
                    continue
            if "local_model" in provider:
                try:
                    await require_local_ollama(self.client)
                except (httpx.HTTPError, ValueError):
                    attempt["reason"] = (
                        "local Ollama unavailable or cloud not disabled; check OLLAMA_NO_CLOUD=1"
                    )
                    # The probe sends no request, so this is a skip like a missing credential.
                    continue
            blocked = []
            model = None
            for candidate in ranked:
                block = self.model_block(provider, candidate, size)
                if block is None:
                    model = candidate
                    break
                blocked.append((candidate, block))
            if model is None:
                if len(blocked) == 1:
                    attempt["reason"] = blocked[0][1][0]
                else:
                    attempt["reason"] = "; ".join(
                        f"{candidate['id']}: {reason}"
                        for candidate, (reason, _) in blocked
                    )
                    names_models.add(id(attempt))
                if any(hard for _, (_, hard) in blocked):
                    hard_failure = True
                continue
            attempt["model"] = model["id"]
            key = (provider["id"], model["id"])
            reason, delay, reservation = await self.reserve(
                model,
                key,
                budget,
                self.free_wait_seconds - waited,
                defer_retry_after=routed,
            )
            waited += delay
            if reason:
                attempt["reason"] = reason
                if reason == "Retry-After cooldown":
                    rate_deadlines.append(self.cooldowns[key])
                elif reason not in (
                    "daily budget reached or paid model price unknown",
                    "local RPM limit",
                ):
                    hard_failure = True
                continue
            ready = False
            try:
                cancelled = trace["trace_id"] in self.cancelled or (
                    disconnected and await disconnected()
                )
                ready = not cancelled
            finally:
                if not ready:
                    async with self.lock:
                        window = self.calls[key]
                        if reservation in window:
                            window.remove(reservation)
            if cancelled:
                attempt["reason"] = "client disconnected before upstream dispatch"
                response_payload = {
                    "error": {
                        "message": "Client disconnected",
                        "type": "client_disconnected",
                    }
                }
                trace["http_status"] = 499
                break
            attempt["called"] = True
            if (
                model["free"]
                and model["input_price"] == 0
                and model["output_price"] == 0
            ):
                attempt["cost_usd"] = 0.0
            trace["provider"] = provider["id"]
            trace["model"] = model["id"]
            attempt["request"] = {**body, "model": model["id"]}
            if google_history is not None:
                attempt["request"]["messages"] = google_history
            attempt["request"].pop("provider_models", None)
            attempt["request"].pop("provider_reasoning_effort", None)
            if provider["id"] in efforts:
                attempt["request"]["reasoning_effort"] = efforts[provider["id"]]
                if "glm-5.3" in model["id"].lower():
                    attempt["request"]["chat_template_kwargs"] = {
                        **body.get("chat_template_kwargs", {}),
                        "reasoning_effort": efforts[provider["id"]],
                        "clear_thinking": True,
                    }
            if (
                provider["id"] == "nebius"
                and model["id"].startswith("nvidia/NVIDIA-Nemotron-3-")
                and body.get("tools")
            ):
                attempt["request"]["chat_template_kwargs"] = {
                    "enable_thinking": False,
                    **body.get("chat_template_kwargs", {}),
                }
            request_start = self.clock()
            try:
                dispatch["started"] = True
                response = await self.client.post(
                    base_url(provider) + "/chat/completions",
                    headers=headers(provider),
                    json=attempt["request"],
                )
                attempt["http_status"] = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    payload = {
                        "error": {"message": "Upstream returned a non-JSON response"},
                        "raw_text": response.text,
                    }
                if not isinstance(payload, dict):
                    payload = {
                        "error": {"message": "Upstream returned a non-object response"},
                        "raw_payload": payload,
                    }
                attempt["response"] = payload
                attempt.update(usage(payload))
                if (
                    model["input_price"] is not None
                    and model["output_price"] is not None
                    and attempt["prompt_tokens"] is not None
                    and attempt["completion_tokens"] is not None
                ):
                    attempt["cost_usd"] = (
                        attempt["prompt_tokens"] * model["input_price"]
                        + attempt["completion_tokens"] * model["output_price"]
                    )
                details = tpm_details(payload) if provider["id"] == "groq" else None
                if details:
                    self.tpm_limits[key] = details[0]
                if response.status_code == 413 and provider["id"] == "groq":
                    # Size-specific, so never retried: remember the size and route on.
                    self.too_large[key] = min(self.too_large.get(key, size), size)
                    attempt["reason"] = "upstream HTTP 413 request too large"
                    continue
                if response.status_code == 429:
                    cooldown = upstream_cooldown(
                        response, payload, provider["id"] == "openrouter"
                    )
                    if (
                        details
                        and None not in details[:3]
                        and (details[1] + details[2] > details[0])
                    ):
                        # Groq states the exact wait; it replaces the 60s default.
                        cooldown = details[3] or cooldown
                    self.cooldowns[key] = max(
                        self.cooldowns.get(key, 0), self.clock() + cooldown
                    )
                    rate_deadlines.append(self.cooldowns[key])
                    if not routed and model["free"] and key not in retried:
                        retried.add(key)
                        pending.appendleft(provider)
                if response.status_code in OVERLOAD_COOLDOWN_STATUSES:
                    self.overload_cooldowns[key] = max(
                        self.overload_cooldowns.get(key, 0),
                        self.clock() + overload_cooldown(response),
                    )
                if response.status_code == 429:
                    attempt["reason"] = (
                        f"upstream HTTP 429; cooldown {round(cooldown)}s"
                    )
                    continue
                if response.status_code >= 500:
                    attempt["reason"] = f"upstream HTTP {response.status_code}"
                    continue
                if response.status_code == 410:
                    self.store.retire_model(*key)
                if response.status_code in MODEL_UNAVAILABLE_STATUSES:
                    self.unavailable_cooldowns[key] = (
                        self.clock() + MODEL_UNAVAILABLE_COOLDOWN_SECONDS
                    )
                    attempt["reason"] = (
                        f"upstream model unavailable (HTTP {response.status_code})"
                    )
                    continue
                if response.status_code == 402 or payment_required(payload):
                    attempt["reason"] = (
                        f"upstream payment required (HTTP {response.status_code})"
                    )
                    continue
                if (
                    provider["id"] == "google"
                    and response.status_code == 400
                    and google_signature_error(payload)
                ):
                    attempt["reason"] = "upstream Google HTTP 400: thought_signature"
                    continue
                if response.status_code >= 400:
                    if routed:
                        attempt["reason"] = f"upstream HTTP {response.status_code}"
                        continue
                    attempt["reason"] = (
                        f"non-retryable upstream HTTP {response.status_code}"
                    )
                    response_payload = payload
                    trace["http_status"] = response.status_code
                    break
                if (
                    not isinstance(payload.get("choices"), list)
                    or not payload["choices"]
                    or any(
                        not isinstance(c, dict)
                        or not isinstance(c.get("message"), dict)
                        for c in payload["choices"]
                    )
                ):
                    attempt["reason"] = "invalid upstream chat response"
                    continue
                empty = [
                    c
                    for c in payload["choices"]
                    if not (
                        (
                            isinstance(c["message"].get("content"), str)
                            and c["message"]["content"].strip()
                        )
                        or (
                            isinstance(c["message"].get("tool_calls"), list)
                            and c["message"]["tool_calls"]
                        )
                        or (
                            isinstance(c["message"].get("function_call"), dict)
                            and c["message"]["function_call"]
                        )
                    )
                ]
                if empty:
                    attempt["reason"] = (
                        "upstream assistant message has no content, tool_calls or function_call"
                    )
                    if any(c.get("finish_reason") == "length" for c in empty):
                        # Reasoning models (Groq gpt-oss) can spend the whole output budget thinking.
                        attempt["reason"] += (
                            " (finish_reason length: the output token budget ran out"
                            " before any visible output; raise max_tokens or lower"
                            " reasoning effort)"
                        )
                    continue
                attempt["reason"] = "success"
                if provider["id"] == "google":
                    self.remember_google_signatures(payload, session)
                trace.update(usage(payload))
                trace.update(
                    provider=provider["id"],
                    model=model["id"],
                    http_status=response.status_code,
                )
                context = model["context_length"]
                if "local_model" in provider:
                    context = (
                        await ollama_running_context(self.client, model["id"])
                        or context
                    )
                response_payload = payload
                break
            except httpx.RequestError as error:
                attempt["reason"] = (
                    "timeout"
                    if isinstance(error, httpx.TimeoutException)
                    else "upstream connection error"
                )
                if model["free"]:
                    self.transport_cooldowns[key] = self.clock() + 300
            finally:
                if attempt["http_status"] != 429:
                    hard_failure = True
                attempt["latency_ms"] = (self.clock() - request_start) * 1000
                if not model["free"] and attempt["cost_usd"] is None:
                    attempt.update(cost_upper_bound(attempt["request"], model, attempt))
        if response_payload is None:
            reasons = "; ".join(
                f"{a['provider']} ({a['model']}): {a['reason']}"
                if a["model"] and id(a) not in names_models
                else f"{a['provider']}: {a['reason']}"
                for a in trace["attempts"]
            )
            message = "No provider available. " + reasons
            if absent:
                message += ". Missing environment variables: " + ", ".join(
                    sorted(absent)
                )
            response_payload = {
                "error": {"message": message, "type": "no_provider_available"}
            }
            if routed:
                response_payload["error"]["rate_limited_only"] = (
                    bool(rate_deadlines) and not hard_failure
                )
                response_payload["error"]["attempts"] = [
                    {
                        field: attempt[field]
                        for field in (
                            "provider",
                            "model",
                            "called",
                            "http_status",
                            "reason",
                        )
                    }
                    for attempt in trace["attempts"]
                ]
            trace["http_status"] = (
                502 if any(a["called"] for a in trace["attempts"]) else 503
            )
        trace["response"] = response_payload
        called = [a for a in trace["attempts"] if a["called"]]
        trace["known_cost_usd"] = sum(
            a["cost_usd"] for a in called if a["cost_usd"] is not None
        )
        trace["cost_complete"] = (bool(called) or trace["http_status"] == 499) and all(
            a["cost_usd"] is not None for a in called
        )
        trace["cost_usd"] = trace["known_cost_usd"] if trace["cost_complete"] else None
        # An overloaded paid attempt (e.g. Nebius HTTP 529) reports no usage; the
        # provider's billing for it is unknown, so it stays unknown, never zero.
        # No provider was called (e.g. every provider skipped): nothing was billed.
        trace["billing_status"] = (
            "complete"
            if trace["cost_complete"]
            else "unknown_paid_attempt"
            if called
            else "none"
        )
        trace["overloaded_attempts"] = [
            {
                "provider": a["provider"],
                "model": a["model"],
                "http_status": a["http_status"],
                "cost_known": a["cost_usd"] is not None,
            }
            for a in called
            if a["http_status"] in OVERLOAD_STATUSES
        ]
        if (
            trace["http_status"] == 502
            and trace["overloaded_attempts"]
            and isinstance(response_payload.get("error"), dict)
        ):
            response_payload["error"]["billing_status"] = trace["billing_status"]
            response_payload["error"]["overloaded_attempts"] = trace[
                "overloaded_attempts"
            ]
        reserves = [
            a["cost_usd"]
            if a["cost_usd"] is not None
            else a.get("cost_upper_bound_usd")
            for a in called
        ]
        if (
            called
            and not trace["cost_complete"]
            and all(value is not None for value in reserves)
        ):
            trace.update(cost_upper_bound_usd=sum(reserves), cost_basis="upper_bound")
        trace["latency_ms"] = (self.clock() - started) * 1000
        trace["flags"] = flags_for(self.store, trace, context)
        self.store.save_trace(trace)
        self.cancelled.discard(trace["trace_id"])
        return response_payload, trace["http_status"], trace_headers(trace)


def create_app(store=None, client=None, configuration=None):
    storage = store or Store()
    strong_configuration = (
        (
            configured_providers()
            if os.environ.get("TWT_OLLAMA_MODEL")
            else hosted_providers()
        )
        if configuration is None
        else configuration
    )
    configuration = configured_providers() if configuration is None else configuration
    http = client or httpx.AsyncClient(
        timeout=30,
        trust_env=not (
            os.environ.get("TWT_OLLAMA_STRONG_MODEL")
            or any("local_model" in p for p in configuration)
        ),
    )
    gateway = Gateway(storage, http, configuration)
    gateway.strong_providers = strong_configuration

    @asynccontextmanager
    async def lifespan(app):
        yield
        if client is None:
            await http.aclose()
        if store is None:
            storage.close()

    app = FastAPI(title="TokensWithTaste", lifespan=lifespan)

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": f"{m['provider']}/{m['id']}",
                    "object": "model",
                    "owned_by": m["provider"],
                }
                for m in catalog_models(storage, gateway.providers)
                if m["chat"]
            ],
        }

    @app.post("/v1/chat/completions")
    async def complete(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and not loopback_origin(origin):
            return error_response("Only loopback origins are allowed", 403)
        if (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            return error_response("Content-Type must be application/json", 415)
        try:
            body = await request.json()
        except ValueError:
            return error_response("Invalid JSON", 400)
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("messages"), list)
            or not body["messages"]
            or not isinstance(body.get("model", "default"), str)
            or (
                "response_format" in body
                and not isinstance(body["response_format"], dict)
            )
        ):
            return error_response(
                "Expected a model string, nonempty messages list and response_format object",
                400,
            )
        privacy = request.headers.get("X-Privacy", "standard").lower()
        if privacy not in ("standard", "strict"):
            return error_response("X-Privacy must be standard or strict", 400)
        trace_id = request.headers.get("X-Trace-Id")
        if trace_id is not None:
            try:
                trace_id = str(uuid.UUID(trace_id))
            except ValueError:
                return error_response("X-Trace-Id must be a UUID", 400)
        payload, status, response_headers = await gateway.complete(
            body,
            privacy,
            request.headers.get("X-Session-Id"),
            trace_id,
            request.is_disconnected,
        )
        return JSONResponse(payload, status_code=status, headers=response_headers)

    @app.post("/v1/receipts")
    async def receipts(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and not loopback_origin(origin):
            return error_response("Only loopback origins are allowed", 403)
        try:
            body = await request.json()
            ids = body["trace_ids"]
            if not isinstance(ids, list) or len(ids) > 1000:
                raise ValueError
            ids = list(dict.fromkeys(str(uuid.UUID(value)) for value in ids))
        except (ValueError, TypeError, KeyError, AttributeError):
            return error_response("Expected at most 1000 UUID trace_ids", 400)
        result = []
        for trace_id in ids:
            trace = storage.trace(trace_id)
            if trace is None:
                if body.get("cancel") is True:
                    gateway.cancelled.add(trace_id)
                continue
            receipt = {
                key: trace.get(key)
                for key in (
                    "trace_id",
                    "provider",
                    "model",
                    "cost_usd",
                    "cost_complete",
                    "prompt_tokens",
                    "completion_tokens",
                    "http_status",
                    "cost_upper_bound_usd",
                    "cost_basis",
                    "billing_status",
                    "overloaded_attempts",
                )
            }
            # Receipt tokens cover every dispatched attempt, not just the
            # successful reply. Keep response-level trace usage unchanged for
            # response quality flags, but reconcile receipts with the report.
            attempts = [a for a in trace["attempts"] if a["called"]]
            receipt["usage_complete"] = bool(attempts) and all(
                a.get(field) is not None
                for a in attempts
                for field in ("prompt_tokens", "completion_tokens")
            )
            for field in ("prompt_tokens", "completion_tokens"):
                known = sum(a.get(field) or 0 for a in attempts)
                receipt["known_" + field] = known
                receipt[field] = (
                    known
                    if attempts and all(a.get(field) is not None for a in attempts)
                    else None
                )
            result.append(receipt)
        return {"receipts": result}

    return app
