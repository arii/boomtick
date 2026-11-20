"""Offline tests for the Tokens with Taste (local gateway) mutation backend. No network."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
import clients
import config
import health
import replay_loop


class TwtBackendTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        for target in ("urllib.request.urlopen", "socket.socket.connect", "socket.getaddrinfo"):
            guard = patch(target, side_effect=AssertionError("offline test attempted external execution"))
            guard.start()
            self.addCleanup(guard.stop)

    def reply(self, content):
        return (200, {"choices": [{"message": {"content": content}}]})

    def test_not_active_without_explicit_opt_in(self):
        self.assertIsNone(config.llm_backend())
        self.assertEqual(config.mode("llm"), "stub")

    def test_explicit_activation_needs_no_key(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        self.assertEqual(config.llm_backend(), "twt")
        self.assertEqual(config.mode("llm"), "live")
        self.assertIn("Tokens with Taste", config.status()["llm"]["label"])
        self.assertIn("unverified", config.status()["llm"]["label"])

    def test_force_stub_overrides(self):
        os.environ.update(PROOFLOOP_LIVE_SERVICES="twt", PROOFLOOP_FORCE_STUB="1")
        self.assertIsNone(config.llm_backend())

    def test_non_loopback_gateway_url_is_ignored(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        for bad in ("http://example.com/v1", "https://127.0.0.1:8000/v1", "http://127.0.0.1.evil.com/v1",
                    "http://169.254.169.254/v1"):
            os.environ["TWT_BASE_URL"] = bad
            self.assertEqual(config.twt_base_url(), "", bad)
            self.assertIsNone(config.llm_backend(), bad)

    def test_loopback_variants_accepted(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        for ok in ("http://127.0.0.1:9000/v1", "http://localhost:8000/v1/"):
            os.environ["TWT_BASE_URL"] = ok
            self.assertEqual(config.llm_backend(), "twt", ok)

    def test_twt_wins_over_openrouter_and_openrouter_still_works(self):
        os.environ.update(PROOFLOOP_LIVE_SERVICES="llm,twt", OPENROUTER_API_KEY="not-a-key")
        self.assertEqual(config.llm_backend(), "twt")
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "llm"
        self.assertEqual(config.llm_backend(), "openrouter")
        del os.environ["OPENROUTER_API_KEY"]
        self.assertIsNone(config.llm_backend())

    def test_request_shape_and_privacy(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        seen = {}

        def fake(method, url, headers=None, body=None, timeout=0, retries=0):
            seen.update(method=method, url=url, headers=headers, body=body)
            return self.reply('Sure: {"add": ["trace_to_source", "bogus_step", "ground_in_related_tabs"]}')

        with patch.object(clients, "http_json", fake):
            added = clients.llm_propose_steps({"must_include": 2}, agent.KNOWN_STEPS, [agent.BASE_STEP, "ground_in_related_tabs"])
        self.assertEqual(added, ["trace_to_source"])  # unknown and already-present ids dropped
        self.assertEqual(seen["url"], "http://127.0.0.1:8000/v1/chat/completions")
        self.assertEqual(seen["body"]["model"], "default")
        self.assertNotIn("Authorization", seen["headers"])
        self.assertEqual(seen["headers"]["X-Session-Id"], "proofloop-mutation")
        prompt = seen["body"]["messages"][0]["content"]
        for private in ("San Francisco", "[PHONE", "arii.github.io", "onasafari"):
            self.assertNotIn(private, prompt)

    def test_garbage_reply_yields_no_steps(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        for content in ("no json here", "{not valid json}", None, ""):
            with patch.object(clients, "http_json", lambda *a, **k: self.reply(content)):
                self.assertEqual(clients.llm_propose_steps({}, agent.KNOWN_STEPS, []), [])

    def test_gateway_failure_falls_back_to_rule_based(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        rep = agent.replay({"version": "v0", "steps": [agent.BASE_STEP]}, __import__("validate").load_suite()["tasks"])
        with patch.object(clients, "http_json", side_effect=clients.ApiError(502, "waterfall exhausted")):
            steps, how = replay_loop.mutate({"version": "v0", "steps": [agent.BASE_STEP]}, rep)
        self.assertIn("rule-based", how)
        self.assertIn("ground_in_related_tabs", steps)

    def test_health_green_and_red(self):
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "twt"
        with patch.object(clients, "http_json", lambda *a, **k: self.reply("hi")):
            self.assertEqual(health.check_llm()[0], "GREEN")
        with patch.object(clients, "http_json", side_effect=clients.ApiError(0, "refused")):
            with self.assertRaises(clients.ApiError):
                health.check_llm()
        self.assertEqual(health.check_llm.__name__, "check_llm")


if __name__ == "__main__":
    unittest.main()
