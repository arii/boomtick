#!/usr/bin/env python3
"""Local backend for the extension and dashboard (127.0.0.1:8787).

GET  /augment?title=&url=   chip payload (active version, proof, Senso hits, service labels)
GET  /ledger                proof_ledger.json + last_run.json
GET  /status                live/stub mode per service
POST /config                {SENSO_API_KEY, ...} -> state/keys.json (allow-listed names only)
GET  /                      dashboard proof table
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import clients
import config

DASH = Path(__file__).resolve().parent.parent / "dashboard.html"
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "http://127.0.0.1", "http://localhost")


def _read(name, default):
    p = config.STATE_DIR / name
    return json.loads(p.read_text()) if p.exists() else default


def augment(title, url):
    ledger = _read("proof_ledger.json", {"active_version": "", "entries": []})
    run = _read("last_run.json", {})
    promoted = [e for e in ledger["entries"] if e["status"] == "promoted"]
    last = promoted[-1] if promoted else None
    hits = []
    try:
        hits = clients.senso().search(title) if title else []
    except clients.ApiError as e:
        hits = [{"error": str(e)}]
    return {
        "active_version": ledger["active_version"] or None,
        "pass": run.get("active", {}).get("passed"), "total": run.get("active", {}).get("total"),
        "initial": run.get("initial"),
        "last_promoted": last, "history": ledger["entries"],
        "senso_hits": hits, "services": config.status(),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        origin = self.headers.get("Origin", "")
        if origin.startswith(ALLOWED_ORIGIN_PREFIXES):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/augment":
            return self._send(200, augment(q.get("title", ""), q.get("url", "")))
        if u.path == "/ledger":
            return self._send(200, {"ledger": _read("proof_ledger.json", {"active_version": "", "entries": []}),
                                    "run": _read("last_run.json", {})})
        if u.path == "/status":
            return self._send(200, config.status())
        if u.path in ("/", "/dashboard"):
            return self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/config":
            return self._send(404, {"error": "not found"})
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith(ALLOWED_ORIGIN_PREFIXES):
            return self._send(403, {"error": "origin not allowed"})
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "bad json"})
        keys = {k: v for k, v in data.items() if k in config.KEY_NAMES and isinstance(v, str) and v}
        p = config.STATE_DIR / "keys.json"
        cur = json.loads(p.read_text()) if p.exists() else {}
        cur.update(keys)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur))
        p.chmod(0o600)
        self._send(200, {"saved": sorted(keys), "services": config.status()})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    print(f"ProofLoop server on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
