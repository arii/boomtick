"""Local replay acceptance rules. Not a safety proof or an LLM evaluation.

Compare the same tasks and individual required checks. A candidate must improve
passed-task count, lose no passing check, and add no failed checks. No confidence
or constraint probability is invented from deterministic counts.
"""


def decide(baseline, candidate, tasks):
    def rows(report):
        result = {r["task_id"]: r for r in report["results"]}
        if len(result) != len(report["results"]):
            raise ValueError("duplicate replay task ids")
        return result

    before, after = rows(baseline), rows(candidate)
    expected = {t["id"] for t in tasks}
    if not expected or len(expected) != len(tasks) or set(before) != expected or set(after) != expected:
        raise ValueError("gate requires the same nonempty unique task suite")
    regressions = []
    failed_before = failed_after = passed_before = passed_after = 0
    for task in tasks:
        tid = task["id"]
        checks = set(task["required_checks"])
        old = set(before[tid]["failed_checks"])
        new = set(after[tid]["failed_checks"])
        if not old <= checks or not new <= checks:
            raise ValueError("unknown check in replay results")
        regressions.extend(f"{tid}:{check}" for check in sorted(new - old))
        failed_before += len(old)
        failed_after += len(new)
        passed_before += not old
        passed_after += not new
    if regressions or passed_after < passed_before or failed_after > failed_before:
        choice, reason = "reject_and_refine", "replay regression"
    elif passed_after > passed_before:
        choice, reason = "promote", "more tasks pass with no lost passing checks"
    else:
        choice, reason = "hold", "no strict increase in passed tasks"
    return {"policy": "local-replay-v1", "source": "local", "choice": choice, "reason": reason,
            "regressed_checks": regressions, "failed_checks_before": failed_before,
            "failed_checks_after": failed_after, "scope": "deterministic replay checks only"}
