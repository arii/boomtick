#!/usr/bin/env python3
"""Read-only loopback backend. Never accepts credentials or searches page titles.

GET /augment exposes local replay status only. Live sponsor work is performed
by the separately activated harness, never by background browser requests.
"""
import hashlib
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import config

DASH = Path(__file__).resolve().parent.parent / "dashboard.html"


def allowed_origin(origin, port):
    if origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
        return True
    extension = os.environ.get("PROOFLOOP_EXTENSION_ID", "")
    return bool(re.fullmatch("[a-p]{32}", extension) and origin == f"chrome-extension://{extension}")


_HINTED = set()


def note_rejected_origin(origin):
    """Print one stderr hint per rejected extension origin so the operator can copy the exact ID."""
    if isinstance(origin, str) and re.fullmatch("chrome-extension://[a-p]{32}", origin) and origin not in _HINTED:
        _HINTED.add(origin)
        print(f"rejected {origin}: restart with PROOFLOOP_EXTENSION_ID={origin.split('//', 1)[1]}", file=sys.stderr, flush=True)


def _read(name, default):
    p = config.STATE_DIR / name
    return json.loads(p.read_text()) if p.exists() else default


def prompt_payload():
    """Active prompt text written by the replay loop, or None before the first run."""
    path = config.STATE_DIR / "active_prompt.md"
    if not path.exists():
        return None
    text = path.read_text()
    return {"version": _read("last_run.json", {}).get("prompt", {}).get("version"),
            "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}


def augment():
    ledger = _read("proof_ledger.json", {"active_version": "", "entries": []})
    run = _read("last_run.json", {})
    legacy = ledger.get("schema_version") != 2
    history = [] if legacy else ledger["entries"]
    promoted = [e for e in history if e["status"] == "promoted"]
    last = promoted[-1] if promoted else None
    pp = prompt_payload()
    return {"active_version": None if legacy else ledger["active_version"],
            "prompt": {"version": pp["version"], "sha256": pp["sha256"]} if pp else None,
            "pass": run.get("active", {}).get("passed"), "total": run.get("active", {}).get("total"),
            "last_promoted": last, "history": history, "services": config.status(),
            "retrieval": last.get("retrieval") if last else None,
            "legacy_state": legacy and bool(ledger.get("entries")),
            "scope": "deterministic replay only; no page data sent to sponsors"}


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        ok = origin is None or allowed_origin(origin, port)
        if not ok:
            note_rejected_origin(origin)
        return ok

    def _send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin", "")
        if allowed_origin(origin, self.server.server_port):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204 if self._authorized() else 403, b"")

    def do_GET(self):
        if not self._authorized():
            return self._send(403, {"error": "host/origin not allowed"})
        path = urlparse(self.path).path
        if path == "/augment":
            return self._send(200, augment())
        if path == "/ledger":
            ledger = _read("proof_ledger.json", {"schema_version": 2, "active_version": "", "entries": []})
            if ledger.get("schema_version") != 2:
                return self._send(409, {"error": "legacy ledger; select separate state directory or explicitly reset"})
            return self._send(200, {"ledger": ledger, "run": _read("last_run.json", {})})
        if path == "/prompt":
            pp = prompt_payload()
            return self._send(200, pp) if pp else self._send(404, {"error": "no active prompt yet; run replay_loop.py"})
        if path == "/status":
            return self._send(200, config.status())
        if path in ("/", "/dashboard"):
            return self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        self._send(410, {"error": "credential/config writes disabled; no browser key storage"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    print(f"ProofLoop read-only backend on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
