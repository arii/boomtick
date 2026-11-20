"""Explicit per-process activation. Credentials alone never enable a service.

Only process environment is used. This module does not read .env, saved JSON keys,
or Chrome storage. Supply secrets through an approved secret manager externally.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("PROOFLOOP_STATE", ROOT / "state"))
DATA_DIR = ROOT / "data"
SCHEMA_DIR = ROOT / "schemas"
SKILLS_LOCAL = ROOT / "skills-local"
KEY_NAMES = ["SENSO_API_KEY", "COGNEE_API_URL", "COGNEE_API_KEY", "COGNEE_TENANT_ID",
             "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "SENSO_POLL_S"]
NEEDS = {"cognee": ("COGNEE_API_URL", "COGNEE_API_KEY"),
         "senso": ("SENSO_API_KEY",), "llm": ("OPENROUTER_API_KEY",)}


DEFAULT_LLM_MODEL = "openrouter/free"
TWT_DEFAULT_URL = "http://127.0.0.1:8000/v1"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def get(name, default=""):
    if os.environ.get("PROOFLOOP_FORCE_STUB") == "1" and name in KEY_NAMES:
        return ""
    return os.environ.get(name) or default


def base_url(service):
    if service == "cognee":
        return get("COGNEE_API_URL").rstrip("/")
    env, default = {"senso": ("SENSO_BASE_URL", "https://apiv2.senso.ai"),
                    "openrouter": ("OPENROUTER_BASE_URL", "https://openrouter.ai")}[service]
    return get(env, default).rstrip("/")


def _enabled():
    return {s.strip() for s in os.environ.get("PROOFLOOP_LIVE_SERVICES", "").split(",")}


def twt_base_url():
    """Tokens with Taste gateway URL. Loopback only: a non-loopback URL is ignored, so prompts
    can never be redirected to a remote host by this setting. Returns "" when unusable."""
    url = (os.environ.get("TWT_BASE_URL") or TWT_DEFAULT_URL).rstrip("/")
    parsed = urlparse(url)
    return url if parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS else ""


def llm_backend():
    """'twt' (local Tokens with Taste gateway), 'openrouter', or None. Both need explicit activation:
    PROOFLOOP_LIVE_SERVICES must list 'twt' (no key needed) or 'llm' (plus OPENROUTER_API_KEY).
    twt wins when both are enabled."""
    if os.environ.get("PROOFLOOP_FORCE_STUB") == "1":
        return None
    enabled = _enabled()
    if "twt" in enabled and twt_base_url():
        return "twt"
    if "llm" in enabled and all(get(k) for k in NEEDS["llm"]):
        return "openrouter"
    return None


def mode(service):
    if os.environ.get("PROOFLOOP_FORCE_STUB") == "1":
        return "stub"
    if service == "llm":
        return "live" if llm_backend() else "stub"
    return "live" if service in _enabled() and all(get(k) for k in NEEDS[service]) else "stub"


def status():
    backend = llm_backend()
    llm_name = {"twt": "Mutation LLM via local Tokens with Taste gateway",
                "openrouter": "OpenRouter mutation LLM"}.get(backend, "Mutation LLM")
    names = {"cognee": "Cognee", "senso": "Senso", "llm": llm_name}
    return {s: {"mode": mode(s), "verified": False,
                "label": f"{name}: enabled, unverified (calls may use credits)" if mode(s) == "live"
                else f"{name}: offline stub"} for s, name in names.items()}
