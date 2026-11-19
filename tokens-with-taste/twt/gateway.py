import asyncio
import os
import time
import uuid
from ipaddress import ip_address
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .audit import flags_for, usage
from .catalog import (
    base_url, catalog_models, configured_providers, headers, missing,
    ollama_running_context, require_local_ollama,
)
from .store import Store, now


def loopback_origin(origin):
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
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
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 60


def trace_headers(trace):
    return {
        "X-Trace-Id": trace["trace_id"], "X-Provider-Used": trace["provider"] or "none",
        "X-Cost-Usd": str(trace["cost_usd"]) if trace["cost_usd"] is not None else "unknown",
        "X-Audit-Flags": ",".join(trace["flags"]),
    }


def error_response(message, status):
    return JSONResponse({"error": {"message": message}}, status_code=status)


def eligible_models(catalog, provider, body):
    candidates = [m for m in catalog if m["provider"] == provider["id"] and m["chat"]]
    requested = body.get("model", "default")
    if requested not in ("default", "route:default"):
        candidates = [m for m in candidates if requested in (m["id"], f"{provider['id']}/{m['id']}")]
    elif provider.get("free_only"):
        candidates = [m for m in candidates if m["free"]]
    if body.get("tools"):
        candidates = [m for m in candidates if m["tools"]]
    if body.get("response_format") and body["response_format"].get("type") != "text":
        capability = "json_schema" if body["response_format"].get("type") == "json_schema" else "json"
        candidates = [m for m in candidates if m.get(capability)]
    return candidates


class Gateway:
    def __init__(self, store, client, configuration=None, clock=time.monotonic):
        self.store = store
        self.client = client
        self.providers = configuration if configuration is not None else configured_providers()
        self.clock = clock
        self.calls = defaultdict(deque)
        self.cooldowns = {}
        self.lock = asyncio.Lock()

    async def complete(self, body, privacy="standard", session=None):
        started = self.clock()
        original_body = dict(body)
        body = {**body, "stream": False}
        body.pop("stream_options", None)
        trace = {"trace_id": str(uuid.uuid4()), "timestamp": now(), "route": body.get("model", "default"),
                 "privacy": privacy, "session_id": session, "provider": None, "model": None,
                 "attempts": [], "http_status": 503, "latency_ms": 0, "prompt_tokens": None,
                 "completion_tokens": None, "reasoning_tokens": None, "visible_tokens": None,
                 "cost_usd": None, "known_cost_usd": 0, "cost_complete": False,
                 "flags": [], "request": original_body, "response": None}
        catalog = catalog_models(self.store, self.providers)
        absent = set()
        response_payload = None
        context = None
        budget = os.environ.get("TWT_DAILY_BUDGET_USD")
        if budget is not None:
            try:
                budget = float(budget)
                if not 0 <= budget < float("inf"):
                    raise ValueError
            except ValueError:
                trace["response"] = {"error": {"message": "TWT_DAILY_BUDGET_USD must be a finite nonnegative number"}}
                trace["http_status"] = 500
                self.store.save_trace(trace)
                return trace["response"], 500, trace_headers(trace)
        for provider in self.providers:
            attempt = {"provider": provider["id"], "model": None, "called": False,
                       "timestamp": now(),
                       "reason": "", "http_status": None, "latency_ms": 0,
                       "request": None, "response": None, "prompt_tokens": None,
                       "completion_tokens": None, "reasoning_tokens": None, "cost_usd": None}
            trace["attempts"].append(attempt)
            missing_keys = missing(provider)
            if missing_keys:
                absent.update(missing_keys)
                attempt["reason"] = "missing credentials: " + ", ".join(missing_keys)
                continue
            if privacy == "strict" and (not provider["strict"] or provider["trains_on_free_tier"] is not False):
                attempt["reason"] = "strict privacy excluded"
                continue
            candidates = eligible_models(catalog, provider, body)
            if not candidates:
                attempt["reason"] = "no synced eligible chat model matching requested model/free-tier/tools/JSON capabilities; run twt sync"
                continue
            model = min(candidates, key=lambda m: (not m["free"], m["input_price"] if m["input_price"] is not None else float("inf"), m["id"]))
            attempt["model"] = model["id"]
            if "local_model" in provider:
                try:
                    await require_local_ollama(self.client)
                except (httpx.HTTPError, ValueError):
                    attempt["reason"] = "local Ollama unavailable or cloud not disabled; check OLLAMA_NO_CLOUD=1"
                    continue
            key = (provider["id"], model["id"])
            async with self.lock:
                if budget is not None and not model["free"] and (
                        self.store.spend_today() >= budget or model["input_price"] is None or model["output_price"] is None):
                    attempt["reason"] = "daily budget reached or paid model price unknown"
                    continue
                current = self.clock()
                if self.cooldowns.get(key, 0) > current:
                    attempt["reason"] = "Retry-After cooldown"
                    continue
                window = self.calls[key]
                while window and window[0] <= current - 60:
                    window.popleft()
                if model.get("rpm") is not None and len(window) >= model["rpm"]:
                    attempt["reason"] = "local RPM limit"
                    continue
                window.append(current)
            attempt["called"] = True
            trace["provider"] = provider["id"]
            trace["model"] = model["id"]
            attempt["request"] = {**body, "model": model["id"]}
            request_start = self.clock()
            try:
                response = await self.client.post(base_url(provider) + "/chat/completions",
                                                  headers=headers(provider), json=attempt["request"])
                attempt["http_status"] = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    payload = {"error": {"message": "Upstream returned a non-JSON response"}, "raw_text": response.text}
                if not isinstance(payload, dict):
                    payload = {"error": {"message": "Upstream returned a non-object response"}, "raw_payload": payload}
                attempt["response"] = payload
                attempt.update(usage(payload))
                if (model["input_price"] is not None and model["output_price"] is not None
                        and attempt["prompt_tokens"] is not None and attempt["completion_tokens"] is not None):
                    attempt["cost_usd"] = attempt["prompt_tokens"] * model["input_price"] + attempt["completion_tokens"] * model["output_price"]
                if response.status_code == 429:
                    self.cooldowns[key] = max(self.cooldowns.get(key, 0), self.clock() + retry_seconds(response.headers.get("Retry-After")))
                if response.status_code == 429 or response.status_code >= 500:
                    attempt["reason"] = f"upstream HTTP {response.status_code}"
                    continue
                if response.status_code >= 400:
                    attempt["reason"] = f"non-retryable upstream HTTP {response.status_code}"
                    response_payload = payload
                    trace["http_status"] = response.status_code
                    break
                if (not isinstance(payload.get("choices"), list) or not payload["choices"]
                        or any(not isinstance(c, dict) or not isinstance(c.get("message"), dict) for c in payload["choices"])):
                    attempt["reason"] = "invalid upstream chat response"
                    continue
                attempt["reason"] = "success"
                trace.update(usage(payload))
                trace.update(provider=provider["id"], model=model["id"], http_status=response.status_code)
                context = model["context_length"]
                if "local_model" in provider:
                    context = await ollama_running_context(self.client, model["id"]) or context
                response_payload = payload
                break
            except httpx.TimeoutException:
                attempt["reason"] = "timeout"
            except httpx.RequestError:
                attempt["reason"] = "upstream connection error"
            finally:
                attempt["latency_ms"] = (self.clock() - request_start) * 1000
        if response_payload is None:
            reasons = "; ".join(f"{a['provider']}: {a['reason']}" for a in trace["attempts"])
            message = "No provider available. " + reasons
            if absent:
                message += ". Missing environment variables: " + ", ".join(sorted(absent))
            response_payload = {"error": {"message": message, "type": "no_provider_available"}}
            trace["http_status"] = 502 if any(a["called"] for a in trace["attempts"]) else 503
        trace["response"] = response_payload
        called = [a for a in trace["attempts"] if a["called"]]
        trace["known_cost_usd"] = sum(a["cost_usd"] for a in called if a["cost_usd"] is not None)
        trace["cost_complete"] = bool(called) and all(a["cost_usd"] is not None for a in called)
        trace["cost_usd"] = trace["known_cost_usd"] if trace["cost_complete"] else None
        trace["latency_ms"] = (self.clock() - started) * 1000
        trace["flags"] = flags_for(self.store, trace, context)
        self.store.save_trace(trace)
        return response_payload, trace["http_status"], trace_headers(trace)


def create_app(store=None, client=None, configuration=None):
    storage = store or Store()
    configuration = configured_providers() if configuration is None else configuration
    http = client or httpx.AsyncClient(timeout=30, trust_env=not any("local_model" in p for p in configuration))
    gateway = Gateway(storage, http, configuration)

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
        return {"object": "list", "data": [
            {"id": f"{m['provider']}/{m['id']}", "object": "model", "owned_by": m["provider"]}
            for m in catalog_models(storage, gateway.providers) if m["chat"]]}

    @app.post("/v1/chat/completions")
    async def complete(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and not loopback_origin(origin):
            return error_response("Only loopback origins are allowed", 403)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return error_response("Content-Type must be application/json", 415)
        try:
            body = await request.json()
        except ValueError:
            return error_response("Invalid JSON", 400)
        if (not isinstance(body, dict) or not isinstance(body.get("messages"), list)
                or not body["messages"] or not isinstance(body.get("model", "default"), str)
                or ("response_format" in body and not isinstance(body["response_format"], dict))):
            return error_response("Expected a model string, nonempty messages list and response_format object", 400)
        privacy = request.headers.get("X-Privacy", "standard").lower()
        if privacy not in ("standard", "strict"):
            return error_response("X-Privacy must be standard or strict", 400)
        payload, status, response_headers = await gateway.complete(body, privacy, request.headers.get("X-Session-Id"))
        return JSONResponse(payload, status_code=status, headers=response_headers)

    return app
