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
            for event in ("push", "workflow_dispatch"):
                with (
                    self.subTest(event=event),
                    patch.dict(
                        os.environ, {"EVENT_NAME": event, "GITHUB_OUTPUT": str(output)}
                    ),
                ):
                    output.write_text("")
                    GATE.main()
                    self.assertEqual(output.read_text(), "docs_only=false\n")

    def test_pr_classification_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with patch.dict(
                os.environ,
                {
                    "EVENT_NAME": "pull_request",
                    "GITHUB_OUTPUT": str(output),
                    "BASE_SHA": "a" * 40,
                    "HEAD_SHA": "b" * 40,
                },
            ):
                for paths, expected in (
                    ([b"docs/a.md"], "true"),
                    ([b"docs/a.md", b"Dockerfile"], "false"),
                    ([b".github/workflows/smoke-test-impact-analysis.yml"], "false"),
                    ([], "false"),
                ):
                    with (
                        self.subTest(paths=paths),
                        patch.object(GATE, "changed_paths", return_value=paths),
                    ):
                        output.write_text("")
                        GATE.main()
                        self.assertEqual(output.read_text(), f"docs_only={expected}\n")
                with patch.object(GATE, "changed_paths", side_effect=ValueError):
                    output.write_text("")
                    with self.assertRaises(ValueError):
                        GATE.main()
                    self.assertEqual(output.read_text(), "")


class SmokeDocsGateTests(unittest.TestCase):
    def test_smoke_keeps_job_and_gates_every_heavy_step(self):
        workflow = (
            SCRIPT.parent.parent / ".github/workflows/smoke-test-impact-analysis.yml"
        ).read_text()
        self.assertIn("  smoke-test:\n    timeout-minutes: 30", workflow)
        self.assertIn("  push:\n    branches: [ main ]", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertNotIn("paths-ignore:", workflow)
        self.assertIn("run: python3 scripts/ci-docs-only.py", workflow)
        self.assertIn("BASE_SHA: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertIn("HEAD_SHA: ${{ github.event.pull_request.head.sha }}", workflow)
        steps = workflow.split("      - ")[1:]
        self.assertEqual(len(steps), 9)
        self.assertEqual(
            [step.splitlines()[0] for step in steps[:3]],
            [
                "uses: actions/checkout@v7",
                "name: Test the docs gate",
                "name: Classify changed paths",
            ],
        )
        for step in steps[3:]:
            with self.subTest(step=step.splitlines()[0]):
                self.assertIn("if: steps.diff.outputs.docs_only != 'true'", step)
                self.assertNotIn("continue-on-error", step)
        self.assertIn("&& steps.check-image.outputs.exists != 'true'", workflow)
        self.assertIn('gemini_api_key: "MOCK_KEY"', workflow)


if __name__ == "__main__":
    unittest.main()
