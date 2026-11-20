"""Offline tests for the auto-updating agent prompt. No network, no servers."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
import config
import replay_loop
import server
import skill_prompt
import validate


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"PROOFLOOP_FORCE_STUB": "1"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        state = patch.object(config, "STATE_DIR", self.root / "state")
        state.start()
        self.addCleanup(state.stop)
        for target in ("urllib.request.urlopen", "socket.socket.connect", "socket.getaddrinfo", "server.HTTPServer"):
            guard = patch(target, side_effect=AssertionError("offline test attempted external execution"))
            guard.start()
            self.addCleanup(guard.stop)
        self.tasks = validate.load_suite()["tasks"]
        self.full = {"version": "v1.2", "steps": list(agent.KNOWN_STEPS)}
        self.base = {"version": "v0", "steps": [agent.BASE_STEP]}

    def run_loop(self, *args):
        argv = ["replay_loop.py", *args]
        out = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            code = replay_loop.main()
        return code, out.getvalue()

    # ---- rendering
    def test_every_step_has_a_prompt_rule(self):
        self.assertEqual(set(agent.PROMPT_RULES), set(agent.KNOWN_STEPS))

    def test_render_has_rules_and_only_passing_constraints(self):
        rep = agent.replay(self.full, self.tasks)
        block = skill_prompt.render(self.full, self.tasks, rep)
        for step in self.full["steps"]:
            self.assertIn(agent.PROMPT_RULES[step], block)
        self.assertIn(self.tasks[0]["expected_constraint"], block)
        self.assertIn("skill v1.2", block)
        self.assertIn("6/6", block)
        weak = agent.replay(self.base, self.tasks)
        weak_block = skill_prompt.render(self.base, self.tasks, weak)
        self.assertNotIn(self.tasks[0]["expected_constraint"], weak_block)  # t1 fails under v0
        self.assertNotIn(agent.PROMPT_RULES["ground_in_related_tabs"], weak_block)

    def test_render_is_deterministic(self):
        rep = agent.replay(self.full, self.tasks)
        self.assertEqual(skill_prompt.render(self.full, self.tasks, rep), skill_prompt.render(self.full, self.tasks, rep))

    # ---- syncing
    def test_sync_create_update_and_idempotent(self):
        target = self.root / "AGENTS.md"
        block = skill_prompt.render(self.full, self.tasks, agent.replay(self.full, self.tasks))
        with self.assertRaises(FileNotFoundError):
            skill_prompt.sync_block(target, block)
        self.assertEqual(skill_prompt.sync_block(target, block, create=True), "created")
        self.assertEqual(skill_prompt.sync_block(target, block), "unchanged")
        newer = block.replace("skill v1.2", "skill v1.9")
        self.assertEqual(skill_prompt.sync_block(target, newer), "updated")
        text = target.read_text()
        self.assertEqual(text.count(skill_prompt.BEGIN), 1)
        self.assertIn("skill v1.9", text)
        self.assertNotIn("skill v1.2", text)

    def test_sync_preserves_everything_outside_the_markers(self):
        target = self.root / "GEMINI.md"
        target.write_text("# My rules\nkeep me\n")
        block = skill_prompt.render(self.full, self.tasks, agent.replay(self.full, self.tasks))
        skill_prompt.sync_block(target, block)
        target.write_text(target.read_text() + "\n## After\ntrailing text\n")
        skill_prompt.sync_block(target, block.replace("skill v1.2", "skill v1.3"))
        text = target.read_text()
        self.assertTrue(text.startswith("# My rules\nkeep me\n"))
        self.assertIn("## After\ntrailing text", text)
        self.assertIn("skill v1.3", text)

    def test_sync_refuses_unsafe_targets_and_broken_markers(self):
        block = "x\n"
        for bad in (self.root / ".env", self.root / ".env.local", self.root / ".git" / "config.md",
                    self.root / "state.json", self.root / "key.pem"):
            bad.parent.mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ValueError, msg=str(bad)):
                skill_prompt.sync_block(bad, block, create=True)
            self.assertFalse(bad.exists())
        dangling = self.root / "broken.md"
        dangling.write_text(f"before\n{skill_prompt.BEGIN}\nno end marker\n")
        with self.assertRaises(ValueError):
            skill_prompt.sync_block(dangling, block)
        self.assertIn("no end marker", dangling.read_text())  # untouched

    # ---- end to end through the replay loop
    def test_loop_writes_prompt_and_syncs_target(self):
        target = self.root / "agent-instructions.md"
        code, out = self.run_loop("--reset", "--bad-demo", "--sync-prompt", str(target), "--create-target")
        self.assertEqual(code, 0)
        active = (config.STATE_DIR / "active_prompt.md").read_text()
        self.assertEqual(target.read_text(), active)
        self.assertIn("skill v1.2", active)  # bad v1.3 was rolled back, prompt stays on v1.2
        self.assertNotIn("v1.3", active)
        for step in agent.KNOWN_STEPS:
            self.assertIn(agent.PROMPT_RULES[step], active)
        self.assertIn("Prompt synced", out)

    def test_rollback_leaves_previous_prompt_in_place(self):
        target = self.root / "agent-instructions.md"
        self.run_loop("--reset", "--sync-prompt", str(target), "--create-target")
        before = target.read_text()
        self.run_loop("--bad-demo", "--sync-prompt", str(target))  # starts from v1.2, bad cycle rejected
        self.assertEqual(target.read_text(), before)

    def test_unpromoted_v0_never_overwrites_an_existing_prompt(self):
        target = self.root / "agent-instructions.md"
        target.write_text("old content\n")
        code, out = self.run_loop("--reset", "--max-cycles", "0", "--sync-prompt", str(target))
        self.assertEqual(code, 0)
        self.assertEqual(target.read_text(), "old content\n")
        self.assertIn("left unchanged", out)

    def test_sync_failure_is_reported_not_raised(self):
        code, out = self.run_loop("--reset", "--sync-prompt", str(self.root / ".env"), "--create-target")
        self.assertEqual(code, 0)
        self.assertIn("Prompt sync FAILED", out)
        self.assertFalse((self.root / ".env").exists())

    # ---- backend
    def test_server_prompt_payload(self):
        self.assertIsNone(server.prompt_payload())
        self.assertIsNone(server.augment()["prompt"])
        self.run_loop("--reset")
        pp = server.prompt_payload()
        self.assertIn("ProofLoop rules for agents", pp["text"])
        self.assertEqual(len(pp["sha256"]), 64)
        self.assertEqual(pp["version"], "v1.2")
        self.assertEqual(server.augment()["prompt"]["sha256"], pp["sha256"])
        self.assertNotIn("text", server.augment()["prompt"])  # chip payload stays small


if __name__ == "__main__":
    unittest.main()
