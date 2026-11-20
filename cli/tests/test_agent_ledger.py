"""Unit tests for scripts/agent_ledger.py key-identity behavior.

The Link field doubles as the task key and the store folds
latest-row-per-key, so two distinct tasks posted with the same URL merge
in the read view. These tests pin the collision-safe write path:
`new --link` mints a unique task-<id> key while preserving the URL in the
note, and legacy `post --link` keeps URL-as-key but warns.
"""

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "agent_ledger.py"
spec = importlib.util.spec_from_file_location("agent_ledger", LEDGER_PATH)
agent_ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_ledger)

FORM_URL = "https://docs.google.com/forms/d/e/TEST/formResponse"
URL = "https://github.com/arii/boomtick/pull/1314"


def run_cli(argv):
    """Run agent_ledger.main() with argv, returning (exit_code, result_dict)."""
    buf = io.StringIO()
    old_argv = sys.argv
    sys.argv = ["agent_ledger.py"] + argv
    try:
        with redirect_stdout(buf):
            rc = agent_ledger.main()
    finally:
        sys.argv = old_argv
    return rc, json.loads(buf.getvalue())


def dry(argv):
    rc, res = run_cli(["--form-url", FORM_URL, "--dry-run"] + argv)
    assert rc == 0
    return res


def test_new_with_link_mints_unique_key_and_preserves_url():
    first = dry(["new", "--source", "t", "--note", "task one", "--link", URL])
    second = dry(["new", "--source", "t", "--note", "task two", "--link", URL])
    assert first["key"].startswith("task-")
    assert second["key"].startswith("task-")
    # the whole point: distinct tasks about the same URL get distinct keys
    assert first["key"] != second["key"]
    # the key, not the URL, goes into the Link field; the URL survives in the note
    assert first["fields"]["entry.1391612799"] == first["key"]
    assert URL in first["fields"]["entry.526880121"]
    assert first["link"] == URL


def test_new_without_link_keeps_note_unchanged():
    res = dry(["new", "--source", "t", "--note", "plain task"])
    assert res["key"].startswith("task-")
    assert res["fields"]["entry.526880121"] == "plain task"
    assert res["fields"]["entry.1391612799"] == res["key"]
    assert "link" not in res


def test_post_with_url_link_keeps_legacy_key_but_warns():
    res = dry(["post", "--source", "t", "--note", "about that PR", "--link", URL])
    # legacy identity preserved: the URL is still the key
    assert res["fields"]["entry.1391612799"] == URL
    assert "merges under latest-per-key folding" in res["warning"]


def test_post_without_link_does_not_warn():
    res = dry(["post", "--source", "t", "--note", "no link"])
    assert "warning" not in res
    assert res["fields"]["entry.1391612799"] == ""


def test_update_and_claim_post_under_the_given_key():
    res = dry(
        [
            "update",
            "--source",
            "t",
            "--note",
            "progress",
            "--key",
            URL,
            "--status",
            "Done",
        ]
    )
    assert res["fields"]["entry.1391612799"] == URL
    assert res["key"] == URL
    res = dry(["claim", "--source", "t", "--key", "task-abc123def456"])
    assert res["fields"]["entry.1391612799"] == "task-abc123def456"
    assert res["fields"]["entry.910915240"] == "Act"


def test_viewform_share_link_converted_to_formresponse(monkeypatch):
    captured = {}

    def fake_post_row(form_url, source, note, status, link, dry_run):
        captured["form_url"] = form_url
        return {"submitted": True}

    monkeypatch.setattr(agent_ledger, "post_row", fake_post_row)
    rc, _ = run_cli(
        [
            "--form-url",
            "https://docs.google.com/forms/d/e/TEST/viewform?usp=header",
            "post",
            "--source",
            "t",
            "--note",
            "n",
        ]
    )
    assert rc == 0
    assert captured["form_url"].endswith("/formResponse")
