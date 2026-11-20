"""Single config for every sponsor call.

Live vs stub is decided here from env vars (or state/keys.json, written by the
extension's Keys & Status strip via the server's /config endpoint). Swapping a
stub for the live API is a config change only.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("PROOFLOOP_STATE", ROOT / "state"))
DATA_DIR = ROOT / "data"
SCHEMA_DIR = ROOT / "schemas"
SKILLS_LOCAL = ROOT / "skills-local"

KEY_NAMES = ["SENSO_API_KEY", "TYPESAFE_API_KEY", "COGNEE_API_URL", "COGNEE_API_KEY", "OPENROUTER_API_KEY"]

JEV_MODEL = "typesafe/jev-1.14.0"


def _file_keys() -> dict:
    p = STATE_DIR / "keys.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def get(name: str, default: str = "") -> str:
    if os.environ.get("PROOFLOOP_FORCE_STUB") == "1" and name in KEY_NAMES:
        return ""
    return os.environ.get(name) or _file_keys().get(name) or default


def base_url(service: str) -> str:
    defaults = {
        "jev": "https://api.typesafe.ai",
        "senso": "https://api.senso.ai",
        "openrouter": "https://openrouter.ai",
    }
    env = {"jev": "TYPESAFE_BASE_URL", "senso": "SENSO_BASE_URL", "openrouter": "OPENROUTER_BASE_URL"}
    if service == "cognee":
        return get("COGNEE_API_URL").rstrip("/")
    return (os.environ.get(env[service]) or defaults[service]).rstrip("/")


def mode(service: str) -> str:
    """Return 'live' or 'stub' for cognee | jev | senso | llm."""
    needs = {"cognee": "COGNEE_API_URL", "jev": "TYPESAFE_API_KEY",
             "senso": "SENSO_API_KEY", "llm": "OPENROUTER_API_KEY"}[service]
    return "live" if get(needs) else "stub"


def status() -> dict:
    labels = {
        "cognee": ("Cognee (live)", "Cognee stub (local graph) - live Cognee pending"),
        "jev": ("TypeSafe Jev (live)", "Jev stub (threshold gate) - live Jev pending key"),
        "senso": ("Senso (live)", "Senso (local stub - live API pending key)"),
        "llm": ("OpenRouter LLM (live)", "Rule-based mutator (no LLM key) - live LLM pending"),
    }
    return {s: {"mode": mode(s), "label": labels[s][0 if mode(s) == "live" else 1]} for s in labels}
