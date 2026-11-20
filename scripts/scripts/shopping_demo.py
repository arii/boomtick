#!/usr/bin/env python3
"""Offline Capture -> Coordinate -> Handoff -> Audit demo, never a checkout.

Only synthetic fixtures are accepted. No sponsor SDK, credentials, network calls,
Google Sheet writes or repository observer connection is performed.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

PHASES = ("Capture", "Coordinate", "Handoff", "Audit")
SPONSORS = {
    "senso": {
        "intended_role": "shopping/finance discovery via Senso MCP",
        "status": "pending_contract_and_access",
        "source": "https://docs.senso.ai/docs/mcp-server",
        "gap": "Documented MCP searches an organization knowledge base; shopping data is not verified.",
    },
    "cognee": {
        "intended_role": "cross-assistant graph memory",
        "status": "pending_configuration_and_cost_review",
        "source": "https://docs.cognee.ai/python-api/cognify",
        "gap": "Local receipt replay is not a Cognee graph; graph/embedding setup is unverified.",
    },
    "superlinked": {
        "intended_role": "multimodal product ranking",
        "status": "pending_schema_model_and_access",
        "source": "https://superlinked.com/docs/encode/multimodal",
        "gap": "Fixture price ordering is not vector search or image encoding.",
    },
    "firedrill": {
        "intended_role": "simulation/failover benchmark",
        "status": "pending_workspace_and_approved_credit_estimate",
        "source": "https://firedrill.run/hacker-docs",
        "gap": "Local injected failure is not a Firedrill drill report.",
    },
    "tokensand": {
        "intended_role": "repository observer connection",
        "status": "pending_project_setup_and_disclosure_approval",
        "source": "https://tokensand.com/docs/api",
        "gap": "Private checksum-pinned SDK and explicit instrumentation required; no repo is connected.",
    },
}
FIXTURE_REQUEST = {
    "query": "Compare synthetic noise-cancelling headphones under USD 150",
    "budget_cents": 15000,
    "currency": "USD",
    "purchase_authorized": False,
}
FIXTURE_PRODUCTS = (
    {"id": "fixture-quiet-a", "price_cents": 12900, "currency": "USD"},
    {"id": "fixture-quiet-b", "price_cents": 9900, "currency": "USD"},
    {"id": "fixture-over-budget", "price_cents": 19900, "currency": "USD"},
)


def canonical(value):
    """Stable bytes for integrity checking, not a signature or authenticity proof."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    """Hash one canonical event body."""
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_actor(actor):
    """Allow labels, not arbitrary personal text or secrets, in the demo receipt."""
    if not re.fullmatch(r"assistant-[a-z0-9]{1,16}", actor):
        raise ValueError(
            "actor must be assistant- followed by 1-16 lowercase letters/digits"
        )


def load_events(path):
    """Read and validate a single-task receipt. Refuse partial or modified data."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(
            "incomplete receipt line; preserve evidence and use a new file"
        )
    events = []
    previous = None
    for index, line in enumerate(raw.splitlines()):
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("receipt event must be an object")
        body = {key: value for key, value in event.items() if key != "hash"}
        if event.get("hash") != digest(body):
            raise ValueError("receipt hash mismatch")
        if index >= len(PHASES) or event.get("phase") != PHASES[index]:
            raise ValueError("receipt phases out of order")
        if event.get("seq") != index + 1 or event.get("previous_hash") != previous:
            raise ValueError("receipt chain mismatch")
        if event.get("mode") != "fixture" or event.get("schema_version") != 1:
            raise ValueError("unsupported receipt schema or mode")
        validate_actor(event.get("actor", ""))
        if not re.fullmatch(r"task-[0-9a-f]{32}", event.get("task_id", "")):
            raise ValueError("invalid task key")
        if events and event["task_id"] != events[0]["task_id"]:
            raise ValueError("mixed task keys")
        if not isinstance(event.get("payload"), dict):
            raise ValueError("receipt payload must be an object")
        events.append(event)
        previous = event["hash"]
    return events


@contextmanager
def locked_receipt(path):
    """Serialize local writers on Linux/macOS. The persistent .lock is not a task."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def append_event(path, events, actor, payload):
    """Append one flushed durable event. Caller holds the receipt lock."""
    event = {
        "schema_version": 1,
        "seq": len(events) + 1,
        "task_id": events[0]["task_id"] if events else "task-" + uuid.uuid4().hex,
        "phase": PHASES[len(events)],
        "actor": actor,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fixture",
        "previous_hash": events[-1]["hash"] if events else None,
        "payload": payload,
    }
    event["hash"] = digest(event)
    with path.open("ab") as handle:
        handle.write(canonical(event) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    events.append(event)


def coordinate(simulate_failure):
    """Deterministic price-only comparison of fictional products, never a purchase."""
    eligible = [
        dict(product)
        for product in FIXTURE_PRODUCTS
        if product["currency"] == FIXTURE_REQUEST["currency"]
        and product["price_cents"] <= FIXTURE_REQUEST["budget_cents"]
    ]
    ranked = sorted(
        eligible, key=lambda product: (product["price_cents"], product["id"])
    )
    return {
        "attempts": (
            [{"adapter": "fixture-primary", "status": "simulated_timeout"}]
            if simulate_failure
            else []
        )
        + [
            {
                "adapter": "fixture-fallback"
                if simulate_failure
                else "fixture-primary",
                "status": "ok",
            }
        ],
        "ranking_method": "synthetic price ascending; not multimodal",
        "products": ranked,
        "proposed_product_id": ranked[0]["id"],
        "decision": "Needs Okay",
        "purchase_executed": False,
    }


def summary(events):
    """Return honest evidence boundaries alongside the result."""
    return {
        "mode": "fixture",
        "task_id": events[0]["task_id"] if events else None,
        "phases": [event["phase"] for event in events],
        "actors": list(dict.fromkeys(event["actor"] for event in events)),
        "chain_valid": True,
        "decision": "Needs Okay",
        "purchase_executed": False,
        "sponsor_integrations_live": False,
        "live_sheet_reader_verified": False,
        "real_two_assistant_loop_verified": False,
        "note": "Local labels/process replay only. Hash chain is not signed or tamper-proof.",
    }


def run_demo(
    path, actor, resume=False, stop_after_handoff=False, simulate_failure=False
):
    """Run or resume from the durable receipt, without external side effects."""
    validate_actor(actor)
    with locked_receipt(path):
        events = load_events(path)
        if resume:
            if len(events) < 3:
                raise ValueError("resume requires a persisted Handoff")
            if len(events) == 4:
                return summary(events)  # Idempotent retry, no duplicate audit event.
            if events[2]["payload"].get("next_actor") != actor:
                raise ValueError(
                    "resume actor must match the persisted handoff recipient"
                )
        elif events:
            raise ValueError(
                "receipt already exists; use resume or choose a new receipt"
            )
        if not events:
            append_event(
                path, events, actor, {"request": FIXTURE_REQUEST, "sponsors": SPONSORS}
            )
            append_event(path, events, actor, coordinate(simulate_failure))
            next_actor = "assistant-b" if actor != "assistant-b" else "assistant-a"
            append_event(
                path,
                events,
                actor,
                {
                    "next_actor": next_actor,
                    "context": {
                        "task_id": events[0]["task_id"],
                        "decision": "Needs Okay",
                        "proposed_product_id": events[1]["payload"][
                            "proposed_product_id"
                        ],
                    },
                    "memory_backend": "local JSONL replay, not Cognee",
                },
            )
            if stop_after_handoff:
                return summary(events)
        append_event(
            path,
            events,
            actor,
            {
                "prior_events_checked": len(events),
                "previous_receipt_hash": events[-1]["hash"],
                "outcome": "comparison prepared; human purchase approval still required",
                "execution": "separate-process resume"
                if resume
                else "single-process fixture",
                "live_sponsors": [],
                "external_writes": 0,
            },
        )
        return summary(load_events(path))


def main(argv=None):
    """Run the safe scaffold. There is deliberately no live/checkout option."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "resume", "audit", "integrations"))
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--actor", default="assistant-a")
    parser.add_argument("--stop-after-handoff", action="store_true")
    parser.add_argument("--simulate-failure", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "integrations":
        result = {"mode": "fixture", "sponsors": SPONSORS}
    else:
        if not args.receipt:
            parser.error("--receipt is required")
        if args.command != "run" and (args.stop_after_handoff or args.simulate_failure):
            parser.error("failure/stop flags apply only to run")
        try:
            if args.command == "audit":
                with locked_receipt(args.receipt):
                    events = load_events(args.receipt)
                    if not events:
                        raise ValueError("no receipt events")
                    result = summary(events)
            else:
                result = run_demo(
                    args.receipt,
                    args.actor,
                    args.command == "resume",
                    args.stop_after_handoff,
                    args.simulate_failure,
                )
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(
                json.dumps({"error": str(error), "external_writes": 0}), file=sys.stderr
            )
            return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
