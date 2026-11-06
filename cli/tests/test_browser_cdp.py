"""Unit tests for dev_tools.services.browser_cdp (remote CDP driver).

All browser interaction is faked via sys.modules; no live browserless
container is needed. Run: python3 scripts/run-python-tool.py pytest cli/tests/test_browser_cdp.py
"""
import sys
import types

import pytest

from dev_tools.services.browser_cdp import (
    VisualDiffResult,
    _compare_png_bytes,
    capture_dom_and_visual_snapshot,
    get_cdp_endpoint,
)


class _FakePage:
    def set_viewport_size(self, viewport):
        pass

    def goto(self, url, wait_until=None, timeout=None):
        pass

    def evaluate(self, _js):
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

    def new_context(self, viewport=None):
        return _FakeContext()

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, exc=None):
        self._exc = exc

    def connect_over_cdp(self, _endpoint, timeout=None):
        if self._exc is not None:
            raise self._exc
        return _FakeBrowser()


class _FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _install_fake_playwright(monkeypatch, exc=None):
    def sync_playwright():
        return _FakePlaywright(_FakeChromium(exc))

    pkg = types.ModuleType("playwright")
    sub = types.ModuleType("playwright.sync_api")
    sub.sync_playwright = sync_playwright
    pkg.sync_api = sub
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sub)


def test_endpoint_default(monkeypatch):
    monkeypatch.delenv("BROWSERLESS_ENDPOINT", raising=False)
    monkeypatch.delenv("BROWSERLESS_TOKEN", raising=False)
    assert get_cdp_endpoint() == "ws://127.0.0.1:3000"


def test_endpoint_appends_token(monkeypatch):
    monkeypatch.setenv("BROWSERLESS_ENDPOINT", "ws://browserless:3000")
    monkeypatch.setenv("BROWSERLESS_TOKEN", "secret")
    assert get_cdp_endpoint() == "ws://browserless:3000?token=secret"


def test_endpoint_keeps_existing_query(monkeypatch):
    monkeypatch.setenv("BROWSERLESS_ENDPOINT", "ws://h:3000?a=b")
    monkeypatch.setenv("BROWSERLESS_TOKEN", "secret")
    assert get_cdp_endpoint() == "ws://h:3000?a=b&token=secret"


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
    _install_fake_playwright(monkeypatch)
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert isinstance(result, VisualDiffResult)
    assert result.reachable is True
    assert result.dom_node_count == 42
    assert result.interactive_elements == 7
    assert result.mismatch_percentage == 0.0
    assert result.screenshot_path is not None
    # stdout stays pure JSON: all telemetry goes to stderr
    assert capsys.readouterr().out == ""


def test_capture_unreachable_browser(tmp_path, monkeypatch):
    _install_fake_playwright(monkeypatch, exc=RuntimeError("refused"))
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert result.reachable is False
    assert result.screenshot_path is None
    assert result.error.startswith("BROWSERLESS_UNREACHABLE")


def test_capture_without_playwright(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    result = capture_dom_and_visual_snapshot(
        "http://example.test/", tmp_path)
    assert result.reachable is False
    assert result.error == "PLAYWRIGHT_NOT_INSTALLED"
