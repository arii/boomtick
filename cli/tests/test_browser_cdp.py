"""Unit tests for dev_tools.services.browser_cdp (grid-session CDP driver).

No live browser needed: the grid session helpers and Playwright are
faked via monkeypatch. Run: python3 scripts/run-python-tool.py pytest
cli/tests/test_browser_cdp.py
"""
import re
import sys
import types

import pytest

from dev_tools.services import browser_cdp
from dev_tools.services.browser_cdp import (
    VisualDiffResult,
    _cdp_ws_url,
    _compare_png_bytes,
    _session_capabilities,
    capture_dom_and_visual_snapshot,
    get_grid_base,
)


class _FakePage:
    last_evaluate = None

    def __init__(self):
        self.viewport = None

    def set_viewport_size(self, viewport):
        self.viewport = viewport

    def goto(self, url, wait_until=None, timeout=None):
        pass

    def evaluate(self, js):
        _FakePage.last_evaluate = js
        return {"dom_node_count": 42, "interactive_elements": 7}

    def screenshot(self, path=None, full_page=False):
        from pathlib import Path
        Path(path).write_bytes(b"fake-png-bytes")

    def close(self):
        pass


class _FakeContext:
    def new_page(self):
        return _FakePage()


class _FakeBrowser:
    contexts: list = []

    def __init__(self, exc=None):
        self._exc = exc
        self.connected_to = None

    def new_context(self, viewport=None):
        return _FakeContext()

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, fake_browser):
        self._browser = fake_browser
        self.seen_endpoint = None

    def connect_over_cdp(self, endpoint, timeout=None):
        self.seen_endpoint = endpoint
        if self._browser._exc is not None:
            raise self._browser._exc
        self._browser.connected_to = endpoint
        return self._browser


class _FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install_fake_playwright(monkeypatch, exc=None):
    fake_browser = _FakeBrowser(exc)

    def sync_playwright():
        return _FakePlaywright(_FakeChromium(fake_browser))

    pkg = types.ModuleType("playwright")
    sub = types.ModuleType("playwright.sync_api")
    sub.sync_playwright = sync_playwright
    pkg.sync_api = sub
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sub)
    return fake_browser


def _install_fake_grid(monkeypatch, deleted, exc=None):
    def fake_create(grid_base, timeout=60):
        if exc is not None:
            raise exc
        assert grid_base.startswith("http")
        return "fake-session-id"

    def fake_delete(grid_base, session_id, timeout=15):
        deleted.append(session_id)

    monkeypatch.setattr(browser_cdp, "_create_grid_session", fake_create)
    monkeypatch.setattr(browser_cdp, "_delete_grid_session", fake_delete)


def test_grid_base_default(monkeypatch):
    monkeypatch.delenv("BROWSER_ENDPOINT", raising=False)
    assert get_grid_base() == "http://browser:4444"


def test_grid_base_env_override(monkeypatch):
    monkeypatch.setenv("BROWSER_ENDPOINT", "http://h:4444/")
    assert get_grid_base() == "http://h:4444"


def test_cdp_ws_url_scheme_swap():
    assert _cdp_ws_url("http://browser:4444", "abc") == \
        "ws://browser:4444/session/abc/se/cdp"
    assert _cdp_ws_url("https://h:4444/", "abc") == \
        "wss://h:4444/session/abc/se/cdp"


def test_compare_identical_bytes(tmp_path):
    baseline = tmp_path / "base.png"
    baseline.write_bytes(b"same-bytes")
    assert _compare_png_bytes(baseline, baseline) == 0.0


def test_compare_different_bytes_nonzero(tmp_path):
    baseline = tmp_path / "base.png"
    candidate = tmp_path / "cand.png"
    baseline.write_bytes(b"aaa")
    candidate.write_bytes(b"bbb")
    assert _compare_png_bytes(baseline, candidate) != 0.0


def test_capture_reachable_snapshot(tmp_path, monkeypatch, capsys):
    deleted = []
    _install_fake_grid(monkeypatch, deleted)
    fake_browser = _install_fake_playwright(monkeypatch)
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert isinstance(result, VisualDiffResult)
    assert result.reachable is True
    assert result.dom_node_count == 42
    assert result.interactive_elements == 7
    assert result.mismatch_percentage == 0.0
    assert result.screenshot_path is not None
    assert fake_browser.connected_to == \
        "ws://browser:4444/session/fake-session-id/se/cdp"
    assert deleted == ["fake-session-id"]
    # stdout stays pure JSON: all telemetry goes to stderr
    assert capsys.readouterr().out == ""


def test_capture_deletes_session_on_cdp_failure(tmp_path, monkeypatch):
    deleted = []
    _install_fake_grid(monkeypatch, deleted)
    _install_fake_playwright(monkeypatch, exc=RuntimeError("refused"))
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert result.reachable is False
    assert result.screenshot_path is None
    assert result.error.startswith("BROWSER_UNREACHABLE")
    # the grid slot must not leak even when CDP fails
    assert deleted == ["fake-session-id"]


def test_capture_unreachable_grid(tmp_path, monkeypatch):
    deleted = []
    _install_fake_grid(monkeypatch, deleted,
                       exc=RuntimeError("connection refused"))
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert result.reachable is False
    assert result.error.startswith("BROWSER_UNREACHABLE")
    assert deleted == []


def test_session_capabilities_pin_profile_and_webmcp():
    caps = _session_capabilities()
    args = caps["goog:chromeOptions"]["args"]
    assert "--user-data-dir=/data/shared-browser/agent" in args
    assert "--enable-features=WebMCP" in args


def test_evaluate_js_has_no_adjacent_string_literals(tmp_path, monkeypatch):
    """Regression: JS has no Python-style implicit literal
    concatenation, so two adjacent string literals ('a,' 'b') are a
    page-side SyntaxError. The selector must ship as one literal."""
    deleted = []
    _install_fake_grid(monkeypatch, deleted)
    _install_fake_playwright(monkeypatch)
    capture_dom_and_visual_snapshot("http://example.test/", tmp_path)
    expr = _FakePage.last_evaluate
    assert "'a, button, input, select, textarea, " \
        '[role="button"]\'' in expr
    assert re.search(r"'[^'\n]*'\s*'", expr) is None


def test_capture_without_playwright(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert result.reachable is False
    assert result.error.startswith("BROWSER_UNREACHABLE")
    assert "PLAYWRIGHT_NOT_INSTALLED" in result.error
