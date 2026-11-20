"""Offline regression tests. No real credentials, browser, server or sponsor calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
import clients
import config
import health
import replay_gate
import replay_loop
import server
import validate


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"PROOFLOOP_FORCE_STUB": "1"}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = patch.object(config, "STATE_DIR", Path(self.tmp.name))
        self.state.start()
        self.addCleanup(self.state.stop)
        # Fail immediately if any tested code attempts networking or server startup.
        for target in ("urllib.request.urlopen", "socket.socket.connect", "socket.getaddrinfo", "server.HTTPServer"):
            guard = patch(target, side_effect=AssertionError("offline test attempted external execution"))
            guard.start()
            self.addCleanup(guard.stop)
        self.tasks = validate.load_suite()["tasks"]
        self.base = {"version": "v0", "steps": [agent.BASE_STEP]}
        self.good = {"version": "v1", "steps": list(agent.KNOWN_STEPS)}
        self.before = agent.replay(self.base, self.tasks)
        self.after = agent.replay(self.good, self.tasks)

    def gate(self, before=None, after=None):
        return replay_gate.decide(before or self.before, after or self.after, self.tasks)

    def test_improvement_promotes(self):
        self.assertEqual(self.gate()["choice"], "promote")
        self.assertNotIn("confidence", self.gate())

    def test_equal_holds(self):
        self.assertEqual(self.gate(self.before, self.before)["choice"], "hold")

    def test_regression_rejects(self):
        self.assertEqual(self.gate(self.after, self.before)["choice"], "reject_and_refine")

    def test_hidden_check_regression_rejected_despite_more_tasks_passing(self):
        # Add a failure to a formerly passing check on a task still passing overall elsewhere.
        after = json.loads(json.dumps(self.after))
        after["results"][0]["failed_checks"] = [self.tasks[0]["required_checks"][0]]
        gate = self.gate(self.before, after)
        # Choose a formerly passing check rather than one the baseline already failed.
        for t, old, new in zip(self.tasks, self.before["results"], after["results"]):
            passing = set(t["required_checks"]) - set(old["failed_checks"])
            if passing:
                new["failed_checks"] = [sorted(passing)[0]]
                break
        gate = self.gate(self.before, after)
        self.assertEqual(gate["choice"], "reject_and_refine")
        self.assertTrue(gate["regressed_checks"])

    def test_same_nonempty_suite_required(self):
        with self.assertRaises(ValueError):
            replay_gate.decide(self.before, self.after, [])
        incomplete = {**self.after, "results": self.after["results"][:-1]}
        with self.assertRaises(ValueError):
            self.gate(after=incomplete)

    def test_duplicates_and_unknown_checks_fail_closed(self):
        duplicate = {**self.after, "results": self.after["results"] + [self.after["results"][0]]}
        with self.assertRaises(ValueError):
            self.gate(after=duplicate)
        bad = json.loads(json.dumps(self.after))
        bad["results"][0]["failed_checks"] = ["unknown"]
        with self.assertRaises(ValueError):
            self.gate(after=bad)

    def test_gate_recomputes_counts(self):
        fake = {**self.before, "passed": 999, "violations": 0, "pass_rate": 1}
        self.assertEqual(self.gate(fake, self.before)["choice"], "hold")

    def test_keys_alone_never_activate(self):
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        os.environ.update(SENSO_API_KEY="test-not-secret", COGNEE_API_URL="http://fixture", COGNEE_API_KEY="test", OPENROUTER_API_KEY="test")
        self.assertTrue(all(v["mode"] == "stub" for v in config.status().values()))

    def test_explicit_activation_and_force_override(self):
        os.environ.update(PROOFLOOP_LIVE_SERVICES="senso", SENSO_API_KEY="test")
        self.assertEqual(config.mode("senso"), "stub")
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        self.assertEqual(config.mode("senso"), "live")
        self.assertEqual(config.mode("llm"), "stub")
        self.assertFalse(config.status()["senso"]["verified"])
        self.assertIn("unverified", config.status()["senso"]["label"])

    def test_missing_credentials_fail_closed(self):
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "senso,cognee,llm"
        self.assertTrue(all(config.mode(s) == "stub" for s in config.NEEDS))

    def test_no_secret_files_read(self):
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        os.environ["PROOFLOOP_LIVE_SERVICES"] = "senso,cognee,llm"
        with patch.object(Path, "read_text", side_effect=AssertionError("unexpected file read")):
            self.assertTrue(all(config.mode(s) == "stub" for s in config.NEEDS))

    def fake_senso(self, hits=True, valid_id=True):
        return types.SimpleNamespace(label="offline fake", post_raw=lambda *a: (202, {"id": "content" if valid_id else None, "kb_node_id": "node"}),
                                     get_node=lambda *a: {"content": {"processing_status": "complete"}},
                                     search=lambda *a: [{"content_id": "content"}] if hits else [])

    def test_senso_readback_mismatch_raises(self):
        with self.assertRaises(clients.ApiError):
            clients.senso_promote(self.fake_senso(False), "fixture", "fixture", "v1")

    def test_senso_missing_id_rejected(self):
        with self.assertRaises(clients.ApiError):
            clients.senso_promote(self.fake_senso(valid_id=False), "fixture", "fixture", "v1")

    def test_senso_matching_readback_labeled_stub(self):
        result = clients.senso_promote(self.fake_senso(), "fixture", "fixture", "v1")
        self.assertEqual(result, {"node_id": "node", "verified": True, "mode": "stub"})

    def cycle(self, sc, steps=None):
        ledger = {"schema_version": 2, "active_version": "v0", "entries": []}
        with contextlib.redirect_stdout(io.StringIO()):
            active, report, candidate = replay_loop.run_cycle(1, self.base, steps or self.good["steps"], "v1", self.tasks, self.before, ledger, sc)
        validate.check_ledger(ledger)
        return active, ledger

    def test_failed_readback_preserves_active_and_records_failure(self):
        active, ledger = self.cycle(self.fake_senso(False))
        self.assertEqual(active, self.base)
        self.assertEqual(ledger["active_version"], "v0")
        self.assertEqual(ledger["entries"][0]["status"], "promotion_failed")

    def test_false_boolean_readback_defense_in_depth(self):
        with patch.object(clients, "senso_promote", return_value={"node_id": "node", "verified": False}):
            active, ledger = self.cycle(self.fake_senso())
        self.assertEqual(active, self.base)
        self.assertEqual(ledger["entries"][0]["status"], "promotion_failed")

    def test_successful_cycle(self):
        active, ledger = self.cycle(self.fake_senso())
        self.assertEqual(active["version"], "v1")
        self.assertEqual(ledger["entries"][0]["retrieval"]["mode"], "stub")

    def test_hold_distinct_from_rollback(self):
        active, ledger = self.cycle(self.fake_senso(), self.base["steps"])
        self.assertEqual(ledger["entries"][0]["status"], "held")
        self.assertEqual(active, self.base)

    def test_server_augment_never_constructs_sponsor_client(self):
        with patch.object(clients, "senso", side_effect=AssertionError("background sponsor request")):
            data = server.augment()
        self.assertIsNone(data["active_version"])

    def test_origin_allowlist_exact(self):
        for origin in ("http://localhost:8787", "http://127.0.0.1:8787"):
            self.assertTrue(server.allowed_origin(origin, 8787))
        for origin in ("http://localhost.evil:8787", "http://127.0.0.1.evil:8787", "http://localhost:9999", "null", "", "chrome-extension://" + "a" * 32):
            self.assertFalse(server.allowed_origin(origin, 8787))
        os.environ["PROOFLOOP_EXTENSION_ID"] = "a" * 32
        self.assertTrue(server.allowed_origin("chrome-extension://" + "a" * 32, 8787))
        self.assertFalse(server.allowed_origin("chrome-extension://" + "a" * 32 + ".evil", 8787))

    def test_host_and_origin_validation(self):
        fake = types.SimpleNamespace(server=types.SimpleNamespace(server_port=8787), headers={"Host": "localhost:8787"})
        self.assertTrue(server.Handler._authorized(fake))
        fake.headers["Host"] = "evil:8787"
        self.assertFalse(server.Handler._authorized(fake))
        fake.headers = {"Host": "localhost:8787", "Origin": "http://localhost.evil:8787"}
        self.assertFalse(server.Handler._authorized(fake))

    def test_rejected_extension_origin_prints_exact_id_hint_once(self):
        server._HINTED.clear()
        ext = "chrome-extension://" + "b" * 32
        with contextlib.redirect_stderr(io.StringIO()) as err:
            server.note_rejected_origin(ext)
            server.note_rejected_origin(ext)
            server.note_rejected_origin("https://evil.example")
            server.note_rejected_origin("chrome-extension://short")
        self.assertEqual(err.getvalue().count("PROOFLOOP_EXTENSION_ID=" + "b" * 32), 1)
        self.assertEqual(err.getvalue().count("rejected"), 1)

    def test_config_post_cannot_write(self):
        sent = []
        fake = types.SimpleNamespace(_send=lambda *args: sent.append(args))
        server.Handler.do_POST(fake)
        self.assertEqual(sent[0][0], 410)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_legacy_ledger_not_presented_as_verified(self):
        (Path(self.tmp.name) / "proof_ledger.json").write_text(json.dumps({"active_version": "old", "entries": [{"status": "promoted"}]}))
        data = server.augment()
        self.assertTrue(data["legacy_state"])
        self.assertIsNone(data["active_version"])
        self.assertEqual(data["history"], [])

    def test_full_offline_replay_and_schema(self):
        with patch.object(sys, "argv", ["replay_loop.py", "--reset", "--bad-demo"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(replay_loop.main(), 0)
        ledger = json.loads((Path(self.tmp.name) / "proof_ledger.json").read_text())
        validate.check_ledger(ledger)
        self.assertEqual([e["tasks_passed_after"] for e in ledger["entries"]], [5, 6, 4])
        self.assertEqual([e["status"] for e in ledger["entries"]], ["promoted", "promoted", "rolled_back"])
        self.assertEqual(ledger["active_version"], "v1.2")
        self.assertEqual(len(validate.load_sessions()), 8)

    def test_health_defaults_to_no_calls_even_when_enabled(self):
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        os.environ.update(PROOFLOOP_LIVE_SERVICES="senso", SENSO_API_KEY="test")
        with patch.object(sys, "argv", ["health.py"]), patch.object(health, "check_senso", side_effect=AssertionError("probe without opt-in")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(health.main(), 0)

    def test_health_probe_with_stubs_makes_no_calls(self):
        with patch.object(sys, "argv", ["health.py", "--probe-live"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(health.main(), 0)

    def test_live_session_upload_requires_explicit_opt_in(self):
        os.environ.pop("PROOFLOOP_FORCE_STUB")
        os.environ.update(PROOFLOOP_LIVE_SERVICES="cognee", COGNEE_API_URL="https://fixture.invalid", COGNEE_API_KEY="test")
        with self.assertRaises(SystemExit):
            replay_loop.ingest_and_recall([], {"tasks": self.tasks})

    def test_legacy_state_rejected_without_mutation(self):
        state = Path(self.tmp.name)
        content = json.dumps({"active_version": "old", "entries": [{"status": "promoted"}]})
        (state / "proof_ledger.json").write_text(content)
        with patch.object(sys, "argv", ["replay_loop.py"]), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            replay_loop.main()
        self.assertEqual((state / "proof_ledger.json").read_text(), content)
        self.assertEqual([p.name for p in state.iterdir()], ["proof_ledger.json"])


if __name__ == "__main__":
    unittest.main()
