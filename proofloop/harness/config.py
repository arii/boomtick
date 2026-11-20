"""Explicit per-process activation. Credentials alone never enable a service.

Only the process environment is used. This module does not read .env files, saved JSON keys or
Chrome storage. Supply secrets through your shell or a secret manager.

A service is "live" when it is listed in PROOFLOOP_LIVE_SERVICES and its required variables are set,
otherwise "off". There are no runtime stubs: code that needs an off service raises Blocked.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("PROOFLOOP_STATE", ROOT / "state"))
DATA_DIR = ROOT / "data"
PRIVATE_DIR = DATA_DIR / "private"
SCHEMA_DIR = ROOT / "schemas"
KEY_NAMES = ["SENSO_API_KEY", "COGNEE_API_URL", "COGNEE_API_KEY", "COGNEE_TENANT_ID", "OPENROUTER_API_KEY"]
NEEDS = {"cognee": ("COGNEE_API_URL", "COGNEE_API_KEY"), "senso": ("SENSO_API_KEY",), "llm": ("OPENROUTER_API_KEY",)}

DEFAULT_LLM_MODEL = "openrouter/free"
TWT_DEFAULT_URL = "http://127.0.0.1:8000/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Blocked(RuntimeError):
    """A required live service is not enabled or not reachable. Never caught to fake a result."""


def get(name, default=""):
    return os.environ.get(name) or default


def base_url(service):
    if service == "cognee":
        return get("COGNEE_API_URL").rstrip("/")
    env, default = {"senso": ("SENSO_BASE_URL", "https://apiv2.senso.ai"),
                    "openrouter": ("OPENROUTER_BASE_URL", "https://openrouter.ai")}[service]
    return get(env, default).rstrip("/")


def _enabled():
    return {s.strip() for s in os.environ.get("PROOFLOOP_LIVE_SERVICES", "").split(",") if s.strip()}


def twt_base_url():
    """Tokens with Taste gateway URL. Loopback only: a non-loopback URL is ignored, so prompts
    can never be redirected to a remote host by this setting. Returns "" when unusable."""
    url = (os.environ.get("TWT_BASE_URL") or TWT_DEFAULT_URL).rstrip("/")
    parsed = urlparse(url)
    return url if parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS else ""


def llm_backend():
    """'twt' (local Tokens with Taste gateway), 'openrouter', or None. twt needs 'twt' in
    PROOFLOOP_LIVE_SERVICES (no key; the gateway holds provider keys). openrouter needs 'llm' plus
    OPENROUTER_API_KEY. twt wins when both are enabled."""
    enabled = _enabled()
    if "twt" in enabled and twt_base_url():
        return "twt"
    if "llm" in enabled and all(get(k) for k in NEEDS["llm"]):
        return "openrouter"
    return None


def mode(service):
    if service == "llm":
        return "live" if llm_backend() else "off"
    return "live" if service in _enabled() and all(get(k) for k in NEEDS[service]) else "off"


def require(service):
    if mode(service) != "live":
        hint = {"llm": "PROOFLOOP_LIVE_SERVICES=twt (gateway on TWT_BASE_URL) or llm with OPENROUTER_API_KEY",
                "senso": "PROOFLOOP_LIVE_SERVICES=senso with SENSO_API_KEY",
                "cognee": "PROOFLOOP_LIVE_SERVICES=cognee with COGNEE_API_URL and COGNEE_API_KEY (COGNEE_TENANT_ID for Cognee Cloud)"}[service]
        raise Blocked(f"{service} is not enabled. Set {hint}.")


def status():
    """Booleans and labels only. Never key values."""
    backend = llm_backend()
    labels = {"llm": f"LLM via {backend}" if backend else "LLM: off", "cognee": "Cognee", "senso": "Senso"}
    out = {}
    for s in ("llm", "cognee", "senso"):
        m = mode(s)
        out[s] = {"mode": m, "label": labels[s] if s == "llm" else f"{labels[s]}: {'enabled' if m == 'live' else 'off'}"}
    out["llm"]["backend"] = backend
    return out
