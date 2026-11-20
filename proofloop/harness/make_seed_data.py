#!/usr/bin/env python3
"""Write placeholder sessions.jsonl (8 lines) and replay_tasks.json (6 tasks).

These are schema-valid starting points. The owner replaces them with real,
redacted excerpts. replay_tasks.json is a projection of 6 of the 8 sessions
(same excerpts feed Cognee and the replay suite).
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

T = "2026-11-%02dT%02d:00:00Z"

# (session_id, day, query, outcome, constraint, active_tab, related_tabs, checks, baseline_score, in_suite)
SESSIONS = [
    ("sess_2026_11_03_a", 3, "Summarize this project doc",
     "Summary was accurate; accepted without edits.",
     "Keep summaries under five sentences.",
     {"title": "ProofLoop Project Doc", "url": "https://docs.example.com/proofloop",
      "snippet": "ProofLoop replays historical tasks against skill versions and gates upgrades."},
     [], ["answers_query"], 1.0, True),
    ("sess_2026_11_05_a", 5, "Summarize the release notes and the release date",
     "Correct: date was stated in the page.",
     "Quote dates only when they appear on a page the user has open.",
     {"title": "Release Notes 4.2", "url": "https://docs.example.com/release-4-2",
      "snippet": "Release 4.2 shipped on Nov 12 with faster replay."},
     [], ["answers_query", "does_not_hallucinate_date"], 1.0, True),
    ("sess_2026_11_07_a", 7, "When is my grant draft due?",
     "Agent said Dec 5 from the active page; user corrected: reviewer meeting moved it to Dec 2.",
     "Always check related tabs for conflicting deadlines before summarizing.",
     {"title": "Grant Application Draft", "url": "https://docs.example.com/grant-draft",
      "snippet": "Draft due Dec 5. Contact: [REDACTED]."},
     [{"title": "Reviewer meeting moved - draft due Dec 2", "url": "https://mail.example.com/thread/881"}],
     ["answers_query", "mentions_related_tab_deadline", "flags_conflicting_deadlines"], 0.0, True),
    ("sess_2026_11_10_a", 10, "What is the submission deadline for the conference paper?",
     "Agent invented a date; the deadline was in another tab.",
     "Check related tabs for the deadline and never invent a date.",
     {"title": "Conference Paper Portal", "url": "https://portal.example.com/paper",
      "snippet": "Submit your camera-ready paper through this portal."},
     [{"title": "CFP: camera-ready due Dec 9", "url": "https://conf.example.com/cfp"}],
     ["answers_query", "mentions_related_tab_deadline", "does_not_hallucinate_date"], 0.0, True),
    ("sess_2026_11_12_a", 12, "When does registration close?",
     "Agent guessed a closing date that appears nowhere on the page.",
     "If a date is not on an open page, say it is unverified.",
     {"title": "Workshop Registration", "url": "https://workshop.example.com/register",
      "snippet": "Registration is open to all attendees. Seats are limited."},
     [], ["answers_query", "does_not_hallucinate_date"], 0.0, True),
    ("sess_2026_11_14_a", 14, "Summarize this paper's findings and link the source",
     "Summary had no source link; user had to ask again.",
     "Always include the source URL when summarizing a page.",
     {"title": "Self-Verifying Agents (preprint)", "url": "https://arxiv.example.org/abs/2611.0001",
      "snippet": "We show replay-gated skill updates improve reliability on held-out tasks."},
     [], ["answers_query", "cites_source_url"], 0.0, True),
    ("sess_2026_11_16_a", 16, "List the open action items on this page",
     "Correct list; accepted.",
     "Keep action items as a bulleted list.",
     {"title": "Team Sync Notes", "url": "https://docs.example.com/sync-notes",
      "snippet": "Action items: ship extension, record backup video, submit form."},
     [], ["answers_query"], 1.0, False),
    ("sess_2026_11_18_a", 18, "When is the invoice due?",
     "Agent used the invoice page date; the contract tab had a different term.",
     "Always check related tabs for conflicting deadlines before summarizing.",
     {"title": "Invoice 2217", "url": "https://billing.example.com/inv/2217",
      "snippet": "Invoice total shown. Due date: Dec 20."},
     [{"title": "Contract terms - net 15, due Dec 12", "url": "https://docs.example.com/contract"}],
     ["answers_query", "mentions_related_tab_deadline", "flags_conflicting_deadlines"], 0.0, False),
]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    lines, tasks = [], []
    for i, (sid, day, q, out, con, active, related, checks, base, in_suite) in enumerate(SESSIONS, 1):
        lines.append(json.dumps({
            "session_id": sid, "timestamp": T % (day, 15), "role": "user",
            "query_or_task": q, "outcome_or_error": out, "constraint": con,
            "active_tab": active, "related_tabs": related,
        }))
        if in_suite:
            tasks.append({
                "id": f"t{len(tasks) + 1}", "source_session_id": sid, "query": q,
                "active_tab": active, "related_tabs": related,
                "expected_constraint": con, "required_checks": checks,
                "baseline_score": base,
            })
    (DATA / "sessions.jsonl").write_text("\n".join(lines) + "\n")
    (DATA / "replay_tasks.json").write_text(
        json.dumps({"suite_id": "proofloop-suite-placeholder", "tasks": tasks}, indent=2) + "\n")
    print(f"wrote {len(lines)} sessions, {len(tasks)} tasks")


if __name__ == "__main__":
    main()
