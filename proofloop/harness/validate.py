#!/usr/bin/env python3
"""Validate sessions.jsonl, replay_tasks.json and proof_ledger.json against schemas.

    python3 validate.py        # validates data files (+ ledger if present)
"""
import json
import sys

import config

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit("pip install jsonschema")


def _schema(name):
    return json.loads((config.SCHEMA_DIR / name).read_text())


def _check(obj, schema_name, label):
    errors = sorted(Draft202012Validator(_schema(schema_name)).iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        msg = "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors[:5])
        raise SystemExit(f"INVALID {label}: {msg}")


def load_sessions():
    lines = [l for l in (config.DATA_DIR / "sessions.jsonl").read_text().splitlines() if l.strip()]
    sessions = [json.loads(l) for l in lines]
    from datetime import datetime
    for i, s in enumerate(sessions, 1):
        _check(s, "sessions.schema.json", f"sessions.jsonl line {i}")
        try:
            datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            raise SystemExit(f"INVALID sessions.jsonl line {i}: timestamp not ISO 8601")
    return sessions


def load_suite():
    suite = json.loads((config.DATA_DIR / "replay_tasks.json").read_text())
    _check(suite, "replay_tasks.schema.json", "replay_tasks.json")
    return suite


def check_ledger(ledger):
    _check(ledger, "proof_ledger.schema.json", "proof_ledger.json")


def main():
    sessions, suite = load_sessions(), load_suite()
    print(f"sessions.jsonl: {len(sessions)} lines OK")
    print(f"replay_tasks.json: {len(suite['tasks'])} tasks OK")
    ids = {s["session_id"] for s in sessions}
    missing = [t["id"] for t in suite["tasks"] if t["source_session_id"] not in ids]
    if missing:
        sys.exit(f"tasks reference unknown sessions: {missing}")
    p = config.STATE_DIR / "proof_ledger.json"
    if p.exists():
        check_ledger(json.loads(p.read_text()))
        print("state/proof_ledger.json OK")


if __name__ == "__main__":
    main()
