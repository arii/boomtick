"""Auto-repeat loop, gate, mutator grounding, task generation and recall, with injected fakes."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clients  # noqa: E402
import config  # noqa: E402
import gate  # noqa: E402
import mutator  # noqa: E402
import replay_loop  # noqa: E402
import rules as rules_mod  # noqa: E402
import skill_prompt  # noqa: E402
import tasks as tasks_mod  # noqa: E402
import validate  # noqa: E402
from services import Services, extract_json  # noqa: E402
from fakes import FakeCognee, FakeLLM, FakeSenso  # noqa: E402

SESSIONS = validate.load_sessions()
BY_ID = {s["session_id"]: s for s in SESSIONS}


def suite():
    def t(sid, kind, checks, split):
        s = BY_ID[sid]
        return {"id": "t_" + sid[5:], "source_session_id": sid, "task_kind": kind, "query": s["query_or_task"],
                "active_tab": s["active_tab"], "related_tabs": s["related_tabs"], "checks": checks, "split": split}
    return {"suite_id": "test", "generated": {"by": "test", "at": "2026-11-20T00:00:00Z", "reviewed": True}, "tasks": [
        t("sess_2026_11_16_vouch", "insurance_or_service_quote",
          [{"type": "must_include", "value": "San Francisco"}, {"type": "must_not_include", "value": "San Jose"}], "train"),
        t("sess_2026_11_18_waas", "job_application",
          [{"type": "must_include", "value": "[PHONE-PRO]"}, {"type": "must_not_include", "value": "[PHONE-FAMILY]"}], "train"),
        t("sess_2026_11_16_luma", "event_registration", [{"type": "must_not_include", "value": "San Jose"}], "holdout"),
    ]}


CITY = {"id": "city-not-san-jose", "kind": "forbid_value", "field": "city", "forbid": ["San Jose"], "expect": "San Francisco",
        "tasks": ["insurance_or_service_quote", "event_registration"], "message": "Your sessions say San Francisco, not San Jose.",
        "provenance": ["sess_2026_11_16_vouch"]}
PHONE = {"id": "phone-pro-for-applications", "kind": "forbid_value", "field": "phone", "forbid": ["[PHONE-FAMILY]"], "expect": "[PHONE-PRO]",
         "tasks": ["job_application"], "message": "Use your professional number for applications.", "provenance": ["sess_2026_11_18_waas"]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_state = config.STATE_DIR
        config.STATE_DIR = Path(self.tmp.name)
        os.environ["PROOFLOOP_ALLOW_SESSION_UPLOAD"] = "1"
        self.logs = []

    def tearDown(self):
        config.STATE_DIR = self.old_state
        os.environ.pop("PROOFLOOP_ALLOW_SESSION_UPLOAD", None)
        self.tmp.cleanup()

    def services(self, llm, senso=None, cognee=True):
        return Services(llm=llm, cognee=FakeCognee(SESSIONS) if cognee else None, senso=senso or FakeSenso(), llm_backend="fake")

    def run_loop(self, llm, s=None, **kw):
        s = s or suite()
        llm.suite = s
        return replay_loop.run(self.services(llm, kw.pop("senso", None), kw.pop("cognee", True)), s, SESSIONS,
                               samples=kw.pop("samples", 2), log=self.logs.append, **kw)


class LoopTest(Base):
    def test_promotes_grounded_proposals_until_converged(self):
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY]},
                                       {"instructions": [], "page_rules": [CITY, PHONE]}])
        out = self.run_loop(llm)
        statuses = [e["status"] for e in out["ledger"]["entries"]]
        self.assertEqual(statuses, ["baseline", "promoted", "promoted"])
        self.assertEqual(out["active"]["version"], "v2")
        self.assertEqual(out["scores"]["train"], 1.0)
        self.assertIn("converged: every train task passes", out["stop"])
        stored = json.loads((config.STATE_DIR / "active_rules.json").read_text())
        self.assertEqual(stored["rules"]["version"], "v2")
        self.assertTrue(stored["senso"]["verified"])
        validate.check_ledger(out["ledger"])
        self.assertTrue(all(e["recall"]["mode"] == "live" for e in out["ledger"]["entries"]))

    def test_holdout_is_never_shown_to_the_mutator(self):
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}])
        self.run_loop(llm)
        prompt = llm.mutator_prompts()[0]
        failures = prompt.split("Replay failures", 1)[1].split("Past sessions recalled", 1)[0]
        self.assertNotIn("t_2026_11_16_luma", failures)

    def test_ungrounded_value_is_corrected_or_rejected(self):
        bad = dict(CITY, forbid=["Oakland"])  # not in the cited session
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [bad]}, {"instructions": [], "page_rules": [bad]}] * 3)
        out = self.run_loop(llm, patience=3)
        self.assertEqual([e["status"] for e in out["ledger"]["entries"]][1:], ["invalid_proposal"] * 3)
        self.assertIn("does not appear in cited sessions", out["ledger"]["entries"][1]["gate"]["reason"])
        self.assertIn("3 consecutive proposals", out["stop"])
        self.assertEqual(out["active"]["version"], "v0")

    def test_no_gain_is_held_and_repeats_are_refused(self):
        useless = {"id": "email-rule", "kind": "keep_unchecked", "label_all": ["sponsor"], "tasks": ["event_registration"],
                   "message": "Do not share contact info with sponsors.", "provenance": ["sess_2026_11_16_luma"]}
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [useless]}, {"instructions": [], "page_rules": [useless]},
                                       {"instructions": [], "page_rules": [useless]}, {"instructions": [], "page_rules": [useless]}])
        out = self.run_loop(llm, patience=2)
        st = [e["status"] for e in out["ledger"]["entries"]]
        self.assertEqual(st[:2], ["baseline", "held"])
        self.assertEqual(st[2], "invalid_proposal", "an already-rejected proposal is refused, not replayed")

    def test_holdout_drop_rejects(self):
        def executor(messages):
            user = messages[1]["content"]
            if "Luma" in user or "luma" in user:
                return "BAD San Jose" if "page_rules" in messages[0]["content"] or "Use San Francisco" in messages[0]["content"] else "GOOD"
            return "GOOD San Francisco [PHONE-PRO]" if "never enter" in messages[0]["content"] else "BAD San Jose [PHONE-FAMILY]"
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}] + [{"instructions": [], "page_rules": [PHONE]}] * 3,
                      executor=executor)
        out = self.run_loop(llm, patience=1)
        self.assertEqual(out["ledger"]["entries"][1]["status"], "rejected")
        self.assertIn("t_2026_11_16_luma", out["ledger"]["entries"][1]["gate"]["reason"])

    def test_senso_failure_keeps_active(self):
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}] * 4)
        out = self.run_loop(llm, senso=FakeSenso(fail=True), patience=1)
        self.assertEqual(out["ledger"]["entries"][1]["status"], "promotion_failed")
        self.assertEqual(out["active"]["version"], "v0")
        self.assertFalse((config.STATE_DIR / "active_rules.json").exists())

    def test_feedback_reaches_the_mutator(self):
        (config.STATE_DIR / "active_rules.json").write_text(json.dumps({"rules": {"version": "v1", "parent": "v0", "instructions": [], "page_rules": [CITY]}}))
        (config.STATE_DIR / "feedback.jsonl").write_text(json.dumps({"rule_id": "city-not-san-jose", "action": "rule_wrong"}) + "\n")
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}])
        self.run_loop(llm)
        self.assertIn('"city-not-san-jose": 1', llm.mutator_prompts()[0])

    def test_recall_disabled_is_recorded_and_live_upload_needs_consent(self):
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}])
        out = self.run_loop(llm, cognee=False, recall_enabled=False)
        self.assertTrue(all(e["recall"]["mode"] == "disabled" for e in out["ledger"]["entries"]))
        os.environ.pop("PROOFLOOP_ALLOW_SESSION_UPLOAD")
        with self.assertRaises(config.Blocked):
            self.run_loop(FakeLLM())

    def test_failing_tasks_own_session_is_evidence_even_when_recall_misses_it(self):
        class EmptyCognee(FakeCognee):
            def search(self, query):
                return []
        llm = FakeLLM(mutator_replies=[{"instructions": [], "page_rules": [CITY, PHONE]}])
        s = suite()
        llm.suite = s
        services = Services(llm=llm, cognee=EmptyCognee(SESSIONS), senso=FakeSenso(), llm_backend="fake")
        out = replay_loop.run(services, s, SESSIONS, samples=2, log=self.logs.append)
        self.assertEqual(out["ledger"]["entries"][1]["status"], "promoted", "citing the failing task's own session is allowed")
        ev = out["ledger"]["entries"][1]["evidence_sessions"]
        self.assertEqual(set(ev), {"sess_2026_11_16_vouch", "sess_2026_11_18_waas"}, "train sources only; the holdout source is not evidence")
        prompt = llm.mutator_prompts()[0]
        self.assertIn('"source_session_id": "sess_2026_11_16_vouch"', prompt)
        self.assertIn("source session of a failing task", prompt)

    def test_runtime_has_no_stub_fallback(self):
        for k in ("PROOFLOOP_LIVE_SERVICES", "SENSO_API_KEY", "COGNEE_API_KEY", "COGNEE_API_URL"):
            os.environ.pop(k, None)
        with self.assertRaises(config.Blocked):
            Services.live()
        with self.assertRaises(config.Blocked):
            Services().llm([{"role": "user", "content": "x"}])
        self.assertEqual(config.status()["senso"]["mode"], "off")


class UnitTest(Base):
    def test_gate_margin_and_decisions(self):
        def res(train, hold):
            r = {f"a{i}": {"score": s, "split": "train"} for i, s in enumerate(train)}
            r.update({f"h{i}": {"score": s, "split": "holdout"} for i, s in enumerate(hold)})
            return r
        base = res([0, 0, 1.0], [0.5])
        self.assertEqual(gate.decide(base, res([1, 1, 1.0], [0.5]), 3)["choice"], "promote")
        self.assertEqual(gate.decide(base, res([1 / 3, 0, 1.0], [0.5]), 3)["choice"], "hold")
        noisy = res([1 / 3, 2 / 3, 1.0], [0.5])
        self.assertGreater(gate.margin(noisy, 3, res([2 / 3, 1 / 3, 1.0], [0.5])), gate.margin(base, 3), "disagreeing samples widen the margin")
        self.assertEqual(gate.decide(base, res([1, 0, 1.0], [0.5]), 3)["choice"], "promote", "one task flipping 0 -> 1 on every sample beats noise")
        self.assertEqual(gate.decide(base, res([1, 1, 0], [0.5]), 3)["choice"], "reject")
        self.assertEqual(gate.decide(base, res([1, 1, 1.0], [0]), 3)["choice"], "reject")
        self.assertAlmostEqual(gate.margin(base, 3), 1 / 9, places=3)

    def test_rules_grounding(self):
        ok = {"version": "v1", "parent": "v0", "instructions": [{"text": "Ask before choosing a work type.", "provenance": ["sess_2026_11_16_vouch"]}],
              "page_rules": [CITY, PHONE]}
        rules_mod.validate(ok, BY_ID)
        for bad, msg in [(dict(PHONE, forbid=["[PHONE-WORK]"]), "placeholder"), (dict(CITY, provenance=["sess_2099_01_01_x"]), "outside the evidence"),
                         (dict(CITY, kind="keep_unchecked"), "schema"), (dict(CITY, id="Bad Id"), "schema")]:
            with self.assertRaises(ValueError) as cm:
                rules_mod.validate(dict(ok, page_rules=[bad]), BY_ID)
            self.assertIn(msg, str(cm.exception))

    def test_task_generation_checks_values_against_the_session(self):
        s = [BY_ID["sess_2026_11_16_vouch"], BY_ID["sess_2026_11_18_waas"]]
        llm = FakeLLM(task_replies=[
            {"task_kind": "insurance_or_service_quote", "checks": [{"type": "must_not_include", "value": "Oakland"}]},
            {"task_kind": "insurance_or_service_quote", "checks": [{"type": "must_not_include", "value": "San Jose"}]},
            {"task_kind": "job_application", "checks": [{"type": "must_include", "value": "[PHONE-PRO]"}]}])
        out, skipped = tasks_mod.generate(Services(llm=llm, llm_backend="fake"), s, log=lambda *_: None)
        self.assertEqual([t["checks"][0]["value"] for t in out["tasks"]], ["San Jose", "[PHONE-PRO]"])
        self.assertFalse(out["generated"]["reviewed"])
        self.assertEqual(skipped, [])
        self.assertEqual(len({t["split"] for t in out["tasks"]}), 2)
        validate.check_suite(out)

    def test_task_generation_rejects_sentences_and_contradictions(self):
        hrm = BY_ID["sess_2026_11_17_hrm"]
        llm = FakeLLM(task_replies=[
            {"task_kind": "verification", "checks": [{"type": "must_include", "value": "Merged is never treated as deployed; claims are verified against the live device"}]},
            {"task_kind": "verification", "checks": [{"type": "must_include", "value": "not headless alone"}, {"type": "must_not_include", "value": "headless"}]},
            {"task_kind": "verification", "checks": [{"type": "must_include", "value": "live hardware"}, {"type": "no_unsupported_claims", "value": "deployment status"}]}])
        check = tasks_mod.make_check(hrm)
        with self.assertRaises(ValueError) as a:
            check(llm.task_replies[0])
        self.assertIn("is a sentence", str(a.exception))
        with self.assertRaises(ValueError) as b:
            check(llm.task_replies[1])
        self.assertIn("contradict", str(b.exception))
        check(llm.task_replies[2])

    def test_mutator_refuses_without_evidence(self):
        with self.assertRaises(mutator.InvalidProposal):
            mutator.propose(Services(llm=FakeLLM()), rules_mod.empty(), [], [], {}, set(), "v1", BY_ID, rules_mod.task_ids())

    def test_extract_json_and_secret_redaction(self):
        self.assertEqual(extract_json('sure:\n```json\n{"a": {"b": 1}}\n```'), {"a": {"b": 1}})
        self.assertEqual(extract_json('x {"a": 1} y'), {"a": 1})
        os.environ["SENSO_API_KEY"] = "sk-test-secret-123456789"
        try:
            e = clients.ApiError(401, {"detail": "bad key sk-test-secret-123456789", "h": "Bearer abcdefghijklmnop"})
            self.assertNotIn("sk-test-secret", str(e))
            self.assertNotIn("abcdefghijklmnop", str(e))
        finally:
            os.environ.pop("SENSO_API_KEY")

    def test_prompt_render_and_sync(self):
        rs = {"version": "v2", "parent": "v1", "instructions": [], "page_rules": [CITY, PHONE]}
        info = skill_prompt.write_active(rs, {"train": 1.0, "holdout": 1.0}, {"node_id": "n9"})
        self.assertIn("never enter: San Jose", info["block"])
        self.assertIn("node n9", info["block"])
        target = Path(self.tmp.name) / "AGENTS.md"
        target.write_text("# mine\n")
        self.assertEqual(skill_prompt.sync_block(target, info["block"]), "updated")
        self.assertEqual(skill_prompt.sync_block(target, info["block"]), "unchanged")
        self.assertTrue(target.read_text().startswith("# mine\n"))
        for bad in (".env", "x.py", ".git/config"):
            with self.assertRaises(ValueError):
                skill_prompt.sync_block(Path(self.tmp.name) / bad, info["block"], create=True)


if __name__ == "__main__":
    unittest.main()
