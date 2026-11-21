"""Backend auth, /skill, /assist and /feedback. Runs a real server on an ephemeral loopback port."""
# Rule fixtures here are test data for the server, not shipped rules.
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
import config  # noqa: E402
import page_assist  # noqa: E402
import rules as rules_mod  # noqa: E402
import server  # noqa: E402

TOKEN = "test-token-0123456789"
RULES = {"version": "v2", "parent": "v1", "instructions": [], "page_rules": [
    {"id": "city-not-san-jose", "kind": "forbid_value", "field": "city", "forbid": ["San Jose"], "expect": "San Francisco",
     "tasks": ["event_registration"], "message": "Your sessions say San Francisco, not San Jose.", "provenance": ["sess_2026_11_16_luma"]},
    {"id": "phone-pro", "kind": "forbid_value", "field": "phone", "forbid": ["[PHONE-FAMILY]"], "expect": "[PHONE-PRO]",
     "tasks": ["job_application"], "message": "Use your professional number.", "provenance": ["sess_2026_11_18_waas"]},
    {"id": "no-sponsor-consent", "kind": "keep_unchecked", "label_all": ["sponsor"], "tasks": ["event_registration"],
     "message": "You did not want to share contact info with sponsors.", "provenance": ["sess_2026_11_16_luma"]}]}
EXT = "a" * 32


class AssistServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old = (config.STATE_DIR, server.TOKEN, os.environ.get("PROOFLOOP_EXTENSION_ID"))
        config.STATE_DIR = Path(cls.tmp.name)
        (config.STATE_DIR / "active_rules.json").write_text(json.dumps({"rules": RULES, "sha256": rules_mod.sha256(RULES),
                                                                         "scores": {"train": 1.0}, "senso": {"node_id": "n1", "verified": True}}))
        server.Ctx.sessions = None
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

    def test_skill_describes_promoted_rules_and_source(self):
        status, data = self.req("GET", "/skill")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], "v2")
        self.assertEqual(data["source"]["kind"], "senso-copy", "Senso is not enabled in tests, so the tag says local copy")

    def test_assist_scopes_by_task_and_hashes_values(self):
        status, data = self.req("POST", "/assist", {"origin": "https://luma.com/x?secret=1", "task": "event_registration", "title": "SECRET"})
        self.assertEqual(status, 200)
        self.assertEqual([r["id"] for r in data["page_rules"]], ["city-not-san-jose", "no-sponsor-consent"])
        city = data["page_rules"][0]
        self.assertEqual(city["forbid"][0]["sha256"], page_assist.value_hash("city", "san  josé"))
        blob = json.dumps(data)
        self.assertNotIn("SECRET", blob)
        self.assertNotIn('"San Jose"', blob.replace('"label": "San Jose"', ""), "values travel as hashes; only the label is text")
        self.assertTrue(any(c["session_id"] == "sess_2026_11_16_luma" and c["why"] == "this site" for c in data["context"]))
        self.assertEqual(data["recall"], "not requested")

    def test_assist_open_tabs_match_is_cached(self):
        body = {"origin": "https://luma.com", "task": "event_registration", "open_tabs": [
            {"origin": "https://boomtick.blog/ads.txt?x=1", "title": "ads.txt"},
            {"origin": "https://unrelated.example/", "title": "nothing here"},
            {"origin": "chrome://settings", "title": "nope"},
            {"origin": "https://luma.com/other", "title": "active page itself"},
            "junk",
        ]}
        data = self.req("POST", "/assist", body)[1]
        self.assertEqual([m["origin"] for m in data["tab_matches"]], ["https://boomtick.blog"])
        self.assertTrue(any(s["session_id"] == "sess_2026_11_17_adsense" for s in data["tab_matches"][0]["sessions"]))
        self.assertNotIn("cached", data)
        again = self.req("POST", "/assist", body)[1]
        self.assertTrue(again.get("cached"), "identical tab set hits the assist cache")

    def test_assist_unknown_task_and_placeholder_without_private_value(self):
        self.assertEqual(self.req("POST", "/assist", {"origin": "https://x.example", "task": "rm -rf"})[1]["task"], "other")
        data = self.req("POST", "/assist", {"origin": "https://x.example", "task": "job_application"})[1]
        phone = data["page_rules"][0]
        self.assertEqual(phone["forbid"][0], {"sha256": None, "label": "[PHONE-FAMILY]", "resolved": False})

    def test_tampered_or_ungrounded_rules_are_refused(self):
        p = config.STATE_DIR / "active_rules.json"
        good = p.read_text()
        try:
            bad = json.loads(good)
            bad["rules"]["page_rules"][0]["forbid"] = ["Oakland"]  # not in the cited session, and the hash no longer matches
            p.write_text(json.dumps(bad))
            data = self.req("POST", "/assist", {"origin": "https://luma.com", "task": "event_registration"})[1]
            self.assertEqual(data["page_rules"], [])
            self.assertEqual(data["source"]["kind"], "invalid")
            self.assertEqual(self.req("GET", "/skill")[0], 409)
        finally:
            p.write_text(good)

    def test_phone_normalization_matches_formats(self):
        h = page_assist.value_hash("phone", "(415) 555-0100")
        for v in ("415-555-0100", "+1 415 555 0100", "4155550100"):
            self.assertEqual(page_assist.value_hash("phone", v), h)
        self.assertNotEqual(page_assist.value_hash("phone", "415-555-0101"), h)

    def test_post_requires_token_json_and_size_limit(self):
        self.assertEqual(self.req("POST", "/assist", {"origin": "https://luma.com"}, token=False, origin=None)[0], 403)
        self.assertEqual(self.req("POST", "/assist", b"x", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.req("POST", "/assist", b"{" + b" " * 20000 + b"}", headers={"Content-Type": "application/json"})[0], 413)
        self.assertEqual(self.req("POST", "/assist", b"not json", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.req("POST", "/assist", b"[1]", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.req("POST", "/config", {"k": "v"})[0], 410)

    def test_feedback_validates_and_appends(self):
        self.assertEqual(self.req("POST", "/feedback", {"rule_id": "city-not-san-jose", "action": "rule_wrong"})[0], 200)
        self.assertEqual(self.req("POST", "/feedback", {"rule_id": "rule.nope", "action": "dismissed"})[0], 400)
        self.assertEqual(self.req("POST", "/feedback", {"rule_id": "city-not-san-jose", "action": "../../etc"})[0], 400)
        lines = (config.STATE_DIR / "feedback.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["action"], "rule_wrong")
        self.assertNotIn("San", lines[0])


if __name__ == "__main__":
    unittest.main()
