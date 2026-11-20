"""Exercise the CI docs gate against real git histories."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci-docs-only.py"
SPEC = importlib.util.spec_from_file_location("ci_docs_only", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class DocsOnlyTests(unittest.TestCase):
    def test_allowlist(self):
        self.assertTrue(GATE.docs_only([b"docs/guide.md", b"docs/nested/a\nb.md"]))
        for paths in (
            [],
            [b"README.md"],
            [b"docs/app.js"],
            [b"docs/a.md", b"src/x.py"],
            [b"docs/a.MD"],
        ):
            with self.subTest(paths=paths):
                self.assertFalse(GATE.docs_only(paths))

    def test_real_diff_and_rename(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"GIT_CONFIG_NOSYSTEM": "1"}),
        ):
            root = Path(directory)

            def git(*args):
                return (
                    subprocess.check_output(["git", "-C", directory, *args])
                    .decode()
                    .strip()
                )

            git("init", "-q")
            git("config", "user.name", "CI test")
            git("config", "user.email", "ci@example.invalid")
            (root / "docs").mkdir()
            (root / "docs/guide.md").write_text("first\n")
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (root / "docs/guide.md").write_text("second\n")
            git("commit", "-qam", "docs")
            head = git("rev-parse", "HEAD")
            cwd = Path.cwd()
            try:
                os.chdir(root)
                self.assertTrue(GATE.docs_only(GATE.changed_paths(base, head)))
                self.assertFalse(GATE.docs_only(GATE.changed_paths(head, head)))
                git("mv", "docs/guide.md", "code.py")
                git("commit", "-qm", "rename out of docs")
                renamed = git("rev-parse", "HEAD")
                self.assertFalse(GATE.docs_only(GATE.changed_paths(head, renamed)))
                with self.assertRaises(subprocess.CalledProcessError):
                    GATE.changed_paths("f" * 40, head)
                with self.assertRaises(ValueError):
                    GATE.changed_paths("--help", head)
            finally:
                os.chdir(cwd)

    def test_non_pr_always_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with patch.dict(
                os.environ, {"EVENT_NAME": "push", "GITHUB_OUTPUT": str(output)}
            ):
                GATE.main()
            self.assertEqual(output.read_text(), "docs_only=false\n")


if __name__ == "__main__":
    unittest.main()
