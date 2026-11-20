"""Offline shopping scaffold: persistence, handoff, failures and safety boundaries."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "shopping_demo.py"
SPEC = importlib.util.spec_from_file_location("shopping_demo", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


def cli(*args):
    """Use a fresh interpreter so a resume cannot rely on in-memory state."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_four_phase_loop_persists_and_audits(tmp_path):
    """Verify four phase loop persists and audits."""
    receipt = tmp_path / "receipt.jsonl"
    result = DEMO.run_demo(receipt, "assistant-a")
    assert result["phases"] == list(DEMO.PHASES)
    events = DEMO.load_events(receipt)
    assert len({event["task_id"] for event in events}) == 1
    assert events[-1]["payload"]["prior_events_checked"] == 3
    assert result["decision"] == "Needs Okay"
    assert result["purchase_executed"] is False
    assert result["sponsor_integrations_live"] is False
    assert result["real_two_assistant_loop_verified"] is False
    assert result["live_sheet_reader_verified"] is False


def test_handoff_resumes_in_a_separate_process_without_duplicate_events(tmp_path):
    """Verify handoff resumes in a separate process without duplicate events."""
    receipt = tmp_path / "receipt.jsonl"
    first = cli("run", "--receipt", receipt, "--stop-after-handoff")
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["phases"] == list(DEMO.PHASES[:3])
    second = cli("resume", "--receipt", receipt, "--actor", "assistant-b")
    assert second.returncode == 0, second.stderr
    result = json.loads(second.stdout)
    assert result["actors"] == ["assistant-a", "assistant-b"]
    assert result["task_id"] == json.loads(first.stdout)["task_id"]
    assert (
        DEMO.load_events(receipt)[-1]["payload"]["execution"]
        == "separate-process resume"
    )
    before = receipt.read_bytes()
    retry = cli("resume", "--receipt", receipt, "--actor", "assistant-b")
    assert retry.returncode == 0
    assert receipt.read_bytes() == before


def test_failure_is_recorded_then_fixture_fallback_succeeds(tmp_path):
    """Verify failure is recorded then fixture fallback succeeds."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-a", simulate_failure=True)
    coordination = DEMO.load_events(receipt)[1]["payload"]
    assert [item["status"] for item in coordination["attempts"]] == [
        "simulated_timeout",
        "ok",
    ]
    assert coordination["attempts"][1]["adapter"] == "fixture-fallback"
    assert coordination["proposed_product_id"] == "fixture-quiet-b"
    assert all(product["price_cents"] <= 15000 for product in coordination["products"])
    assert all(product["currency"] == "USD" for product in coordination["products"])


def test_wrong_actor_cannot_accept_handoff(tmp_path):
    """Verify wrong actor cannot accept handoff."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-a", stop_after_handoff=True)
    before = receipt.read_bytes()
    with pytest.raises(ValueError, match="recipient"):
        DEMO.run_demo(receipt, "assistant-c", resume=True)
    assert receipt.read_bytes() == before


def test_handoff_target_changes_when_initial_actor_is_b(tmp_path):
    """Verify handoff target changes when initial actor is b."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-b", stop_after_handoff=True)
    assert DEMO.load_events(receipt)[2]["payload"]["next_actor"] == "assistant-a"
    assert DEMO.run_demo(receipt, "assistant-a", resume=True)["phases"][-1] == "Audit"


def test_existing_receipt_is_never_replaced(tmp_path):
    """Verify existing receipt is never replaced."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-a")
    before = receipt.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        DEMO.run_demo(receipt, "assistant-a")
    assert receipt.read_bytes() == before


@pytest.mark.parametrize(
    "mutation", ["payload", "truncate", "reorder", "mixed_key", "schema"]
)
def test_invalid_receipts_fail_closed(tmp_path, mutation):
    """Verify invalid receipts fail closed."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-a")
    events = DEMO.load_events(receipt)
    if mutation == "truncate":
        receipt.write_bytes(receipt.read_bytes()[:-2])
    else:
        if mutation == "payload":
            events[1]["payload"]["decision"] = "Approved"
        elif mutation == "reorder":
            events[0], events[1] = events[1], events[0]
        else:
            key, value = (
                ("task_id", "task-" + "f" * 32)
                if mutation == "mixed_key"
                else ("schema_version", 99)
            )
            events[1][key] = value
            events[1]["hash"] = DEMO.digest(
                {k: v for k, v in events[1].items() if k != "hash"}
            )
        receipt.write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )
    before = receipt.read_bytes()
    result = cli("audit", "--receipt", receipt)
    assert result.returncode == 1
    assert "error" in json.loads(result.stderr)
    assert receipt.read_bytes() == before


def test_missing_or_empty_receipt_is_not_proof(tmp_path):
    """Verify missing or empty receipt is not proof."""
    for command in ("resume", "audit"):
        result = cli(command, "--receipt", tmp_path / "missing.jsonl")
        assert result.returncode == 1
        assert not (tmp_path / "missing.jsonl").exists()


def test_actor_rejects_arbitrary_text(tmp_path):
    """Verify actor rejects arbitrary text."""
    with pytest.raises(ValueError, match="actor"):
        DEMO.run_demo(tmp_path / "receipt.jsonl", "personal text or secret")
    assert not (tmp_path / "receipt.jsonl").exists()


def test_all_sponsors_are_explicitly_pending_and_no_live_mode_exists():
    """Verify all sponsors are explicitly pending and no live mode exists."""
    result = cli("integrations")
    assert result.returncode == 0
    sponsors = json.loads(result.stdout)["sponsors"]
    assert set(sponsors) == {"senso", "cognee", "superlinked", "firedrill", "tokensand"}
    assert all(item["status"].startswith("pending_") for item in sponsors.values())
    assert cli("run", "--live").returncode == 2


def test_audit_does_not_change_receipt(tmp_path):
    """Verify audit does not change receipt."""
    receipt = tmp_path / "receipt.jsonl"
    DEMO.run_demo(receipt, "assistant-a")
    before = receipt.read_bytes()
    result = cli("audit", "--receipt", receipt)
    assert result.returncode == 0
    assert json.loads(result.stdout)["chain_valid"] is True
    assert receipt.read_bytes() == before


def test_failure_flags_are_not_silently_ignored_on_resume(tmp_path):
    """Verify failure flags are not silently ignored on resume."""
    result = cli(
        "resume", "--receipt", tmp_path / "receipt.jsonl", "--simulate-failure"
    )
    assert result.returncode == 2
