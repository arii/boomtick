"""Skill executor and checks for the replay harness.

A skill is {"version", "steps": [step_id, ...]}. The executor interprets the
steps against a task's tab context and produces an answer; each required check
is then evaluated on that answer. No pass rate is hardcoded: it comes from
running these functions over the task suite.
"""
import re

# step id -> what it does (also used as the vocabulary for LLM mutation)
KNOWN_STEPS = {
    "summarize_page": "Answer the query from the active tab snippet.",
    "check_related_tabs": "Scan related tab titles for deadlines and flag conflicts with the active page.",
    "verify_dates": "Only state dates found on open pages; otherwise say the date is unverified.",
    "cite_sources": "Append the active tab URL as the source.",
}

# check -> step that fixes it (used by the rule-based mutator)
CHECK_FIX = {
    "mentions_related_tab_deadline": "check_related_tabs",
    "flags_conflicting_deadlines": "check_related_tabs",
    "does_not_hallucinate_date": "verify_dates",
    "cites_source_url": "cite_sources",
}

DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}\b")
DATE_QUERY_RE = re.compile(r"\b(when|deadline|due|close|closes|date)\b", re.I)
# What an unconstrained model does when asked for a date it cannot see.
GUESSED_DATE = "Nov 27"


def dates_in(text):
    return DATE_RE.findall(text)


def run_task(skill, task):
    steps = set(skill["steps"])
    active, related = task["active_tab"], task["related_tabs"]
    parts = []
    asked_date = bool(DATE_QUERY_RE.search(task["query"]))
    active_dates = dates_in(active["snippet"])

    if "summarize_page" in steps:
        parts.append(f'Answering "{task["query"]}" from {active["title"]}.')
    if asked_date:
        if active_dates:
            parts.append(f"Page date: {active_dates[0]}.")
        elif "verify_dates" in steps:
            parts.append("Date unverified: no open page states it.")
        else:
            parts.append(f"Date: {GUESSED_DATE}.")
    if "check_related_tabs" in steps:
        rel = [(t["title"], d) for t in related for d in dates_in(t["title"])]
        for title, d in rel:
            parts.append(f"Related tab deadline: {d} ({title}).")
        if rel and active_dates and rel[0][1] != active_dates[0]:
            parts.append(f"Conflict: page says {active_dates[0]}, related tab says {rel[0][1]}.")
    if "cite_sources" in steps:
        parts.append(f'Source: {active["url"]}')
    return " ".join(parts)


def _source_dates(task):
    out = set(dates_in(task["active_tab"]["snippet"]))
    for t in task["related_tabs"]:
        out |= set(dates_in(t["title"]))
    return out


def evaluate_check(check, task, answer):
    if check == "answers_query":
        return bool(answer.strip()) and task["active_tab"]["title"] in answer
    if check == "mentions_related_tab_deadline":
        want = {d for t in task["related_tabs"] for d in dates_in(t["title"])}
        return bool(want) and all(d in answer for d in want)
    if check == "flags_conflicting_deadlines":
        return "Conflict:" in answer
    if check == "does_not_hallucinate_date":
        return set(dates_in(answer)) <= _source_dates(task)
    if check == "cites_source_url":
        return task["active_tab"]["url"] in answer
    raise ValueError(f"unknown check: {check}")


def replay(skill, tasks):
    """Run all tasks. Returns per-task results and aggregate counts."""
    results = []
    for t in tasks:
        answer = run_task(skill, t)
        failed = [c for c in t["required_checks"] if not evaluate_check(c, t, answer)]
        results.append({"task_id": t["id"], "passed": not failed, "failed_checks": failed, "answer": answer})
    passed = sum(r["passed"] for r in results)
    total_checks = sum(len(t["required_checks"]) for t in tasks)
    violations = sum(len(r["failed_checks"]) for r in results)
    return {"results": results, "passed": passed, "total": len(tasks),
            "pass_rate": round(passed / len(tasks), 4) if tasks else 0.0,
            "violations": violations, "total_checks": total_checks}
