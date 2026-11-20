"""Explicit per-process activation. Credentials alone never enable a service.

Only process environment is used. This module does not read .env, saved JSON keys,
or Chrome storage. Supply secrets through an approved secret manager externally.
"""
import os
from pathlib import Path

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


def mode(service):
    if os.environ.get("PROOFLOOP_FORCE_STUB") == "1":
        return "stub"
    enabled = {s.strip() for s in os.environ.get("PROOFLOOP_LIVE_SERVICES", "").split(",")}
    return "live" if service in enabled and all(get(k) for k in NEEDS[service]) else "stub"


def status():
    names = {"cognee": "Cognee", "senso": "Senso", "llm": "OpenRouter mutation LLM"}
    return {s: {"mode": mode(s), "verified": False,
                "label": f"{name}: enabled, unverified (calls may use credits)" if mode(s) == "live"
                else f"{name}: offline stub"} for s, name in names.items()}
