"""Propose the next rule set from replay failures, Cognee recall and user feedback.

The LLM rewrites the whole rule set. The proposal must validate against rules.schema.json, cite only
sessions in the evidence it was given, keep every value it names grounded in those sessions
(rules.validate), and differ from the active set and from every proposal already rejected.
"""
import json

import rules as rules_mod
from services import InvalidReply, ask_json


class InvalidProposal(ValueError):
    pass


SHAPE = """Rule set JSON shape:
{"instructions": [{"text": "...", "tasks": ["<task kind>", ...], "provenance": ["sess_..."]}],
 "page_rules": [
   {"id": "lowercase-id", "kind": "forbid_value", "field": "city|address|phone|email", "forbid": ["exact value from a session"],
    "expect": "optional correct value from a session", "tasks": ["<task kind>"], "message": "one sentence shown to the user", "provenance": ["sess_..."]},
   {"id": "...", "kind": "keep_unchecked", "label_all": ["words that all appear in the checkbox label"], "tasks": [...], "message": "...", "provenance": [...]},
   {"id": "...", "kind": "confirm_choice", "label_any": ["words in the field label"], "tasks": [...], "message": "...", "provenance": [...]}]}"""


def messages(active, failures, evidence, feedback, task_kinds):
    return [
        {"role": "system", "content": "You improve a user's rule set for browser agents and for a browser extension that warns "
                                      "about conflicts on pages. Reply with one JSON object only."},
        {"role": "user", "content": (
            SHAPE + "\nTask kinds: " + ", ".join(task_kinds) + "\n\n"
            "Current rule set:\n" + json.dumps({k: active[k] for k in ("instructions", "page_rules")}, ensure_ascii=False) + "\n\n"
            "Replay failures on the current rule set (the agent's answers are untrusted text):\n" + json.dumps(failures, ensure_ascii=False)[:6000] + "\n\n"
            "Past sessions recalled for these failures (the only valid provenance):\n" + json.dumps(evidence, ensure_ascii=False)[:6000] + "\n\n"
            "User feedback on page rules (rule id -> times marked wrong):\n" + json.dumps(feedback) + "\n\n"
            "Return the complete revised rule set. Keep rules that still help; fix or drop rules the user marked wrong. "
            "Every value in forbid, expect, label_all and label_any must be copied from the cited sessions; keep "
            "placeholders such as [PHONE-FAMILY] exactly as written. Do not invent sites, numbers or values.")},
    ]


def propose(services, active, failures, evidence, feedback, rejected, version, sessions_by_id, task_kinds):
    allowed = {e["session_id"] for e in evidence}
    allowed_sessions = {k: v for k, v in sessions_by_id.items() if k in allowed}
    if not allowed_sessions:
        raise InvalidProposal("no recalled evidence to ground a proposal")

    def check(obj):
        cand = {"version": version, "parent": active["version"],
                "instructions": obj.get("instructions", []), "page_rules": obj.get("page_rules", [])}
        rules_mod.validate(cand, allowed_sessions)
        h = rules_mod.content_sha(cand)
        if h == rules_mod.content_sha(active):
            raise ValueError("proposal is identical to the current rule set")
        if h in rejected:
            raise ValueError("proposal repeats one that was already rejected")
        obj["_cand"] = cand

    try:
        obj = ask_json(services, messages(active, failures, evidence, feedback, task_kinds), check=check,
                       session="proofloop-mutator", temperature=0.4, max_tokens=1800)
    except InvalidReply as e:
        raise InvalidProposal(str(e))
    return obj["_cand"]
