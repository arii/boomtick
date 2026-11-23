#!/usr/bin/env python3
"""Loopback backend. Never accepts credentials.

Every API route needs `Authorization: Bearer <token>` (per-run token, see main()) plus a Host
(127.0.0.1 or localhost on the server port, or an exact PROOFLOOP_ALLOWED_HOSTS entry) and an Origin that passes
the loopback / extension-ID check. A request with no Origin header (curl,
local scripts) is therefore rejected unless it carries the token.

GET /augment and /ledger expose loop state for the dashboard. GET /skill describes the promoted rule
set. POST /assist {origin, task, recall, open_tabs} returns the page rules for that task (forbidden
values as hashes), context from past sessions, and tab_matches for other open tabs that touch
recorded sessions (see page_assist.py); it never receives page text or field values.
POST /feedback {rule_id, action} records shown / dismissed / rule_wrong for the loop.
Senso is read (never written) here, and Cognee is queried only when the request asks for recall and
PROOFLOOP_ASSIST_RECALL=1 is set for this process.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import clients
import config
import page_assist
import recall as recall_mod
import validate
from atomic import atomic_write_text

DASH = Path(__file__).resolve().parent.parent / "dashboard.html"


def _allowed_origins(port):
    """The only origins the backend answers CORS for, built from server config (never from the request)."""
    out = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    extension = os.environ.get("PROOFLOOP_EXTENSION_ID", "")
    if re.fullmatch("[a-p]{32}", extension):
        out.append(f"chrome-extension://{extension}")
    return out


def cors_origin(origin, port):
    """The configured origin string equal to `origin`, or None. Headers echo this value, not the request's,
    so request text can never reach a response header."""
    return next((o for o in _allowed_origins(port) if o == origin), None)


def allowed_origin(origin, port):
    return cors_origin(origin, port) is not None


_HINTED = set()


def note_rejected_origin(origin):
    """Print one stderr hint per rejected extension origin so the operator can copy the exact ID."""
    if isinstance(origin, str) and re.fullmatch("chrome-extension://[a-p]{32}", origin) and origin not in _HINTED:
        _HINTED.add(origin)
        print(f"rejected {origin}: restart with PROOFLOOP_EXTENSION_ID={origin.split('//', 1)[1]}", file=sys.stderr, flush=True)


MAX_BODY = 16 * 1024
TOKEN = None  # set by main() or PROOFLOOP_TOKEN; None means every API route is refused


def token_ok(header):
    if not TOKEN or not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].encode(), TOKEN.encode())


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
    """Loop state for the dashboard: ledger history, active version and scores, service modes."""
    ledger = _read("proof_ledger.json", {"schema_version": 3, "active_version": "", "entries": []})
    legacy = ledger.get("schema_version") != 3
    run = _read("last_run.json", {})
    pp = prompt_payload()
    stored = page_assist.active()
    return {"active_version": None if legacy else ledger["active_version"], "legacy_state": legacy and bool(ledger.get("entries")),
            "scores": (stored or {}).get("scores"), "stop": run.get("stop"),
            "prompt": {"version": pp["version"], "sha256": pp["sha256"]} if pp else None,
            "history": [] if legacy else ledger["entries"], "services": config.status()}


class Ctx:
    """Sessions, suite and optional live clients, loaded once per process."""
    sessions = None
    suite = None
    senso = None
    recall = None

    @classmethod
    def load(cls):
        if cls.sessions is None:
            cls.sessions = validate.load_sessions()
            cls.suite = validate.load_suite()
            cls.senso = clients.SensoLive() if config.mode("senso") == "live" else None
            if config.mode("cognee") == "live" and config.get("PROOFLOOP_ASSIST_RECALL") == "1":
                cls.recall = recall_mod.Recall(clients.CogneeLive(), cls.sessions)
        return cls


FEEDBACK_ACTIONS = {"shown", "dismissed", "rule_wrong"}


def record_feedback(body):
    rule_id, action = body.get("rule_id"), body.get("action")
    stored = page_assist.active()
    known = {r["id"] for r in stored["rules"]["page_rules"]} if stored else set()
    if rule_id not in known or action not in FEEDBACK_ACTIONS:
        return False, "unknown rule_id or action"
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rule_id": rule_id, "action": action,
                       "version": stored["rules"]["version"]}) + "\n"
    p = config.STATE_DIR / "feedback.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:  # one short line per write
        f.write(line)
    return True, ""


HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?:[0-9]{1,5}$|^\[[0-9a-f:]+\]:[0-9]{1,5}$")


def allowed_hosts_from_env():
    """Extra Host header values accepted besides 127.0.0.1:<port> and localhost:<port>.

    PROOFLOOP_ALLOWED_HOSTS is a comma-separated list of exact host:port values (for example
    "proofloop.lan:8787,192.168.1.20:8787"), for a backend reached by another name or address. Entries without a
    port, with a path or scheme, or with wildcards are ignored, so a value can never widen to "any host" and DNS
    rebinding stays blocked for every name that is not listed."""
    out = []
    for raw in os.environ.get("PROOFLOOP_ALLOWED_HOSTS", "").split(","):
        h = raw.strip().lower()
        if h and HOST_RE.match(h):
            out.append(h)
    return out


def host_allowed(host, port):
    if not isinstance(host, str):
        return False
    h = host.strip().lower()
    return h in (f"127.0.0.1:{port}", f"localhost:{port}") or h in allowed_hosts_from_env()


def bind_host_from_env():
    """Loopback unless PROOFLOOP_BIND_HOST is set (e.g. 0.0.0.0 inside a container whose port is published to loopback)."""
    return os.environ.get("PROOFLOOP_BIND_HOST", "").strip() or "127.0.0.1"


def is_loopback_host(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def bind_warning(host):
    return (f"WARNING: PROOFLOOP_BIND_HOST={host} is not loopback. Only the bearer token protects this backend, and "
            "traffic is plain HTTP. Publish the port to 127.0.0.1 only, or use TLS or an SSH tunnel.")


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        port = self.server.server_port
        if not host_allowed(self.headers.get("Host"), port):
            return False
        origin = self.headers.get("Origin")
        ok = origin is None or allowed_origin(origin, port)
        if not ok:
            note_rejected_origin(origin)
        return ok

    def _api_authorized(self):
        """Host/origin check plus bearer token. Used by every route that returns or changes state."""
        return self._authorized() and token_ok(self.headers.get("Authorization"))

    def _send(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        allow = cors_origin(self.headers.get("Origin", ""), self.server.server_port)
        if allow:
            self.send_header("Access-Control-Allow-Origin", allow)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self._authorized():
            self.send_response(204)
            allow = cors_origin(self.headers.get("Origin", ""), self.server.server_port)
            if allow:
                self.send_header("Access-Control-Allow-Origin", allow)
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST")
                self.send_header("Vary", "Origin")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send(403, b"")

    def do_GET(self):
        self._safely(self._get)

    def do_POST(self):
        self._safely(self._post)

    def _safely(self, fn):
        """A corrupt state file or other unexpected error returns a short JSON 500, never a traceback or a dropped connection."""
        try:
            fn()
        except (ValueError, OSError, KeyError, TypeError) as e:
            print(f"request failed: {type(e).__name__}", file=sys.stderr, flush=True)
            try:
                self._send(500, {"error": f"server state unreadable ({type(e).__name__}); check PROOFLOOP_STATE files"})
            except OSError as send_err:
                print(f"could not send error response: {type(send_err).__name__}", file=sys.stderr, flush=True)

    def _get(self):
        if not self._authorized():
            return self._send(403, {"error": "host/origin not allowed"})
        path = urlparse(self.path).path
        if path in ("/", "/dashboard"):
            return self._send(200, DASH.read_bytes(), "text/html; charset=utf-8")  # static, no state
        if not self._api_authorized():
            return self._send(403, {"error": "missing or invalid token"})
        if path == "/augment":
            return self._send(200, augment())
        if path == "/ledger":
            ledger = _read("proof_ledger.json", {"schema_version": 3, "active_version": "", "entries": []})
            if ledger.get("schema_version") != 3:
                return self._send(409, {"error": "legacy ledger; select separate state directory or explicitly reset"})
            return self._send(200, {"ledger": ledger, "run": _read("last_run.json", {})})
        if path == "/prompt":
            pp = prompt_payload()
            return self._send(200, pp) if pp else self._send(404, {"error": "no active prompt yet; run replay_loop.py"})
        if path == "/status":
            return self._send(200, config.status())
        if path == "/tasks":
            return self._send(200, json.loads((config.SCHEMA_DIR / "tasks.json").read_text()))
        if path == "/skill":
            try:
                stored = page_assist.active(Ctx.load().sessions)
            except ValueError as e:
                return self._send(409, {"error": str(e)[:300]})
            if not stored:
                return self._send(404, {"error": "no promoted rule set yet"})
            return self._send(200, {"version": stored["rules"]["version"], "sha256": stored["sha256"], "scores": stored.get("scores"),
                                    "source": page_assist.source_tag(stored, Ctx.load().senso), "rules": stored["rules"]})
        self._send(404, {"error": "not found"})

    def _json_body(self):
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            self._send(415, {"error": "application/json required"})
            return None
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return None
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            self._send(400, {"error": "invalid json"})
            return None
        if not isinstance(body, dict):
            self._send(400, {"error": "json object required"})
            return None
        return body

    def _post(self):
        path = urlparse(self.path).path
        if path not in ("/assist", "/feedback"):
            return self._send(410, {"error": "credential/config writes disabled; no browser key storage"})
        if not self._api_authorized():
            return self._send(403, {"error": "host/origin not allowed or missing token"})
        body = self._json_body()
        if body is None:
            return
        if path == "/assist":
            c = Ctx.load()
            return self._send(200, page_assist.assist(body, c.sessions, c.suite, c.senso, c.recall))
        ok, err = record_feedback(body)
        return self._send(200 if ok else 400, {"ok": True} if ok else {"error": err})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    TOKEN = os.environ.get("PROOFLOOP_TOKEN") or secrets.token_urlsafe(24)
    token_file = config.STATE_DIR / "server_token"
    atomic_write_text(token_file, TOKEN + "\n")
    os.chmod(token_file, 0o600)
    bind_host = bind_host_from_env()
    print(f"ProofLoop backend on http://{bind_host}:{port}")
    if not is_loopback_host(bind_host):
        print(bind_warning(bind_host), file=sys.stderr, flush=True)
    extra = allowed_hosts_from_env()
    if extra:
        print(f"Also accepting Host: {', '.join(extra)} (PROOFLOOP_ALLOWED_HOSTS). Requests still need the token and an allowed Origin.",
              file=sys.stderr, flush=True)
    print(f"API token written to {token_file} (mode 600). Paste it into the extension options page.")
    HTTPServer((bind_host, port), Handler).serve_forever()
