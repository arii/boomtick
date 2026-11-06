"""Remote CDP driver for visual/DOM audits via browserless/Chromium.

Connects with Playwright's connect_over_cdp (never launches local
Chrome binaries). All logs go to stderr so stdout stays pure JSON.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


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


def get_cdp_endpoint() -> str:
    endpoint = os.environ.get("BROWSERLESS_ENDPOINT", "ws://127.0.0.1:3000")
    token = os.environ.get("BROWSERLESS_TOKEN", "").strip()
    if token and "token=" not in endpoint:
        sep = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{sep}token={token}"
    return endpoint


def capture_dom_and_visual_snapshot(
    target_url: str,
    output_dir: Path,
    baseline_png: Path | None = None,
    viewport: dict[str, int] | None = None,
) -> VisualDiffResult:
    """Connects to remote browserless container over CDP, extracts DOM metrics & screenshot."""
    endpoint = get_cdp_endpoint()
    vp = viewport or {"width": 1280, "height": 800}
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_png = output_dir / "candidate_viewport.png"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        _log_stderr(f"Playwright not installed: {exc}")
        return VisualDiffResult(
            reachable=False,
            url=target_url,
            mismatch_percentage=0.0,
            dom_node_count=0,
            interactive_elements=0,
            screenshot_path=None,
            error="PLAYWRIGHT_NOT_INSTALLED",
        )

    try:
        with sync_playwright() as p:
            _log_stderr(f"Connecting over CDP to {endpoint.split('?')[0]}...")
            browser = p.chromium.connect_over_cdp(endpoint, timeout=10000)
            context = browser.contexts[0] if browser.contexts else browser.new_context(viewport=vp)
            page = context.new_page()
            page.set_viewport_size(vp)
            page.goto(target_url, wait_until="networkidle", timeout=15000)

            dom_metrics = page.evaluate(
                """() => ({
                    dom_node_count: document.querySelectorAll('*').length,
                    interactive_elements: document.querySelectorAll('a, button, input, select, textarea, [role="button"]').length
                })"""
            )
            page.screenshot(path=str(candidate_png), full_page=False)
            page.close()
            browser.close()

        mismatch = _compare_png_bytes(baseline_png, candidate_png) if baseline_png and baseline_png.exists() else 0.0
        return VisualDiffResult(
            reachable=True,
            url=target_url,
            mismatch_percentage=mismatch,
            dom_node_count=int(dom_metrics.get("dom_node_count", 0)),
            interactive_elements=int(dom_metrics.get("interactive_elements", 0)),
            screenshot_path=str(candidate_png),
        )
    except Exception as exc:
        _log_stderr(f"CDP snapshot failed: {exc}")
        return VisualDiffResult(
            reachable=False,
            url=target_url,
            mismatch_percentage=0.0,
            dom_node_count=0,
            interactive_elements=0,
            screenshot_path=None,
            error=f"BROWSERLESS_UNREACHABLE: {exc}",
        )


def _compare_png_bytes(baseline: Path, candidate: Path) -> float:
    """Lightweight pixel/byte comparison fallback if PIL/pixelmatch is absent."""
    b_bytes = baseline.read_bytes()
    c_bytes = candidate.read_bytes()
    if b_bytes == c_bytes:
        return 0.0
    try:
        from PIL import Image, ImageChops
        with Image.open(baseline).convert("RGB") as img1, Image.open(candidate).convert("RGB") as img2:
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)
            diff = ImageChops.difference(img1, img2)
            non_zero = sum(1 for px in diff.getdata() if px != (0, 0, 0))
            total = img1.size[0] * img1.size[1]
            return round((non_zero / max(total, 1)) * 100.0, 3)
    except Exception:
        return 100.0
