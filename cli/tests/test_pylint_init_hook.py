"""Pylint must execute the configured import hook on supported dev Python."""

import subprocess
import sys
from pathlib import Path


def test_pylint_init_hook_loads_without_scope_error(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "probe.py"
    source.write_text("value = 1\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            "--rcfile=" + str(root / ".pylintrc"),
            "--disable=all",
            "--enable=syntax-error",
            str(source),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NameError" not in result.stderr
