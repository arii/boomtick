"""Keep import-time syntax within the advertised runtime range."""

import ast
import importlib
from pathlib import Path
import sys

import pytest

CLI_ROOT = Path(__file__).resolve().parents[1]


def test_library_syntax_is_python38_compatible():
    for source in (CLI_ROOT / "dev_tools").rglob("*.py"):
        ast.parse(
            source.read_text(encoding="utf-8"),
            filename=str(source),
            feature_version=(3, 8),
        )


@pytest.mark.parametrize(
    "module",
    [
        "config",
        "review_read_pass",
        "orchestration.workflows",
        "orchestration.ci_ops",
        "orchestration.review",
        "handlers.mcp_installer",
        "utils",
        "services.browser_cdp",
        "cli",
    ],
)
def test_runtime_modules_import_without_eager_modern_annotations(module):
    # Also run this focused test on real 3.8/3.9 interpreters, not only CI's
    # development interpreter. AST grammar checks alone miss evaluated hints.
    assert sys.version_info >= (3, 8)
    importlib.import_module("dev_tools.cli")
    importlib.import_module("dev_tools.orchestrator")
    assert importlib.import_module("dev_tools." + module) is not None
