"""Rule sets: validation, grounding checks, hashing and prompt rendering.

A rule set is produced by the mutator and promoted by the gate. Nothing in this module invents
rules; it only checks that a proposed set is well formed and grounded in the sessions it cites.
"""
import hashlib
import json
import re
import unicodedata

import config
from jsonschema import Draft202012Validator

_SCHEMA = None
PLACEHOLDER = re.compile(r"^\[[A-Z][A-Z0-9-]{1,30}\]$")


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads((config.SCHEMA_DIR / "rules.schema.json").read_text())
    return _SCHEMA


def task_ids():
    return [t["id"] for t in json.loads((config.SCHEMA_DIR / "tasks.json").read_text())["tasks"]]


def empty(version="v0"):
    return {"version": version, "parent": None, "instructions": [], "page_rules": []}


def canonical(rules):
    return json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(rules):
    return hashlib.sha256(canonical(rules).encode()).hexdigest()


def content_sha(rules):
    """Hash without version/parent, so a re-proposal of the same content is recognized."""
    return sha256({k: v for k, v in rules.items() if k not in ("version", "parent")})


def norm(text):
    t = unicodedata.normalize("NFD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\[\]-]", " ", t)).strip()


def validate(rules, sessions_by_id):
    """Raise ValueError unless `rules` matches the schema and is grounded in the cited sessions.

    Grounding: every provenance id exists; every forbid/expect term and every label term appears in
    the text of at least one cited session (placeholders like [PHONE-FAMILY] must appear verbatim)."""
    errors = sorted(Draft202012Validator(schema()).iter_errors(rules), key=lambda e: list(e.path))
    if errors:
        raise ValueError("schema: " + "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}"[:160] for e in errors[:4]))
    ids = [r["id"] for r in rules["page_rules"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate page rule ids")

    def cited_text(prov):
        missing = [p for p in prov if p not in sessions_by_id]
        if missing:
            raise ValueError(f"provenance cites unknown sessions: {missing}")
        return norm(" ".join(json.dumps(sessions_by_id[p], ensure_ascii=False) for p in prov))

    for ins in rules["instructions"]:
        cited_text(ins["provenance"])
    for r in rules["page_rules"]:
        text = cited_text(r["provenance"])
        terms = r.get("forbid", []) + ([r["expect"]] if r.get("expect") else []) + r.get("label_all", []) + r.get("label_any", [])
        for term in terms:
            if PLACEHOLDER.match(term):
                if term.lower() not in text:
                    raise ValueError(f"rule {r['id']}: placeholder {term} not in cited sessions")
            elif norm(term) not in text:
                raise ValueError(f"rule {r['id']}: term {term!r} does not appear in cited sessions")
    return rules


def render_prompt(rules, task_kind=None):
    """Plain-text rules for an agent. With task_kind, only rules scoped to that task (or unscoped)."""
    def applies(item):
        return task_kind is None or not item.get("tasks") or task_kind in item["tasks"]

    lines = [f"User rules (ProofLoop rule set {rules['version']}). Follow them when acting for the user:"]
    ins = [i for i in rules["instructions"] if applies(i)]
    pr = [r for r in rules["page_rules"] if applies(r)]
    if not ins and not pr:
        lines.append("(no rules yet)")
    for i, item in enumerate(ins, 1):
        lines.append(f"{i}. {item['text']}")
    for r in pr:
        if r["kind"] == "forbid_value":
            extra = f" Use {r['expect']}." if r.get("expect") else ""
            lines.append(f"- In a {r['field']} field, never enter: {', '.join(r['forbid'])}.{extra} {r['message']}")
        elif r["kind"] == "keep_unchecked":
            lines.append(f"- Leave unchecked any box whose label mentions: {', '.join(r['label_all'])}. {r['message']}")
        else:
            lines.append(f"- Ask the user before choosing a value for: {', '.join(r['label_any'])}. {r['message']}")
    return "\n".join(lines)


def diff(old, new):
    def keyset(rs):
        return {f"instruction: {i['text']}" for i in rs["instructions"]} | {f"page_rule {r['id']}: {r['message']}" for r in rs["page_rules"]}
    a, b = keyset(old), keyset(new)
    return "\n".join([f"+ {x}" for x in sorted(b - a)] + [f"- {x}" for x in sorted(a - b)]) or "(no change)"
