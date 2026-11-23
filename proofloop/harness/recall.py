"""Cognee recall over the session log.

ingest() uploads the redacted sessions once per content hash. search() asks Cognee and maps the
returned chunks back to session ids, then returns the extracted constraint and outcome from
sessions.jsonl, never the raw chunk. Mode is "live" or "disabled"; there is no local imitation.
"""
import hashlib
import json
import re

import config
from atomic import atomic_write_json

SID = re.compile(r"sess_\d{4}_\d{2}_\d{2}_[a-z0-9_]+")


class Recall:
    def __init__(self, cognee, sessions, enabled=True):
        self.cognee = cognee
        self.sessions = {s["session_id"]: s for s in sessions}
        self.mode = "live" if (enabled and cognee is not None) else "disabled"
        self.digest = hashlib.sha256("\n".join(json.dumps(s, sort_keys=True) for s in sessions).encode()).hexdigest()
        self.queries = 0

    def ingest(self):
        if self.mode != "live":
            return {"mode": self.mode}
        marker = config.STATE_DIR / "cognee_ingest.json"
        prev = json.loads(marker.read_text()) if marker.exists() else {}
        if prev.get("sessions_sha256") == self.digest and prev.get("dataset") == self.cognee.DATASET:
            return {"mode": "live", "ingested": "unchanged", "sessions": len(self.sessions)}
        res = self.cognee.ingest(list(self.sessions.values()))
        atomic_write_json(marker, {"sessions_sha256": self.digest, "dataset": self.cognee.DATASET, "result": res})
        return {"mode": "live", "ingested": res, "sessions": len(self.sessions)}

    def search(self, query, k=4):
        """[{session_id, task, outcome, constraint}] for the top sessions Cognee returns."""
        if self.mode != "live":
            return []
        self.queries += 1
        ids = []
        for hit in self.cognee.search(query[:500]):
            found = hit.get("session_ids") or SID.findall(json.dumps(hit))
            for sid in found:
                if sid in self.sessions and sid not in ids:
                    ids.append(sid)
        return [excerpt(self.sessions[sid]) for sid in ids[:k]]


def excerpt(session):
    return {"session_id": session["session_id"], "task": session["query_or_task"][:240],
            "outcome": session["outcome_or_error"][:400], "constraint": session["constraint"][:300],
            "site": (session.get("active_tab") or {}).get("url", "")}
