#!/usr/bin/env python3
"""Package the loop's real state for the handoff after a promotion (see .agents/plans/kiro-loop-handoff.md).

    python3 handoff.py                         # reads PROOFLOOP_STATE, prints one JSON bundle
    PROOFLOOP_LIVE_SERVICES=senso SENSO_API_KEY=... python3 handoff.py --check-senso   # also re-read the Senso node

The bundle holds the ledger (every entry, with gate decisions and scores), the active rule set with its hash and
Senso node, the last run, feedback counts per rule and action, and the validation result. It never holds keys,
private values (rules carry placeholders like [PHONE-FAMILY]), agent answers or session text. It reads only files
the loop wrote; if there is nothing to hand off it says so and exits 2.
"""
import argparse
import json
import sys
from collections import Counter

import clients
import config
import page_assist
import rules as rules_mod
import validate


def load(name):
    p = config.STATE_DIR / name
    return json.loads(p.read_text()) if p.exists() else None


def feedback_counts():
    p = config.STATE_DIR / "feedback.jsonl"
    c = Counter()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            c[f"{r.get('rule_id')}|{r.get('action')}"] += 1
    out = {}
    for k, n in sorted(c.items()):
        rid, action = k.split("|", 1)
        out.setdefault(rid, {})[action] = n
    return out


def bundle(check_senso=False):
    ledger, stored, run = load("proof_ledger.json"), load("active_rules.json"), load("last_run.json")
    if not ledger:
        raise SystemExit(f"nothing to hand off: no proof_ledger.json in {config.STATE_DIR}")
    sessions = validate.load_sessions()
    problems = []
    try:
        validate.check_ledger(ledger)
    except SystemExit as e:
        problems.append(f"ledger: {e}")
    if stored:
        try:
            page_assist.active(sessions)
        except ValueError as e:
            problems.append(str(e))
    entries = ledger["entries"]
    promoted = [e for e in entries if e["status"] == "promoted"]
    out = {
        "state_dir": str(config.STATE_DIR),
        "active_version": ledger.get("active_version"),
        "promotions": len(promoted),
        "statuses": dict(Counter(e["status"] for e in entries)),
        "ledger_entries": [{k: e.get(k) for k in ("cycle", "timestamp", "version", "parent_version", "status", "gate", "scores",
                                                  "recall", "llm", "rules_sha256", "diff", "evidence_sessions", "senso")} for e in entries],
        "active_rules": stored and {"rules": stored["rules"], "sha256": stored["sha256"], "sha256_ok": stored["sha256"] == rules_mod.sha256(stored["rules"]),
                                    "scores": stored.get("scores"), "senso": stored.get("senso"), "promoted_at": stored.get("promoted_at")},
        "last_run": run and {k: run.get(k) for k in ("generated", "stop", "active", "services")},
        "feedback": feedback_counts(),
        "problems": problems,
    }
    if check_senso:
        config.require("senso")
        out["senso_check"] = page_assist.source_tag(stored, clients.SensoLive()) if stored else {"kind": "none"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-senso", action="store_true", help="re-read the active rule set's Senso node (needs senso enabled)")
    args = ap.parse_args()
    try:
        out = bundle(args.check_senso)
    except config.Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
