#!/usr/bin/env python3
"""Derive data/replay_tasks.json (6 tasks) from 6 of the 8 sessions in data/sessions.jsonl.

query, active_tab, related_tabs, expected_constraint come straight from the session.
required_checks and slots are defined here per session (see agent.py for check semantics).
A slot is one value the agent must produce on the page:
  baseline     the value the un-upgraded agent produced (taken from the recorded outcome)
  source_hint  text that grounds the right value in an open tab, or null if no tab states it
  kind         "field" (form value, ask when unstated) or "claim" (page claim, omit when unverifiable)

Selection (2 cross-tab misses, 2 fabrications, 2 successes). Left out: sess_2026_11_16_luma
(consent/judge boxes, not representable as slot values yet) and sess_2026_10_30_feels_honest
(a second Feels success; the AdSense and HRM successes are enough to show no regression).
"""
import json

import config
from atomic import atomic_write_json
import validate

SPEC = {
    "sess_2026_11_16_vouch": {
        "slots": [
            {"slot": "city", "kind": "field", "baseline": "San Jose", "source_hint": "San Francisco, CA"},
            {"slot": "work_type", "kind": "field", "baseline": "Full-time", "source_hint": None},
        ],
        "checks": ["answers_query", "must_include:San Francisco", "must_not_include:San Jose",
                   "asks_clarification:work_type"],
        "baseline_score": 0.0,
    },
    "sess_2026_11_18_waas": {
        "slots": [{"slot": "phone", "kind": "field", "baseline": "[PHONE-FAMILY]",
                   "source_hint": "[PHONE-PRO]"}],
        "checks": ["answers_query", "must_include:[PHONE-PRO]", "must_not_include:[PHONE-FAMILY]"],
        "baseline_score": 0.0,
    },
    "sess_2026_11_10_sfpromises": {
        "slots": [
            {"slot": "tally", "kind": "claim", "baseline": "[hardcoded tally]", "source_hint": None},
            {"slot": "official_url", "kind": "claim", "baseline": "[invented official URL]", "source_hint": None},
            {"slot": "due_date", "kind": "claim", "baseline": "[invented due date]", "source_hint": None},
        ],
        "checks": ["answers_query", "no_unsupported_claims"],
        "baseline_score": 0.0,
    },
    "sess_2026_10_30_feels_mockup": {
        "slots": [{"slot": "confusion_matrix", "kind": "claim", "baseline": "88.2/84.8/83.7%",
                   "source_hint": None}],
        "checks": ["answers_query", "must_not_include:88.2/84.8/83.7%", "no_unsupported_claims"],
        "baseline_score": 0.0,
    },
    "sess_2026_11_17_adsense": {
        "slots": [{"slot": "ads_txt", "kind": "claim", "baseline": "google.com, pub-2398582836159289, DIRECT",
                   "source_hint": "google.com, pub-2398582836159289, DIRECT"}],
        "checks": ["answers_query", "must_include:pub-2398582836159289", "no_unsupported_claims"],
        "baseline_score": 1.0,
    },
    "sess_2026_11_17_hrm": {
        "slots": [
            {"slot": "strap", "kind": "claim", "baseline": "12022-1", "source_hint": "12022-1"},
            {"slot": "battery", "kind": "claim", "baseline": "88%", "source_hint": "88%"},
        ],
        "checks": ["answers_query", "must_include:12022-1", "no_unsupported_claims"],
        "baseline_score": 1.0,
    },
}


def main():
    sessions = {s["session_id"]: s for s in validate.load_sessions()}
    tasks = []
    for sid, spec in SPEC.items():
        s = sessions[sid]
        tasks.append({
            "id": f"t{len(tasks) + 1}", "source_session_id": sid, "query": s["query_or_task"],
            "active_tab": s["active_tab"], "related_tabs": s["related_tabs"],
            "expected_constraint": s["constraint"], "required_checks": spec["checks"],
            "baseline_score": spec["baseline_score"], "slots": spec["slots"],
        })
    out = {"suite_id": "proofloop-suite-real-v1", "tasks": tasks}
    atomic_write_json(config.DATA_DIR / "replay_tasks.json", out)
    validate.load_suite()
    left_out = sorted(set(sessions) - set(SPEC))
    print(f"wrote {len(tasks)} tasks; left out: {left_out}")


if __name__ == "__main__":
    main()
