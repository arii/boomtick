"""Skill executor and checks for the replay harness.

A skill is {"version", "steps": [step_id, ...]}. The executor is a deterministic MODEL of an
agent, not an LLM run: for each slot in a task it decides what the agent would write given
the skill's steps. The un-upgraded value (slot.baseline) comes from the recorded outcome of
the real session. Steps change behavior:

  answer_from_active_tab  (base) emit slot values; without other steps, emit slot.baseline
  ground_in_related_tabs  use slot.source_hint when an open tab (active or related) contains it
  ask_when_unstated       field with no grounding value -> "Clarify: what is your <slot>?"
  trace_to_source         claim with no grounding value -> "Omitted (unverifiable): <slot>"

Checks are then evaluated on the answer text. No pass rate is hardcoded.
"""

KNOWN_STEPS = {
    "answer_from_active_tab": "Answer the query from the active tab.",
    "ground_in_related_tabs": "Fill values from facts found in the active and related tabs, not from assumptions.",
    "ask_when_unstated": "When a form value is not stated in any open tab, ask instead of assuming.",
    "trace_to_source": "Only state claims (numbers, URLs, dates) that appear in an open tab; omit the rest.",
}

# step -> instruction written into the agent prompt when the step is part of the active skill
PROMPT_RULES = {
    "answer_from_active_tab": "Answer from the page the user has open, and say which page you used.",
    "ground_in_related_tabs": "Before filling a form field or stating a fact, look for it in the open tabs and use that value. Never substitute a guess or a default, such as a different city or a different phone number.",
    "ask_when_unstated": "If a required value is not stated in any open tab or by the user, ask the user instead of assuming it.",
    "trace_to_source": "Only state numbers, URLs, dates or results that appear in an open tab, a script or a recorded run. If you cannot trace a claim to a source, leave it out or say it is unverified.",
}

# check name (before ':') -> step that fixes it
CHECK_FIX = {
    "must_include": "ground_in_related_tabs",
    "must_not_include": "ground_in_related_tabs",
    "asks_clarification": "ask_when_unstated",
    "no_unsupported_claims": "trace_to_source",
}

BASE_STEP = "answer_from_active_tab"


def check_name(check):
    return check.split(":", 1)[0]


def _tab_texts(task):
    tabs = [task["active_tab"]] + task["related_tabs"]
    return [" ".join(t.get(k, "") for k in ("title", "url", "snippet")) for t in tabs]


def resolve_slot(slot, steps, task):
    hint, kind = slot.get("source_hint"), slot["kind"]
    texts = _tab_texts(task)
    if "ground_in_related_tabs" in steps and hint and any(hint in t for t in texts):
        return hint
    if hint is None:
        if kind == "field" and "ask_when_unstated" in steps:
            return f"Clarify: what is your {slot['slot']}?"
        if kind == "claim" and "trace_to_source" in steps:
            return f"Omitted (unverifiable): {slot['slot']}"
    return slot["baseline"]


def run_task(skill, task):
    steps = set(skill["steps"])
    if BASE_STEP not in steps:
        return ""
    parts = [f'Answering "{task["query"]}" from {task["active_tab"]["title"]}.']
    for slot in task.get("slots", []):
        parts.append(f'{slot["slot"]}: {resolve_slot(slot, steps, task)}')
    return " | ".join(parts)


def evaluate_check(check, task, answer):
    name, _, arg = check.partition(":")
    if name == "answers_query":
        return bool(answer) and task["active_tab"]["title"] in answer
    if name == "must_include":
        return arg in answer
    if name == "must_not_include":
        return arg not in answer
    if name == "asks_clarification":
        return f"Clarify: what is your {arg}?" in answer
    if name == "no_unsupported_claims":
        return _claims_supported(task, answer, " ".join(_tab_texts(task)))
    raise ValueError(f"unknown check: {check}")


def _claims_supported(task, answer, sources):
    """Every claim slot's emitted value must appear in an open tab (or be an explicit omission)."""
    for slot in task.get("slots", []):
        if slot["kind"] != "claim":
            continue
        line = next((p for p in answer.split(" | ") if p.startswith(slot["slot"] + ": ")), None)
        if line is None:
            continue
        value = line[len(slot["slot"]) + 2:]
        if value.startswith("Omitted"):
            continue
        if value not in sources:
            return False
    return True


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
