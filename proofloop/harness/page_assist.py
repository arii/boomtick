"""What the extension gets for a page: the promoted page rules for the page's task, with forbidden
values as salted hashes, plus short context items from past sessions.

- Rules come only from the promoted rule set (state/active_rules.json, stored in Senso at promotion).
  When Senso is live the node is re-read and its hash compared, and the source tag says which.
- Forbidden and expected values never travel as text. Placeholders such as [PHONE-FAMILY] are
  resolved from data/private/values.json (git-ignored), normalized and hashed. The extension hashes
  what is in a field the same way (assist/match.js) and compares. Real values never leave this host.
- Context items are extracted constraints from sessions.jsonl (already redacted), never transcripts.
"""
import hashlib
import json
import re
import threading
import time
import unicodedata
from urllib.parse import urlparse

import config
import recall as recall_mod
import rules as rules_mod

SALT = "proofloop:v1:"
_cache = {"senso": {}, "recall": {}}


def normalize(field, value):
    v = str(value)
    if field == "phone":
        d = re.sub(r"\D", "", v)
        return d[1:] if len(d) == 11 and d.startswith("1") else d
    v = unicodedata.normalize("NFD", v).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", v)).strip()


def value_hash(field, value):
    return hashlib.sha256((SALT + field + ":" + normalize(field, value)).encode()).hexdigest()


def private_values():
    p = config.PRIVATE_DIR / "values.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    return {k: v for k, v in data.items() if rules_mod.PLACEHOLDER.match(k) and isinstance(v, str)}


def _resolve(field, term, values):
    """(hash, label, resolved). A placeholder without a private value cannot match any field."""
    if rules_mod.PLACEHOLDER.match(term):
        if term in values:
            return value_hash(field, values[term]), term, True
        return None, term, False
    return value_hash(field, term), term, True


def active(sessions=None):
    """The promoted rule set, or None. With sessions, it is re-validated (schema and grounding) and its
    hash checked, so a hand-edited or corrupted file is refused instead of served."""
    p = config.STATE_DIR / "active_rules.json"
    if not p.exists():
        return None
    stored = json.loads(p.read_text())
    if sessions is not None:
        try:
            rules_mod.validate(stored["rules"], {s["session_id"]: s for s in sessions})
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"active_rules.json refused: {e}")
        if stored.get("sha256") != rules_mod.sha256(stored["rules"]):
            raise ValueError("active_rules.json refused: sha256 does not match its rules")
    return stored


def source_tag(stored, senso_client=None, now=time.time):
    """Where the rule set came from, checked against Senso when it is live."""
    senso = (stored or {}).get("senso") or {}
    node = senso.get("node_id")
    if not node:
        return {"kind": "local", "label": "local rule file (not in Senso)"}
    if senso_client is None:
        return {"kind": "senso-copy", "node_id": node, "label": f"Senso node {node} (local copy; Senso not enabled here)"}
    hit = _cache["senso"].get(node)
    # A confirmed read is cached 5 minutes; a failed one only 30 seconds, so a transient error clears quickly.
    if not hit or now() - hit["at"] > (300 if hit["ok"] else 30):
        try:
            text = senso_client.read_text(node)
        except Exception as e:  # noqa: BLE001 - any read failure is reported, never hidden
            hit = {"at": now(), "ok": False, "reason": f"read failed ({type(e).__name__}: {str(e)[:120]})"}
        else:
            try:
                doc = json.loads(text)
            except ValueError:
                hit = {"at": now(), "ok": False, "reason": "node text is not the stored rule set JSON"}
            else:
                if not isinstance(doc, dict) or doc.get("type") != "PROOFLOOP_RULESET":
                    hit = {"at": now(), "ok": False, "reason": "node text is not a ProofLoop rule set"}
                elif doc.get("sha256") != stored["sha256"] or rules_mod.sha256(doc.get("rules", {})) != stored["sha256"]:
                    hit = {"at": now(), "ok": False, "reason": "hash differs from the local rule set"}
                else:
                    hit = {"at": now(), "ok": True}
        _cache["senso"][node] = hit
    if hit["ok"]:
        return {"kind": "senso", "node_id": node, "label": f"Senso rule set, node {node} (read back and hash-checked)"}
    return {"kind": "senso-mismatch", "node_id": node, "reason": hit["reason"],
            "label": f"Senso node {node} could not be confirmed ({hit['reason']}); using local copy"}


def page_rules_for(rules, task):
    values = private_values()
    out = []
    for r in rules["page_rules"]:
        if task not in r["tasks"]:
            continue
        item = {k: r[k] for k in ("id", "kind", "tasks", "message", "provenance")}
        if r["kind"] == "forbid_value":
            item["field"] = r["field"]
            item["forbid"] = []
            for term in r["forbid"]:
                h, label, resolved = _resolve(r["field"], term, values)
                item["forbid"].append({"sha256": h, "label": label, "resolved": resolved})
            if r.get("expect"):
                item["expect_label"] = r["expect"]
        else:
            item["terms"] = r.get("label_all") or r.get("label_any")
            item["match"] = "all" if r["kind"] == "keep_unchecked" else "any"
        out.append(item)
    return out


def _origin(url):
    try:
        u = urlparse(url)
        return f"{u.scheme}://{u.hostname}" if u.hostname else ""
    except ValueError:
        return ""


def session_context(sessions, suite, origin, task, limit=3):
    """Sessions recorded on this origin, then sessions whose replay task has the same kind."""
    kinds = {t["source_session_id"]: t["task_kind"] for t in (suite or {}).get("tasks", [])}
    here, same = [], []
    for s in sessions:
        urls = [s["active_tab"].get("url", "")] + [t.get("url", "") for t in s["related_tabs"]]
        if origin and any(_origin(u) == origin for u in urls):
            here.append(s)
        elif kinds.get(s["session_id"]) == task:
            same.append(s)
    items = []
    for s, why in [(s, "this site") for s in here] + [(s, "same kind of task") for s in same]:
        ex = recall_mod.excerpt(s)
        items.append({"session_id": ex["session_id"], "date": s["timestamp"][:10], "why": why,
                      "fact": ex["constraint"][:220], "source": "Session log"})
        if len(items) >= limit:
            break
    return items


def recall_context(rec, origin, task, wait=2.5):
    """Cognee recall for (origin, task), cached 10 minutes. Returns (items, state)."""
    if rec is None or rec.mode != "live":
        return [], "disabled"
    key = f"{origin}|{task}"
    hit = _cache["recall"].get(key)
    if hit and time.time() - hit["at"] < 600:
        return hit["items"], hit["state"]

    box = {}

    def work():
        try:
            box["items"] = rec.search(f"{task.replace('_', ' ')} on {urlparse(origin).hostname or ''}", k=3)
        except Exception as e:  # noqa: BLE001
            box["error"] = type(e).__name__

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(wait)
    if th.is_alive():
        return [], "pending"
    if "error" in box:
        state, items = f"error:{box['error']}", []
    else:
        state = "live"
        items = [{"session_id": x["session_id"], "date": x["session_id"][5:15].replace("_", "-"), "why": "Cognee recall",
                  "fact": x["constraint"][:220], "source": "Cognee recall"} for x in box["items"]]
    _cache["recall"][key] = {"at": time.time(), "items": items, "state": state}
    return items, state


def clean_tabs(raw, limit=12):
    """Compact open-tab summaries: origin (no path/query/fragment) plus a short title. Drops
    non-http(s) entries and anything malformed. No page text or field values are accepted."""
    out, seen = [], set()
    if not isinstance(raw, list):
        return out
    for t in raw:
        if not isinstance(t, dict):
            continue
        origin = _origin(str(t.get("origin", ""))[:200])
        if not origin.startswith(("http://", "https://")) or origin in seen:
            continue
        seen.add(origin)
        title = str(t.get("title", ""))[:80]
        out.append({"origin": origin, "title": title})
        if len(out) >= limit:
            break
    return out


def tab_matches(sessions, suite, tabs, task, limit=8):
    """One pass over the other open tabs: which of them touch recorded sessions. Only tabs
    with at least one match are returned, with short session facts (no transcripts)."""
    out = []
    for t in tabs:
        items = session_context(sessions, suite, t["origin"], task, limit=2)
        if items:
            out.append({"origin": t["origin"], "title": t["title"],
                        "sessions": [{"session_id": c["session_id"], "date": c["date"], "fact": c["fact"]} for c in items]})
        if len(out) >= limit:
            break
    return out


_ASSIST_CACHE, _ASSIST_TTL, _ASSIST_MAX = {}, 120, 64


def _assist_key(origin, task, tabs, version, recall):
    fp = hashlib.sha256(("|".join(sorted(t["origin"] for t in tabs))).encode()).hexdigest()[:16]
    return (origin, task, fp, version, bool(recall))


def assist(body, sessions, suite, senso_client=None, rec=None):
    origin = body.get("origin") if isinstance(body.get("origin"), str) else ""
    task = body.get("task") if body.get("task") in rules_mod.task_ids() else "other"
    origin = _origin(origin[:200])
    tabs = [t for t in clean_tabs(body.get("open_tabs")) if t["origin"] != origin]
    try:
        stored = active(sessions)
    except ValueError as e:
        return {"version": None, "task": task, "page_rules": [], "context": [], "tab_matches": [], "recall": "not requested",
                "source": {"kind": "invalid", "label": str(e)[:200]}}
    version = stored["rules"]["version"] if stored else None
    key = _assist_key(origin, task, tabs, version, body.get("recall") is True)
    hit = _ASSIST_CACHE.get(key)
    if hit and time.time() - hit["at"] < _ASSIST_TTL:
        return dict(hit["data"], cached=True)
    context = session_context(sessions, suite, origin, task)
    recalled, recall_state = recall_context(rec, origin, task) if body.get("recall") is True else ([], "not requested")
    seen = {c["session_id"] for c in context}
    context += [r for r in recalled if r["session_id"] not in seen]
    matches = tab_matches(sessions, suite, tabs, task)
    if not stored:
        data = {"version": None, "task": task, "page_rules": [], "context": context, "tab_matches": matches,
                "recall": recall_state, "source": {"kind": "none", "label": "no promoted rule set yet (run replay_loop.py)"}}
    else:
        rs = stored["rules"]
        data = {"version": rs["version"], "sha256": stored["sha256"], "task": task, "page_rules": page_rules_for(rs, task),
                "context": context, "tab_matches": matches, "recall": recall_state, "source": source_tag(stored, senso_client),
                "promoted_at": stored.get("promoted_at")}
    if len(_ASSIST_CACHE) >= _ASSIST_MAX:
        _ASSIST_CACHE.pop(next(iter(_ASSIST_CACHE)))
    _ASSIST_CACHE[key] = {"at": time.time(), "data": data}
    return data
