import json
from collections import Counter


def usage(payload):
    data = payload.get("usage") or {}
    if not isinstance(data, dict):
        data = {}
    details = data.get("completion_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    def count(value):
        return value if type(value) is int and value >= 0 else None
    prompt = count(data.get("prompt_tokens"))
    completion = count(data.get("completion_tokens"))
    reasoning = count(details.get("reasoning_tokens"))
    return {"prompt_tokens": prompt, "completion_tokens": completion,
            "reasoning_tokens": reasoning, "visible_tokens": max(0, completion - reasoning)
            if completion is not None and reasoning is not None else None}


def flags_for(store, trace, context):
    flags = []
    if (trace["reasoning_tokens"] is not None and trace["visible_tokens"] is not None
            and trace["reasoning_tokens"] > 3 * trace["visible_tokens"]):
        flags.append("EXCESSIVE_REASONING")
    prompt = trace["prompt_tokens"]
    if prompt is not None and (prompt > 32000 or (context and prompt > context * .8)):
        flags.append("CONTEXT_BLOAT")
    if sum(a["called"] for a in trace["attempts"]) > 1:
        flags.append("FALLBACK_CASCADE")
    signatures = []
    choices = trace["response"].get("choices", [])
    for choice in choices if isinstance(choices, list) else []:
        if not isinstance(choice, dict):
            continue
        if choice.get("finish_reason") == "length" and "TRUNCATED_MAX_TOKENS" not in flags:
            flags.append("TRUNCATED_MAX_TOKENS")
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        calls = message.get("tool_calls") or []
        for call in calls if isinstance(calls, list) else []:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                continue
            function = call["function"]
            arguments = function.get("arguments", "")
            try:
                arguments = json.loads(arguments)
            except (ValueError, TypeError):
                pass
            signatures.append(json.dumps([function.get("name"), arguments], sort_keys=True))
    if store.repeated_tools(trace["session_id"], signatures):
        flags.append("TOOL_CALL_LOOP")
    return flags


def inspect_trace(trace):
    return "\n".join([
        f"# Trace {trace['trace_id']}",
        f"Route: {trace['route']} | Privacy: {trace['privacy']} | Session: {trace['session_id'] or '(none)'}",
        f"Provider/model: {trace['provider']}/{trace['model']}",
        f"HTTP: {trace['http_status']} | Latency: {trace['latency_ms']:.1f} ms | Cost USD: {trace['cost_usd']}",
        f"Tokens: prompt={trace['prompt_tokens']} completion={trace['completion_tokens']} "
        f"reasoning={trace['reasoning_tokens']} visible={trace['visible_tokens']}",
        f"Flags: {', '.join(trace['flags']) or 'none'}", "## Waterfall attempts",
        *[f"- {a['provider']}/{a['model']}: {a['reason']} (HTTP {a['http_status']}, {a['latency_ms']:.1f} ms)"
          for a in trace["attempts"]],
        "## Prompt / request", "```json", json.dumps(trace["request"], indent=2), "```",
        "## Response", "```json", json.dumps(trace["response"], indent=2), "```",
    ])


FIXES = {
    "EXCESSIVE_REASONING": "Lower reasoning effort or cap max_tokens.",
    "TOOL_CALL_LOOP": "Deduplicate tool calls by name and canonical arguments within the session.",
    "CONTEXT_BLOAT": "Trim history or summarize older messages before sending the next prompt.",
    "TRUNCATED_MAX_TOKENS": "Raise max_tokens for this task or request a shorter answer.",
}


def report(traces):
    groups = {}
    failures = Counter()
    all_flags = Counter()
    for trace in traces:
        attempts = [a for a in trace["attempts"] if a["called"]]
        for attempt in attempts:
            key = (trace["route"], attempt["provider"], attempt["model"])
            row = groups.setdefault(key, {"calls": 0, "spend_usd": 0, "unknown_cost_calls": 0, "unknown_usage_calls": 0,
                                          "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
                                          "flags": Counter()})
            row["calls"] += 1
            row["spend_usd"] += attempt["cost_usd"] or 0
            row["unknown_cost_calls"] += attempt["cost_usd"] is None
            row["unknown_usage_calls"] += attempt["prompt_tokens"] is None or attempt["completion_tokens"] is None
            for field in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
                row[field] += attempt[field] or 0
        for key in {(trace["route"], a["provider"], a["model"]) for a in attempts}:
            groups[key]["flags"].update(trace["flags"])
        all_flags.update(trace["flags"])
        for attempt in trace["attempts"]:
            if attempt["called"] and attempt["reason"] != "success":
                failures[(attempt["provider"], attempt["reason"])] += 1
    fixes = {flag: FIXES[flag] for flag in all_flags if flag in FIXES}
    if "FALLBACK_CASCADE" in all_flags:
        providers = Counter()
        for (provider, _), count in failures.items():
            providers[provider] += count
        worst = providers.most_common(1)[0][0] if providers else "unknown"
        reasons = {reason: count for (provider, reason), count in failures.items() if provider == worst}
        fixes["FALLBACK_CASCADE"] = f"Repair or deprioritize {worst}; failures: {reasons}."
    return {"groups": [{"route": key[0], "provider": key[1], "model": key[2], **row}
                       for key, row in groups.items()], "flag_counts": all_flags, "fixes": fixes}
