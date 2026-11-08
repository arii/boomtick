# pylint: disable=missing-docstring
"""Packaging policy: transitive telemetry deps must float (no == pins).

Regression guard: opentelemetry-api/sdk were ==-pinned (for an old semgrep
crash) while the OTLP exporter floated, so fresh installs resolved a skewed
set (exporter 1.45.x vs sdk 1.37.0) whose ImportError silently disabled the
RAG embedding backend (index_available=false, 0 hits). Telemetry arrives
transitively via chromadb/semgrep; pins here can only reintroduce skew.
"""
import os
import re
import tomllib

PYPROJECT = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")


def _dependencies():
    with open(PYPROJECT, "rb") as handle:
        return tomllib.load(handle)["project"]["dependencies"]


def test_no_exact_pins_on_opentelemetry():
    pinned = [
        dep
        for dep in _dependencies()
        if re.match(r"opentelemetry-.*==", dep)
    ]
    assert not pinned, (
        "opentelemetry packages must float, found exact pins: "
        + ", ".join(pinned)
    )


def test_no_semgrep_runtime_dependency():
    # semgrep's own opentelemetry ~=1.37 pins anchored the resolver while
    # chromadb's OTLP exporter floated, skewing fresh installs into a
    # broken sdk/exporter mix that silently disabled RAG. Nothing in
    # dev_tools or CI invokes the semgrep package; install it separately
    # where the scanner is actually needed.
    names = [re.split(r"[<>=!~\s\[]", dep, maxsplit=1)[0] for dep in _dependencies()]
    assert "semgrep" not in names, "semgrep must not anchor runtime OTEL versions"
