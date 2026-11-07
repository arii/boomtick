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
    assert "--disable-dev-shm-usage" in args


def test_session_capabilities_marks_agent_session():
    # The shared-autonomy viewer attaches only to marked agent
    # sessions; unmarked viewer/human sessions get their own.
    assert _session_capabilities()["boomtick:agentSession"] is True


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


class _FakeMouse:
    def __init__(self):
        self.calls = []

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))


class _FakeKeyboard:
    def __init__(self):
        self.typed = []
        self.pressed = []

    def type(self, text):
        self.typed.append(text)

    def press(self, key):
        self.pressed.append(key)


class _InputFakePage:
    """Duck-typed Playwright page for input-dispatch tests."""

    _DEFAULT_CENTER = {"x": 10, "y": 20}

    def __init__(self, center=_DEFAULT_CENTER):
        self.evaluated = []
        self.mouse = _FakeMouse()
        self.keyboard = _FakeKeyboard()
        self._center = dict(center) if center is not None else None

    def evaluate(self, js):
        self.evaluated.append(js)
        if "getBoundingClientRect" in js:
            return self._center
        return None


def test_inject_cursor_installs_overlay_once():
    page = _InputFakePage()
    browser_cdp.inject_cursor(page)
    browser_cdp.inject_cursor(page)
    installs = [js for js in page.evaluated if "__agent_cdp_cursor" in js]
    assert len(installs) == 2
    assert "__agentCursorInstalled" in installs[0]


def test_click_by_selector_moves_cursor_and_clicks():
    page = _InputFakePage()
    point = browser_cdp.click(page, selector="button.submit")
    assert point == {"x": 10, "y": 20}
    assert ("move", 10, 20) in page.mouse.calls
    assert ("click", 10, 20, "left") in page.mouse.calls
    assert any("__moveAgentCursor(10, 20)" in js for js in page.evaluated)


def test_click_by_coordinates_skips_lookup():
    page = _InputFakePage()
    point = browser_cdp.click(page, x=5, y=6)
    assert point == {"x": 5, "y": 6}
    assert not any("getBoundingClientRect" in js for js in page.evaluated)


def test_click_missing_selector_raises():
    page = _InputFakePage(center=None)
    with pytest.raises(ValueError, match="Selector not found"):
        browser_cdp.click(page, selector=".nope")


def test_click_requires_target():
    page = _InputFakePage()
    with pytest.raises(ValueError, match="selector or"):
        browser_cdp.click(page)


def test_type_text_clears_types_and_enters():
    page = _InputFakePage()
    result = browser_cdp.type_text(page, "hi", selector="input", press_enter=True)
    assert result == {"typed": 2, "selector": "input"}
    assert page.keyboard.typed == ["hi"]
    assert page.keyboard.pressed == ["Enter"]
    assert any("dispatchEvent" in js for js in page.evaluated)


def test_cursor_js_has_no_adjacent_string_literals():
    assert re.search(r"'[^'\n]*'\s*'", browser_cdp.CURSOR_INJECTION_JS) is None
