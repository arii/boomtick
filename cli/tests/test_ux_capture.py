"""Paired capture tests, all browser and Grid operations stay mocked."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from dev_tools.commands.sessions import ux
from dev_tools.services import ux_capture
from dev_tools.services.browser_cdp import VisualDiffResult


def _fake_capture(url, output_dir, **kwargs):
    assert kwargs["save_dom"] is True
    assert kwargs["isolated_context"] is True
    output_dir.mkdir(parents=True)
    png, dom = output_dir / "shot.png", output_dir / "document.html"
    png.write_bytes(url.encode())
    dom.write_text("<html>offline fake</html>")
    return VisualDiffResult(
        True, url, 0, 4, 1, str(png), dom_path=str(dom), final_url=url
    )


def _run(tmp_path, **kwargs):
    args = {
        "base_url": "http://base.test",
        "head_url": "http://head.test",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "routes": ["/a"],
        "output_dir": tmp_path,
    }
    args.update(kwargs)
    return ux_capture.capture_revision_pair(**args)


def test_pair_manifest_preserves_provenance_and_not_verdict(monkeypatch, tmp_path):
    """The pair manifest records provenance and carries no verdict."""
    monkeypatch.setattr(ux_capture, "capture_dom_and_visual_snapshot", _fake_capture)
    result = _run(tmp_path, routes=["/a", "/a", "/b?filter=x"])
    assert result["complete"] is True
    assert result["revision_labels_verified"] is False
    assert result["route_coverage_verified"] is False
    assert result["visual_verdict"] == "not_evaluated"
    assert result["readiness"] == "domcontentloaded_only"
    assert len(result["pairs"]) == 2
    assert result["pairs"][0]["screenshot_bytes_equal"] is False
    assert "mismatch_percentage" not in result["pairs"][0]["head"]
    assert json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8")) == result
    assert _run(tmp_path)["manifest_path"] != result["manifest_path"]


@pytest.mark.parametrize(
    "route",
    [
        "https://evil.test",
        "//evil.test",
        "/../x",
        "/%2e%2e/x",
        "/a#fragment",
        "/\\evil",
        "/a\n",
    ],
)
def test_invalid_routes_never_capture(monkeypatch, tmp_path, route):
    """Invalid routes are rejected before any capture runs."""
    monkeypatch.setattr(
        ux_capture,
        "capture_dom_and_visual_snapshot",
        lambda *a, **kw: pytest.fail("must validate before capture"),
    )
    with pytest.raises(ValueError):
        _run(tmp_path, routes=[route])
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/x",
        "https://user:pass@site.test",
        "https://site.test?token=x",
        "https://site.test/#x",
    ],
)
def test_invalid_base_never_capture(tmp_path, url):
    """An invalid base URL is rejected before any capture runs."""
    with pytest.raises(ValueError):
        _run(tmp_path, base_url=url)


def test_incomplete_capture_never_reports_comparison(monkeypatch, tmp_path):
    """An incomplete capture never reports a comparison."""
    def capture(url, output_dir, **kwargs):
        if "head" in url:
            return VisualDiffResult(False, url, 0, 0, 0, None, error="unavailable")
        return _fake_capture(url, output_dir, **kwargs)

    monkeypatch.setattr(ux_capture, "capture_dom_and_visual_snapshot", capture)
    result = _run(tmp_path)
    assert result["complete"] is False
    assert result["pairs"][0]["screenshot_bytes_equal"] is None


def test_missing_artifacts_are_incomplete(monkeypatch, tmp_path):
    """Missing artifacts mark the capture incomplete."""
    monkeypatch.setattr(
        ux_capture,
        "capture_dom_and_visual_snapshot",
        lambda url, *a, **kw: VisualDiffResult(
            True, url, 0, 1, 0, "/missing.png", dom_path="/missing.html"
        ),
    )
    assert _run(tmp_path)["complete"] is False


def test_cli_nonzero_on_incomplete_capture(monkeypatch, tmp_path):
    """The CLI exits nonzero on an incomplete capture."""
    monkeypatch.setattr(
        ux_capture, "capture_revision_pair", lambda *a, **kw: {"complete": False}
    )
    result = CliRunner().invoke(
        ux,
        [
            "capture",
            "--base-url",
            "http://base.test",
            "--head-url",
            "http://head.test",
            "--base-ref",
            "base",
            "--head-ref",
            "head",
            "--route",
            "/",
            "--output-dir",
            str(tmp_path),
        ],
        obj={"JSON": True},
    )
    assert result.exit_code == 1
    assert '"complete": false' in result.output


def test_cli_forwards_explicit_inputs(monkeypatch, tmp_path):
    """The CLI forwards explicit inputs unchanged."""
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return {"complete": True}

    monkeypatch.setattr(ux_capture, "capture_revision_pair", capture)
    result = CliRunner().invoke(
        ux,
        [
            "capture",
            "--base-url",
            "http://base.test",
            "--head-url",
            "http://head.test",
            "--base-ref",
            "base",
            "--head-ref",
            "head",
            "--route",
            "/a",
            "--route",
            "/b",
            "--output-dir",
            str(tmp_path),
            "--ready-selector",
            "#app",
        ],
        obj={"JSON": True},
    )
    assert result.exit_code == 0, result.output
    args, kwargs = calls[0]
    assert args[:6] == (
        "http://base.test",
        "http://head.test",
        "base",
        "head",
        ("/a", "/b"),
        tmp_path,
    )
    assert kwargs == {"ready_selector": "#app"}


def test_cli_validation_failure_is_nonzero(monkeypatch, tmp_path):
    """The CLI exits nonzero when validation fails."""
    monkeypatch.setattr(
        ux_capture,
        "capture_dom_and_visual_snapshot",
        lambda *a, **kw: pytest.fail("invalid input must not capture"),
    )
    result = CliRunner().invoke(
        ux,
        [
            "capture",
            "--base-url",
            "file:///tmp/x",
            "--head-url",
            "http://head.test",
            "--base-ref",
            "base",
            "--head-ref",
            "head",
            "--route",
            "/",
            "--output-dir",
            str(tmp_path),
        ],
        obj={"JSON": True},
    )
    assert result.exit_code != 0
    assert "HTTP(S)" in result.output
