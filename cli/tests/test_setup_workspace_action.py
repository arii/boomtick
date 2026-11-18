import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ACTION = yaml.safe_load(
    (
        Path(__file__).resolve().parents[2]
        / ".github/actions/setup-workspace/action.yml"
    ).read_text(encoding="utf-8")
)
STEPS = {step["name"]: step for step in ACTION["runs"]["steps"]}


class SetupWorkspaceActionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.workspace = root / "__w/consumer/consumer"
        self.workspace.mkdir(parents=True)
        self.action_root = root / "__w/_actions/arii/boomtick/ref"
        self.action_path = self.action_root / ".github/actions/setup-workspace"
        self.action_path.mkdir(parents=True)
        (self.action_root / "cli").mkdir()
        (self.action_root / "cli/pyproject.toml").touch()
        self.bin_dir = root / "bin"
        self.bin_dir.mkdir()
        self.pip_log = root / "pip.jsonl"
        pip = self.bin_dir / "pip"
        pip.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['PIP_LOG'], 'a', encoding='utf-8') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.exit(int(os.environ.get('PIP_STATUS', '0')))\n",
            encoding="utf-8",
        )
        pip.chmod(0o755)
        td = self.bin_dir / "td"
        td.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        td.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.bin_dir) + os.pathsep + os.environ["PATH"],
            "GITHUB_ACTION_PATH": str(self.action_path),
            "GITHUB_OUTPUT": str(root / "output"),
            "GITHUB_PATH": str(root / "path"),
            "GITHUB_ENV": str(root / "env"),
            "PIP_LOG": str(self.pip_log),
            "PYTHONPATH": "existing-python-path",
        }

    def run_step(self, name, **env):
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", STEPS[name]["run"]],
            cwd=self.workspace,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def resolve(self):
        result = self.run_step("Resolve Paths")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outputs = dict(
            line.split("=", 1)
            for line in Path(self.env["GITHUB_OUTPUT"]).read_text().splitlines()
        )
        self.assertIn("PYTHON_SCRIPTS_PATH", outputs)
        return outputs

    def install(self, outputs, status="0"):
        return self.run_step(
            "Install dev-tools", CLI_DIR=outputs["CLI_DIR"], PIP_STATUS=status
        )

    def calls(self):
        return [json.loads(line) for line in self.pip_log.read_text().splitlines()]

    def test_consumer_in_container_uses_pypi_not_downloaded_action_source(self):
        outputs = self.resolve()
        self.assertEqual(outputs["CLI_DIR"], "")
        result = self.install(outputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [
                [
                    "install",
                    "--upgrade",
                    "boomtick-cli>=0.14.0",
                    "--break-system-packages",
                ]
            ],
        )
        result = self.run_step(
            "Verify td on PATH", PYTHON_SCRIPTS_PATH=outputs["PYTHON_SCRIPTS_PATH"]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_consumer_requirements_install_is_fail_closed(self):
        (self.workspace / "requirements-dev.txt").write_text("boomtick-cli>=0.14.0\n")
        outputs = self.resolve()
        result = self.install(outputs, status="7")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(
            self.calls(),
            [["install", "-r", "requirements-dev.txt", "--break-system-packages"]],
        )

    def test_consumer_pypi_install_failure_is_not_hidden(self):
        result = self.install(self.resolve(), status="8")
        self.assertEqual(result.returncode, 8)
        self.assertEqual(len(self.calls()), 1)

    def test_consumer_requirements_are_used_without_editable_install(self):
        (self.workspace / "requirements-dev.txt").touch()
        result = self.install(self.resolve())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [["install", "-r", "requirements-dev.txt", "--break-system-packages"]],
        )

    def test_unrelated_consumer_cli_is_not_used(self):
        (self.workspace / "cli").mkdir()
        (self.workspace / "cli/pyproject.toml").touch()
        outputs = self.resolve()
        self.assertEqual(outputs["CLI_DIR"], "")
        self.assertEqual(self.install(outputs).returncode, 0)
        self.assertNotIn("-e", self.calls()[0])

    def test_boomtick_checkout_preserves_local_install_and_pythonpath(self):
        self.workspace = self.action_root
        (self.workspace / "requirements-dev.txt").touch()
        (self.workspace / "cli/requirements-dev.txt").touch()
        outputs = self.resolve()
        cli = str(self.workspace / "cli")
        self.assertEqual(outputs["CLI_DIR"], cli)
        result = self.install(outputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [
                ["install", "-r", "requirements-dev.txt", "--break-system-packages"],
                [
                    "install",
                    "-r",
                    cli + "/requirements-dev.txt",
                    "--break-system-packages",
                ],
                ["install", "-e", cli, "--break-system-packages"],
            ],
        )
        result = self.run_step("Export Environment Variables", CLI_DIR=cli)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"PYTHONPATH={cli}:existing-python-path",
            Path(self.env["GITHUB_ENV"]).read_text(),
        )

    def test_node_only_consumers_skip_cli_and_python_steps(self):
        for name in (
            "Resolve Paths",
            "Get pip cache directory",
            "Cache pip",
            "Cache Python .venv",
            "Install dev-tools",
            "Verify td on PATH",
            "Export Environment Variables",
            "Initialize Schemas and Contracts",
        ):
            with self.subTest(step=name):
                self.assertIn("inputs.setup-python == 'true'", STEPS[name]["if"])
        for name in (
            "Export Environment Variables",
            "Initialize Schemas and Contracts",
        ):
            with self.subTest(step=name):
                self.assertIn(
                    "steps.resolve-paths.outputs.CLI_DIR != ''", STEPS[name]["if"]
                )


if __name__ == "__main__":
    unittest.main()
