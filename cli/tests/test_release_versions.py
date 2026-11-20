"""Release collision regression checks, no API calls or publication."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-release-versions.py"
SPEC = importlib.util.spec_from_file_location("release_versions", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


class ReleaseVersionTests(unittest.TestCase):
    def test_collision_and_out_of_order_published_versions(self):
        base = {"cli": "0.20.2", "mcp": "0.11.1"}
        head = {"cli": "0.21.0", "mcp": "0.12.0"}
        errors = GUARD.validate(base, head, ["cli-v0.21.0", "mcp-v0.12.0"])
        self.assertEqual(len(errors), 4)

    def test_new_versions_must_exceed_all_tags(self):
        base = {"cli": "0.20.2", "mcp": "0.11.1"}
        head = {"cli": "0.22.0", "mcp": "0.13.0"}
        self.assertEqual(GUARD.validate(base, head, ["cli-v0.21.0", "mcp-v0.12.0"]), [])
        self.assertTrue(GUARD.validate(base, head, ["cli-v1.0.0"]))

    def test_unchanged_existing_versions_do_not_block_ordinary_prs(self):
        current = {"cli": "0.21.0", "mcp": "0.12.0"}
        self.assertEqual(GUARD.validate(current, current, ["cli-v0.21.0"]), [])

    def test_nonstable_and_malformed_versions_fail(self):
        for value in ["1.2", "v1.2.3", "1.2.3-beta.1", "01.2.3", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                GUARD.stable_version(value)

    def test_real_git_history_blocks_the_original_collision(self):
        script = SCRIPT.resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", directory, *args], text=True
                ).strip()

            git("init", "-q")
            git("config", "user.name", "CI test")
            git("config", "user.email", "ci@example.invalid")
            manifest = root / ".release-please-manifest.json"
            manifest.write_text(json.dumps({"cli": "0.20.2", "mcp": "0.11.1"}))
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            git("tag", "cli-v0.21.0")
            git("tag", "mcp-v0.12.0")
            manifest.write_text(json.dumps({"cli": "0.21.0", "mcp": "0.12.0"}))
            git("commit", "-qam", "collision")
            head = git("rev-parse", "HEAD")
            result = subprocess.run(
                ["python3", str(script), "--base", base, "--head", head],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("already exists", result.stderr)
            same = subprocess.run(
                ["python3", str(script), "--base", head, "--head", head],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(same.returncode, 0)


if __name__ == "__main__":
    unittest.main()
