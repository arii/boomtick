import json
import os
from importlib.resources import files

import httpx


LITELLM_SHA = "d034fb681ca296a0f082a224043eda62a2ce82d4"
PRICE_URL = f"https://raw.githubusercontent.com/BerriAI/litellm/{LITELLM_SHA}/model_prices_and_context_window.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
OLLAMA_URL = "http://127.0.0.1:11434"


def providers():
    return json.loads(files("twt").joinpath("providers.json").read_text())["providers"]


def configured_providers():
    model = os.environ.get("TWT_OLLAMA_MODEL")
    if model:
        return [{"id": "ollama", "base_url": f"{OLLAMA_URL}/v1", "local_model": model,
                 "strict": True, "trains_on_free_tier": False}]
    return providers()


def catalog_models(store, configuration):
    local_model = next((p["local_model"] for p in configuration if "local_model" in p), None)
    if local_model:
        return [m for m in store.models() if m["provider"] == "ollama" and m["id"] == local_model]
    return [m for m in store.models() if m["provider"] != "ollama"]


def missing(provider):
    keys = [provider["key_env"]] if "key_env" in provider else []
    return [key for key in [*keys, *provider.get("required_env", [])] if not os.environ.get(key)]


def base_url(provider):
    return provider["base_url"].replace("{account_id}", os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""))


def headers(provider):
    if "key_env" not in provider:
        return {}
    return {"Authorization": f"Bearer {os.environ[provider['key_env']]}"}


def number(value):
    try:
        result = float(value)
        return result if result >= 0 and result < float("inf") else None
    except (TypeError, ValueError):
        return None


def normalize(provider, row, prices, router):
    model_id = row["id"]
    prefix = provider["map_prefix"]
    metadata = prices.get(f"{prefix}/{model_id}", {})
    if not metadata:
        candidate = prices.get(model_id, {})
        if candidate.get("litellm_provider") == prefix:
            metadata = candidate
    # Cross-reference exact IDs only: suffix matching can attach another model's capabilities.
    reference = row if provider["id"] == "openrouter" else router.get(model_id, {})
    params = reference.get("supported_parameters", [])
    mode = metadata.get("mode")
    architecture = reference.get("architecture", {})
    outputs = architecture.get("output_modalities", [])
    chat = "text" in outputs if outputs else mode == "chat"
    known = provider.get("models", {}).get(model_id, {})
    pricing = row.get("pricing", {}) if provider["id"] == "openrouter" else {}
    input_price = number(pricing.get("prompt"))
    output_price = number(pricing.get("completion"))
    if input_price is None:
        input_price = number(metadata.get("input_cost_per_token"))
    if output_price is None:
        output_price = number(metadata.get("output_cost_per_token"))
    free = known.get("free", False) or (provider["id"] == "openrouter" and
            number(pricing.get("prompt")) == 0 and number(pricing.get("completion")) == 0)
    if provider.get("free_prototyping"):
        free = True
    if "supported_parameters" in reference:
        tools = "tools" in params
        json_mode = "response_format" in params
        json_schema = "structured_outputs" in params
    else:
        tools = metadata.get("supports_function_calling") is True
        json_mode = json_schema = metadata.get("supports_response_schema") is True
    default_rpm = provider.get("rpm")
    if provider["id"] == "openrouter" and not model_id.endswith(":free"):
        default_rpm = None
    rpm = known.get("rpm", default_rpm)
    return {
        "provider": provider["id"], "id": model_id, "chat": chat,
        "tools": tools, "json": json_mode, "json_schema": json_schema,
        "context_length": reference.get("context_length") or metadata.get("max_input_tokens"),
        "input_price": 0.0 if free else input_price, "output_price": 0.0 if free else output_price,
        "free": free, "rpm": rpm,
        "daily": known.get("daily"), "synced_source": provider.get("models_url") or base_url(provider) + "/models",
        "metadata_source": OPENROUTER_URL if reference else PRICE_URL,
        "price_source": OPENROUTER_URL if provider["id"] == "openrouter" else PRICE_URL,
    }


async def require_local_ollama(client):
    response = await client.get(f"{OLLAMA_URL}/api/status")
    response.raise_for_status()
    status = response.json()
    cloud = status.get("cloud") if isinstance(status, dict) else None
    if not isinstance(cloud, dict) or cloud.get("disabled") is not True:
        raise ValueError("Ollama cloud must be disabled (OLLAMA_NO_CLOUD=1)")


def ollama_model_name(model):
    name = model.casefold().removeprefix("registry.ollama.ai/")
    if name.count("/") == 1:
        name = name.removeprefix("library/")
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


async def ollama_running_context(client, model):
    try:
        response = await client.get(f"{OLLAMA_URL}/api/ps", timeout=1)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    rows = payload.get("models") if isinstance(payload, dict) else None
    name = ollama_model_name(model)
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str):
            continue
        context = row.get("context_length")
        if ollama_model_name(row["model"]) == name and type(context) is int and context > 0:
            return context
    return None


async def sync_ollama(store, client, model):
    await require_local_ollama(client)
    source = f"{OLLAMA_URL}/api/show"
    response = await client.post(source, json={"model": model})
    response.raise_for_status()
    details = response.json()
    capabilities = details.get("capabilities") if isinstance(details, dict) else None
    if (not isinstance(capabilities, list) or "completion" not in capabilities
            or details.get("remote_model") or details.get("remote_host")):
        raise ValueError(f"Ollama model {model!r} must be an installed local chat model")
    info = details.get("model_info")
    architecture = info.get("general.architecture") if isinstance(info, dict) else None
    context = info.get(f"{architecture}.context_length") if isinstance(architecture, str) else None
    store.replace_models("ollama", [{
        "provider": "ollama", "id": model, "chat": True, "tools": "tools" in capabilities,
        "json": False, "json_schema": False,
        "context_length": context if type(context) is int and context > 0 else None,
        "input_price": 0.0, "output_price": 0.0, "free": True, "rpm": None, "daily": None,
        "synced_source": source, "metadata_source": source, "price_source": "local",
    }])
    return ["ollama: synced 1 model"]


async def sync(store, client=None, configuration=None):
    configuration = configured_providers() if configuration is None else configuration
    local_model = next((p["local_model"] for p in configuration if "local_model" in p), None)
    owned = client is None
    client = client or httpx.AsyncClient(timeout=60, follow_redirects=not local_model, trust_env=not local_model)
    messages = []
    try:
        if local_model:
            return await sync_ollama(store, client, local_model)
        response = await client.get(PRICE_URL)
        response.raise_for_status()
        prices = response.json()
        response = await client.get(OPENROUTER_URL)
        response.raise_for_status()
        router_rows = response.json()["data"]
        router = {m["id"]: m for m in router_rows}
        messages.append(f"LiteLLM {LITELLM_SHA}: {len(prices)} entries")
        messages.append(f"OpenRouter public catalog: {len(router)} models (no key)")
        for provider in configuration:
            absent = missing(provider)
            if provider["id"] == "openrouter":
                rows = router_rows
            elif absent and not provider.get("public_models"):
                messages.append(f"{provider['id']}: SKIPPED missing {', '.join(absent)}")
                continue
            elif provider.get("discovery_blocked"):
                messages.append(f"{provider['id']}: BLOCKED {provider['discovery_blocked']}")
                continue
            else:
                try:
                    response = await client.get(provider.get("models_url") or base_url(provider) + "/models",
                                                headers={} if absent else headers(provider))
                    response.raise_for_status()
                    rows = response.json()["data"]
                    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get("id"), str) for r in rows):
                        raise ValueError("Invalid model list")
                except (httpx.HTTPError, KeyError, ValueError):
                    messages.append(f"{provider['id']}: FAILED model listing; cached rows retained")
                    continue
            models = [normalize(provider, row, prices, router) for row in rows]
            store.replace_models(provider["id"], models)
            messages.append(f"{provider['id']}: synced {len(models)} models")
            if absent:
                messages.append(f"{provider['id']}: inference SKIPPED missing {', '.join(absent)}")
        return messages
    finally:
        if owned:
            await client.aclose()
