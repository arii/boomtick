#!/usr/bin/env python3
"""Health checks per service: GREEN (live and answering), STUB (no key, stub in use), RED (key set but failing).
    python3 health.py
Never prints key values.
"""
import sys

import clients
import config


def check_senso():
    if config.mode("senso") == "stub":
        return "STUB", "no SENSO_API_KEY; local stub in use"
    r = clients.SensoLive().health()
    return "GREEN", f"GET /org/me -> {r['status']}"


def check_openrouter():
    if config.mode("llm") == "stub":
        return "STUB", "no OPENROUTER_API_KEY; rule-based mutator in use"
    body = {"model": config.get("OPENROUTER_MODEL", "arcee-ai/trinity-large-thinking:free"),
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
    headers = {"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}
    s, _ = clients.http_json("POST", f"{config.base_url('openrouter')}/api/v1/chat/completions", headers, body, timeout=60)
    return "GREEN", f"chat/completions -> {s} (model {body['model']})"


def check_cognee():
    if config.mode("cognee") == "stub":
        return "STUB", "no COGNEE_API_URL; local graph stub in use"
    c = clients.CogneeLive()
    c.ingest([{"session_id": "sess_0000_00_00_healthcheck", "constraint": "healthcheck"}])
    c.search("healthcheck")
    return "GREEN", "add + cognify + search round trip"


def main():
    red = False
    for name, fn in [("senso", check_senso), ("openrouter", check_openrouter), ("cognee", check_cognee)]:
        try:
            state, msg = fn()
        except clients.ApiError as e:
            state, msg, red = "RED", str(e)[:160], True
        print(f"{name:11s} {state:5s} {msg}")
    print(f"gate        LOCAL deterministic threshold gate (Jev disabled)")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
