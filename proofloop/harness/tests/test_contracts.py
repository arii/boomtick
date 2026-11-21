"""Contracts between the loop, Senso, Cognee recall and the page backend, plus gate edge cases.
Fakes are injected in test code only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clients  # noqa: E402
import config  # noqa: E402
import gate  # noqa: E402
import page_assist  # noqa: E402
import recall as recall_mod  # noqa: E402
import replay_loop  # noqa: E402
import rules as rules_mod  # noqa: E402
from fakes import FakeCognee, FakeSenso  # noqa: E402
from services import Services  # noqa: E402
from test_loop import CITY, PHONE, SESSIONS  # noqa: E402

RULES = {"version": "v2", "parent": "v1", "instructions": [], "page_rules": [CITY, PHONE]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.STATE_DIR
        config.STATE_DIR = Path(self.tmp.name)
        page_assist._cache["senso"].clear()

    def tearDown(self):
        config.STATE_DIR = self.old
        self.tmp.cleanup()


class SensoRoundTrip(Base):
    """The text the loop promotes must be what the page backend can confirm."""

    def promoted(self, senso):
        rec = replay_loop.promote(Services(senso=senso), RULES, {"train": 1.0}, {"choice": "promote"})
        return {"rules": RULES, "sha256": rules_mod.sha256(RULES), "senso": rec}, rec

    def test_promote_then_page_confirms_the_node(self):
        senso = FakeSenso()
        stored, rec = self.promoted(senso)
        self.assertTrue(rec["verified"])
        tag = page_assist.source_tag(stored, senso)
        self.assertEqual(tag["kind"], "senso", tag)
        self.assertIn(rec["node_id"], tag["label"])

    def test_each_failure_reason_is_named(self):
        senso = FakeSenso()
        stored, rec = self.promoted(senso)
        node = rec["node_id"]
        cases = {
            "hash differs": lambda: senso.docs[node].update(text=senso.docs[node]["text"].replace('"San Jose"', '"Oakland"')),
            "not the stored rule set JSON": lambda: senso.docs[node].update(text="plain text"),
            "not a ProofLoop rule set": lambda: senso.docs[node].update(text=json.dumps({"type": "other"})),
        }
        original = senso.docs[node]["text"]
        for reason, mutate in cases.items():
            page_assist._cache["senso"].clear()
            senso.docs[node]["text"] = original
            mutate()
            tag = page_assist.source_tag(stored, senso)
            self.assertEqual(tag["kind"], "senso-mismatch")
            self.assertIn(reason, tag["label"])

        class Down(FakeSenso):
            def read_text(self, nid):
                raise clients.ApiError(503, "unavailable")
        page_assist._cache["senso"].clear()
        tag = page_assist.source_tag(stored, Down())
        self.assertIn("read failed (ApiError: HTTP 503", tag["label"])

    def test_failed_read_is_retried_after_30s_but_success_is_cached_5_min(self):
        senso = FakeSenso()
        stored, rec = self.promoted(senso)
        t = [1000.0]
        calls = []
        real = senso.read_text

        def counting(nid):
            calls.append(t[0])
            return real(nid)
        senso.read_text = counting
        page_assist.source_tag(stored, senso, now=lambda: t[0])
        t[0] += 299
        page_assist.source_tag(stored, senso, now=lambda: t[0])
        self.assertEqual(len(calls), 1, "a confirmed read is reused for 5 minutes")
        page_assist._cache["senso"].clear()
        senso.docs[rec["node_id"]]["text"] = "broken"
        page_assist.source_tag(stored, senso, now=lambda: t[0])
        t[0] += 31
        page_assist.source_tag(stored, senso, now=lambda: t[0])
        self.assertEqual(len(calls), 3, "a failed read is retried after 30 seconds")


class RecallContract(Base):
    def test_ingest_once_per_content_and_again_when_sessions_change(self):
        cg = FakeCognee(SESSIONS)
        r = recall_mod.Recall(cg, SESSIONS)
        self.assertEqual(r.ingest()["sessions"], len(SESSIONS))
        self.assertEqual(r.ingest()["ingested"], "unchanged")
        self.assertEqual(cg.ingested, 1)
        changed = SESSIONS[:-1]
        recall_mod.Recall(cg, changed).ingest()
        self.assertEqual(cg.ingested, 2)

    def test_search_returns_extracted_fields_never_raw_chunks(self):
        class Chunky(FakeCognee):
            def search(self, query):
                return [{"text": "RAW CHUNK TEXT sess_2026_11_18_waas and sess_2099_01_01_nope"}]
        out = recall_mod.Recall(Chunky(SESSIONS), SESSIONS).search("phone")
        self.assertEqual([x["session_id"] for x in out], ["sess_2026_11_18_waas"], "ids not in sessions.jsonl are dropped")
        self.assertEqual(set(out[0]), {"session_id", "task", "outcome", "constraint", "site"})
        self.assertNotIn("RAW CHUNK", json.dumps(out))

    def test_disabled_recall_never_calls_cognee(self):
        cg = FakeCognee(SESSIONS)
        r = recall_mod.Recall(cg, SESSIONS, enabled=False)
        self.assertEqual((r.ingest(), r.search("x")), ({"mode": "disabled"}, []))
        self.assertEqual((cg.ingested, cg.queries), (0, []))


class GateEdges(unittest.TestCase):
    def test_no_holdout_tasks_still_decides_on_train(self):
        base = {"a": {"score": 0.0, "split": "train"}, "b": {"score": 0.0, "split": "train"}}
        cand = {"a": {"score": 1.0, "split": "train"}, "b": {"score": 1.0, "split": "train"}}
        g = gate.decide(base, cand, 3)
        self.assertEqual(g["choice"], "promote")
        self.assertIsNone(g["holdout_before"])

    def test_different_task_sets_are_refused(self):
        with self.assertRaises(ValueError):
            gate.decide({"a": {"score": 0, "split": "train"}}, {"b": {"score": 1, "split": "train"}}, 3)
        with self.assertRaises(ValueError):
            gate.decide({}, {}, 3)

    def test_three_task_suite_needs_more_than_one_sample_of_gain(self):
        # The committed suite has 2 train tasks; with 3 samples one task moving 0 -> 1/3 is within noise.
        base = {"a": {"score": 0.0, "split": "train"}, "b": {"score": 0.0, "split": "train"}, "h": {"score": 0.0, "split": "holdout"}}
        one_sample = dict(base, a={"score": 1 / 3, "split": "train"})
        self.assertEqual(gate.decide(base, one_sample, 3)["choice"], "hold")
        two_samples = dict(base, a={"score": 2 / 3, "split": "train"})
        self.assertEqual(gate.decide(base, two_samples, 3)["choice"], "promote")


if __name__ == "__main__":
    unittest.main()
