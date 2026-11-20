"""Constraint cards: structured rules the extension can check locally.

A card is derived from a session constraint by hand review (see PLAN.md section 3.1). The backend
validates the set against schemas/cards.schema.json, applies host scope and returns a content hash
so the extension can tell which version it is using.
"""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import config
from jsonschema import Draft202012Validator

# PROOFLOOP_CARDS lets tests and local experiments point at another card file. It is read from the
# process environment only, never from a request.
CARDS_PATH = Path(os.environ.get("PROOFLOOP_CARDS") or config.DATA_DIR / "cards.json")
SCHEMA_PATH = config.SCHEMA_DIR / "cards.schema.json"


def canonical_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_cards(path=None):
    path = path or CARDS_PATH
    data = json.loads(path.read_text())
    errors = sorted(Draft202012Validator(json.loads(SCHEMA_PATH.read_text())).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError("invalid cards: " + "; ".join(e.message for e in errors[:3]))
    ids = [c["id"] for c in data["cards"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate card ids")
    return {"version": data["version"], "sha256": canonical_hash(data), "cards": data["cards"], "source": "local-file"}


def host_in_scope(host, scope_hosts):
    host = (host or "").lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in scope_hosts)


def applicable(cards, origin, path):
    """Cards whose scope covers this page. Only origin and path are used; no query string or body."""
    parsed = urlparse(origin or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return []
    out = []
    for c in cards:
        sc = c["scope"]
        if not host_in_scope(parsed.hostname, sc["hosts"]):
            continue
        prefixes = sc.get("path_prefixes")
        if prefixes and not any((path or "/").startswith(p) for p in prefixes):
            continue
        out.append(c)
    return out
