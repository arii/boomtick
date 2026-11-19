import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("TWT_DB", "~/.local/share/twt/catalog.sqlite3")).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS models (
                provider TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY(provider, id));
            CREATE TABLE IF NOT EXISTS traces (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                trace_id TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY(trace_id, ordinal));
            CREATE TABLE IF NOT EXISTS tool_calls (
                session TEXT NOT NULL, signature TEXT NOT NULL,
                PRIMARY KEY(session, signature));
        """)
        self.db.commit()
        os.chmod(self.path, 0o600)

    def replace_models(self, provider, models):
        with self.db:
            self.db.execute("DELETE FROM models WHERE provider=?", (provider,))
            self.db.executemany("INSERT INTO models VALUES (?, ?, ?)", [
                (provider, m["id"], json.dumps(m)) for m in models
            ])

    def models(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT data FROM models ORDER BY provider,id")]

    def save_trace(self, trace):
        with self.db:
            self.db.execute("INSERT INTO traces VALUES (?, ?, ?)",
                            (trace["trace_id"], trace["timestamp"], json.dumps(trace)))
            self.db.executemany("INSERT INTO attempts VALUES (?, ?, ?)", [
                (trace["trace_id"], i, json.dumps(a)) for i, a in enumerate(trace["attempts"])
            ])

    def traces(self, since=None):
        rows = self.db.execute("SELECT data FROM traces WHERE timestamp >= ? ORDER BY timestamp", (since or "",))
        return [json.loads(r[0]) for r in rows]

    def trace(self, trace_id):
        row = self.db.execute("SELECT data FROM traces WHERE id=?", (trace_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def spend_today(self):
        day = datetime.now(timezone.utc).date().isoformat()
        return sum(t["known_cost_usd"] for t in self.traces(day))

    def repeated_tools(self, session, signatures):
        if not session:
            return False
        repeated = False
        with self.db:
            for signature in signatures:
                cursor = self.db.execute("INSERT OR IGNORE INTO tool_calls VALUES (?, ?)", (session, signature))
                repeated |= cursor.rowcount == 0
        return repeated

    def close(self):
        self.db.close()
