"""Backend auth, /skill, /assist and /feedback. Runs a real server on an ephemeral loopback port."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cards  # noqa: E402
import config  # noqa: E402
import server  # noqa: E402

TOKEN = "test-token-0123456789"
EXT = "a" * 32


class AssistServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = (config.STATE_DIR, server.TOKEN, os.environ.get("PROOFLOOP_EXTENSION_ID"))
        config.STATE_DIR = Path(cls.tmp.name)
        server.TOKEN = TOKEN
        os.environ["PROOFLOOP_EXTENSION_ID"] = EXT
        cls.httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        config.STATE_DIR, server.TOKEN, ext = cls.old
        if ext is None:
            os.environ.pop("PROOFLOOP_EXTENSION_ID", None)
        else:
            os.environ["PROOFLOOP_EXTENSION_ID"] = ext
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None, token=True, origin=f"chrome-extension://{EXT}", host=None):
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["Authorization"] = f"Bearer {TOKEN}"
        if origin:
            h["Origin"] = origin
        if body is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.putrequest(method, path, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        c.putheader("Content-Length", str(len(data or b"")))
        c.endheaders(data)
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw

    def test_missing_origin_without_token_is_403_on_every_api_route(self):
        for path in ("/status", "/ledger", "/augment", "/prompt", "/skill"):
            self.assertEqual(self.req("GET", path, token=False, origin=None)[0], 403, path)

    def test_token_without_origin_works_for_local_scripts_and_dashboard(self):
        self.assertEqual(self.req("GET", "/status", origin=None)[0], 200)

    def test_wrong_origin_is_403_even_with_token(self):
        for origin in ("https://evil.example", "null", "http://localhost.evil:%d" % self.port, "chrome-extension://" + "b" * 32):
            self.assertEqual(self.req("GET", "/skill", origin=origin)[0], 403, origin)

    def test_wrong_token_and_wrong_host(self):
        self.assertEqual(self.req("GET", "/skill", headers={"Authorization": "Bearer nope"})[0], 403)
        self.assertEqual(self.req("GET", "/skill", host="evil.example")[0], 403)

    def test_dashboard_html_is_static_and_needs_no_token(self):
        status, body = self.req("GET", "/", token=False, origin=None)
        self.assertEqual(status, 200)
        self.assertIn(b"ProofLoop", body)

    def test_unset_extension_id_rejects_extension_origin(self):
        old = os.environ.pop("PROOFLOOP_EXTENSION_ID")
        try:
            self.assertEqual(self.req("GET", "/skill")[0], 403)
        finally:
            os.environ["PROOFLOOP_EXTENSION_ID"] = old

    def test_skill_returns_valid_hashed_cards(self):
        status, data = self.req("GET", "/skill")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["sha256"]), 64)
        self.assertIn("rule.city.sf", [c["id"] for c in data["cards"]])

    def test_assist_scopes_by_host_and_ignores_other_fields(self):
        body = {"origin": "https://luma.com", "path": "/personalagenthack", "title": "SECRET", "value": "123 Main"}
        status, data = self.req("POST", "/assist", body)
        self.assertEqual(status, 200)
        self.assertEqual({c["id"] for c in data["cards"]}, {"rule.city.sf", "rule.city.sf.address"})
        self.assertNotIn("SECRET", json.dumps(data))
        for origin in ("https://apply.vouch.us", "https://example.com", "https://luma.com.evil.example", "javascript:alert(1)", ""):
            self.assertEqual(self.req("POST", "/assist", {"origin": origin, "path": "/"})[1]["cards"], [], origin)

    def test_assist_labels_recall_as_not_wired(self):
        self.assertEqual(self.req("POST", "/assist", {"origin": "https://luma.com", "path": "/"})[1]["recall"]["mode"], "none")

    def test_post_requires_token_json_and_size_limit(self):
        self.assertEqual(self.req("POST", "/assist", {"origin": "https://luma.com"}, token=False, origin=None)[0], 403)
        self.assertEqual(self.req("POST", "/assist", b"x", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.req("POST", "/assist", b"{" + b" " * 20000 + b"}", headers={"Content-Type": "application/json"})[0], 413)
        self.assertEqual(self.req("POST", "/assist", b"not json", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.req("POST", "/config", {"k": "v"})[0], 410)

    def test_feedback_validates_and_appends(self):
        self.assertEqual(self.req("POST", "/feedback", {"card_id": "rule.city.sf", "action": "kept_value"})[0], 200)
        self.assertEqual(self.req("POST", "/feedback", {"card_id": "rule.nope", "action": "kept_value"})[0], 400)
        self.assertEqual(self.req("POST", "/feedback", {"card_id": "rule.city.sf", "action": "../../etc"})[0], 400)
        lines = (config.STATE_DIR / "feedback.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["action"], "kept_value")

    def test_cards_schema_rejects_bad_sets(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "c.json"
            bad.write_text(json.dumps({"version": 1, "cards": [{"id": "x", "kind": "run_code"}]}))
            with self.assertRaises(ValueError):
                cards.load_cards(bad)


if __name__ == "__main__":
    unittest.main()
