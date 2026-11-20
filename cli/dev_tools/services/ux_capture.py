"""Explicit served-revision capture, without builds, checkout or publication."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dev_tools.services.browser_cdp import capture_dom_and_visual_snapshot


def _base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or any(ord(char) < 33 for char in value)
    ):
        raise ValueError("URLs must be HTTP(S), without credentials, query or fragment")
    return value.rstrip("/")


def _route(value: str) -> str:
    parsed = urlsplit(value)
    path = unquote(parsed.path)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.netloc
        or parsed.scheme
        or parsed.fragment
        or "\\" in unquote(value)
        or any(part in {".", ".."} for part in path.split("/"))
        or any(ord(char) < 32 for char in unquote(value))
    ):
        raise ValueError(
            "Routes must be root-relative paths without traversal or fragments"
        )
    return value


def _artifacts_exist(snapshot) -> bool:
    return bool(
        snapshot.reachable
        and snapshot.screenshot_path
        and snapshot.dom_path
        and Path(snapshot.screenshot_path).is_file()
        and Path(snapshot.dom_path).is_file()
    )


def capture_revision_pair(
    base_url,
    head_url,
    base_ref,
    head_ref,
    routes,
    output_dir: Path,
    *,
    ready_selector=None,
):
    """Capture each route on each explicit URL and write a local manifest.

    A complete capture means files exist, not that the labels match the served
    revisions, that routes cover the diff, or that visual intent is correct.
    """
    base_url, head_url = _base_url(base_url), _base_url(head_url)
    routes = list(dict.fromkeys(_route(route) for route in routes))
    if not routes or not base_ref.strip() or not head_ref.strip():
        raise ValueError(
            "At least one route and two nonempty revision labels are required"
        )
    # A new run directory prevents stale captures from masking a failed run.
    run_dir = output_dir / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    pairs = []
    for index, route in enumerate(routes):
        snapshots = {}
        for side, url in (("base", base_url), ("head", head_url)):
            snapshot = capture_dom_and_visual_snapshot(
                url + route,
                run_dir / str(index) / side,
                save_dom=True,
                isolated_context=True,
                ready_selector=ready_selector,
            )
            snapshots[side] = snapshot
        complete = all(_artifacts_exist(snap) for snap in snapshots.values())
        records = {side: snap.to_dict() for side, snap in snapshots.items()}
        for record in records.values():
            # Single snapshots have no comparison baseline. Never emit their
            # default zero as evidence of a zero-difference paired capture.
            record.pop("mismatch_percentage", None)
        pairs.append(
            {
                "route": route,
                "complete": complete,
                "base": records["base"],
                "head": records["head"],
                "screenshot_bytes_equal": (
                    Path(snapshots["base"].screenshot_path or "").read_bytes()
                    == Path(snapshots["head"].screenshot_path or "").read_bytes()
                )
                if complete
                else None,
            }
        )
    manifest_path = run_dir / "manifest.json"
    result = {
        "complete": all(pair["complete"] for pair in pairs),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "revision_labels_verified": False,
        "route_coverage_verified": False,
        "visual_verdict": "not_evaluated",
        "readiness": ready_selector or "domcontentloaded_only",
        "manifest_path": str(manifest_path),
        "pairs": pairs,
    }
    manifest_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
