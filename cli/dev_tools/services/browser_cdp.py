"""Remote CDP driver for visual/DOM audits via the shared headed browser.

Flow: create a Selenium Grid session, connect over that session's CDP
endpoint with Playwright's connect_over_cdp (never launches local
Chrome binaries), capture, then DELETE the session (a leaked session
holds the single grid slot and wedges every later run). All logs go
to stderr so stdout stays pure JSON.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

DEFAULT_GRID_BASE = "http://browser:4444"
UNREACHABLE = "BROWSER_UNREACHABLE"


@dataclass
class VisualDiffResult:
    reachable: bool
    url: str
    mismatch_percentage: float
    dom_node_count: int
    interactive_elements: int
    screenshot_path: str | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _log_stderr(msg: str) -> None:
    """Guarantees stdout remains 100% pure JSON when --json is passed."""
    print(f"[browser_cdp] {msg}", file=sys.stderr)


def get_grid_base() -> str:
    """Selenium Grid base URL (agent override via BROWSER_ENDPOINT)."""
    return os.environ.get("BROWSER_ENDPOINT", DEFAULT_GRID_BASE).rstrip("/")


def _cdp_ws_url(grid_base: str, session_id: str) -> str:
    ws_base = grid_base.rstrip("/").replace(
        "https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/session/{session_id}/se/cdp"


# Agent profile on the shared host dir: logins and localStorage
# survive session and container restarts. ChromeDriver yields to a
# user-supplied --user-data-dir (its temp dir would otherwise win).
# WebMCP testing flag lets agents consume document.modelContext tools
# where sites offer them (verified live: undefined without it).
AGENT_PROFILE_ARGS = [
    "--user-data-dir=/data/shared-browser/agent",
    "--enable-features=WebMCP",
]


def _session_capabilities() -> dict:
    """W3C alwaysMatch block for a headed agent session.

    The boomtick:agentSession marker lets the shared-autonomy viewer
    tell agent sessions apart from human/viewer ones (attaching to a
    viewer session mirrors it recursively). Custom vendor caps
    round-trip through Grid /status slot capabilities.
    """
    return {"browserName": "chrome",
            "boomtick:agentSession": True,
            "goog:chromeOptions": {"args": list(AGENT_PROFILE_ARGS)}}


def _create_grid_session(grid_base: str, timeout: int = 60) -> str:
    """Start a headed Chromium session; returns its sessionId."""
    body = json.dumps({"capabilities": {"alwaysMatch":
                                        _session_capabilities()}}).encode()
    req = urllib.request.Request(grid_base + "/session", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)["value"]["sessionId"]


def _delete_grid_session(grid_base: str, session_id: str,
                         timeout: int = 15) -> None:
    """Best-effort session teardown; never raises."""
    try:
        req = urllib.request.Request(
            f"{grid_base}/session/{session_id}", method="DELETE")
        urllib.request.urlopen(req, timeout=timeout)
    except Exception as exc:
        _log_stderr(f"session teardown best-effort failed: {exc}")


def _compare_png_bytes(baseline_png: Path, candidate_png: Path) -> float:
    """0.0 for identical files; mismatch percentage otherwise.

    Uses Pillow when available; without it, any difference is 100.0.
    Reads files directly (no browser needed) so it stays unit-testable.
    """
    baseline = baseline_png.read_bytes()
    candidate = candidate_png.read_bytes()
    if baseline == candidate:
        return 0.0
    try:
        from PIL import Image, ImageChops
        import io
        with Image.open(io.BytesIO(baseline)).convert("RGB") as img1, \
                Image.open(io.BytesIO(candidate)).convert("RGB") as img2:
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)
            diff = ImageChops.difference(img1, img2)
            non_zero = sum(1 for px in diff.getdata() if px != (0, 0, 0))
            return round(
                non_zero / max(img1.size[0] * img1.size[1], 1) * 100.0, 3)
    except Exception:
        return 100.0


def _unreachable(url: str, reason: str) -> VisualDiffResult:
    _log_stderr(f"snapshot failed: {reason}")
    return VisualDiffResult(
        reachable=False,
        url=url,
        mismatch_percentage=0.0,
        dom_node_count=0,
        interactive_elements=0,
        screenshot_path=None,
        error=f"{UNREACHABLE}: {reason}",
    )


def capture_dom_and_visual_snapshot(
    target_url: str,
    output_dir: Path,
    baseline_png: Path | None = None,
    viewport: dict[str, int] | None = None,
) -> VisualDiffResult:
    """Capture DOM metrics + viewport screenshot via a grid session."""
    grid_base = get_grid_base()
    vp = viewport or {"width": 1280, "height": 800}
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_png = output_dir / "candidate_viewport.png"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _unreachable(target_url,
                            f"PLAYWRIGHT_NOT_INSTALLED ({exc})")

    try:
        session_id = _create_grid_session(grid_base)
    except Exception as exc:
        return _unreachable(target_url, str(exc))

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                _cdp_ws_url(grid_base, session_id), timeout=15000)
            context = (browser.contexts[0] if browser.contexts
                       else browser.new_context(viewport=vp))
            page = context.new_page()
            try:
                page.set_viewport_size(vp)
                page.goto(target_url, wait_until="domcontentloaded",
                          timeout=20000)
                # Single JS string literal: JS has no Python-style
                # implicit literal concatenation ('a,' 'b' is a
                # SyntaxError in the page).
                dom = page.evaluate(
                    "() => ({dom_node_count: "
                    "document.querySelectorAll('*').length, "
                    "interactive_elements: document.querySelectorAll("
                    "'a, button, input, select, textarea, "
                    "[role=\"button\"]').length})")
                page.screenshot(path=str(candidate_png), full_page=False)
            finally:
                page.close()
                browser.close()
    except Exception as exc:
        return _unreachable(target_url, str(exc))
    finally:
        _delete_grid_session(grid_base, session_id)

    mismatch = (_compare_png_bytes(baseline_png, candidate_png)
                if baseline_png and baseline_png.exists() else 0.0)
    return VisualDiffResult(
        reachable=True,
        url=target_url,
        mismatch_percentage=mismatch,
        dom_node_count=int(dom.get("dom_node_count", 0)),
        interactive_elements=int(dom.get("interactive_elements", 0)),
        screenshot_path=str(candidate_png),
    )


CURSOR_INJECTION_JS = (
    "(() => { if (window.__agentCursorInstalled) return;"
    " window.__agentCursorInstalled = true;"
    " const c = document.createElement('div');"
    " c.id = '__agent_cdp_cursor';"
    " c.style.cssText = 'position:fixed;top:0;left:0;width:18px;height:18px;'"
    " + 'border-radius:50%;background:rgba(255,59,48,0.85);border:2px solid #fff;'"
    " + 'box-shadow:0 0 8px rgba(0,0,0,0.6);pointer-events:none;z-index:2147483647;'"
    " + 'transform:translate(-50%,-50%);transition:top 0.08s,left 0.08s;';"
    " document.documentElement.appendChild(c);"
    " window.__moveAgentCursor = (x, y) => {"
    " const el = document.getElementById('__agent_cdp_cursor');"
    " if (el) { el.style.left = x + 'px'; el.style.top = y + 'px'; } }; })();"
)


def inject_cursor(page) -> None:
    """Inject the visible cobrowsing cursor (idempotent per page)."""
    page.evaluate(CURSOR_INJECTION_JS)


def resolve_selector_center(page, selector: str) -> dict:
    """Viewport center of the first element matching selector."""
    point = page.evaluate(
        "(() => { const el = document.querySelector("
        + json.dumps(selector)
        + "); if (!el) return null;"
        + " el.scrollIntoView({block: 'center', inline: 'center'});"
        + " const r = el.getBoundingClientRect();"
        + " return {x: Math.round(r.left + r.width / 2),"
        + " y: Math.round(r.top + r.height / 2)}; })()"
    )
    if not point:
        raise ValueError(f"Selector not found: {selector}")
    return {"x": int(point["x"]), "y": int(point["y"])}


def click(page, selector: str | None = None,
          x: int | None = None, y: int | None = None) -> dict:
    """Move the visual cursor and dispatch a left click."""
    inject_cursor(page)
    if selector is not None:
        center = resolve_selector_center(page, selector)
        x, y = center["x"], center["y"]
    if x is None or y is None:
        raise ValueError("Must provide selector or (x, y) coordinates")
    page.evaluate(f"window.__moveAgentCursor({int(x)}, {int(y)})")
    page.mouse.move(int(x), int(y))
    page.mouse.click(int(x), int(y), button="left")
    return {"x": int(x), "y": int(y)}


def type_text(page, text: str, selector: str | None = None,
              clear_first: bool = True, press_enter: bool = False) -> dict:
    """Click an optional selector, clear it, and type via key events."""
    if selector is not None:
        click(page, selector=selector)
        if clear_first:
            page.evaluate(
                "(() => { const el = document.querySelector("
                + json.dumps(selector)
                + "); if (el && 'value' in el) { el.value = '';"
                + " el.dispatchEvent(new Event('input', {bubbles: true}));"
                + " } })()"
            )
    page.keyboard.type(text)
    if press_enter:
        page.keyboard.press("Enter")
    return {"typed": len(text), "selector": selector}
