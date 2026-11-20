#!/usr/bin/env python3
"""Default: show configuration only, no network calls.

--probe-live explicitly invokes enabled services and may use credits. Configured
credentials are not proof of connectivity. Review inputs/permissions beforehand.
"""
import argparse
import sys

import clients
import config


def check_senso():
    if config.mode("senso") == "stub":
        return "STUB", "not explicitly enabled with credentials"
    result = clients.SensoLive().health()
    if result["status"] != 200:
        raise clients.ApiError(result["status"], "health request not successful")
    return "GREEN", "GET /org/me succeeded (does not prove ingest/search)"


def check_openrouter():
    if config.mode("llm") == "stub":
        return "STUB", "not explicitly enabled with credentials"
    body = {"model": config.get("OPENROUTER_MODEL", config.DEFAULT_LLM_MODEL),
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
    headers = {"Authorization": f"Bearer {config.get('OPENROUTER_API_KEY')}"}
    status, response = clients.http_json("POST", f"{config.base_url('openrouter')}/api/v1/chat/completions", headers, body, timeout=60)
    if status != 200 or not response.get("choices"):
        raise clients.ApiError(status, "completion response missing choices")
    return "GREEN", "synthetic one-token completion succeeded (not replay/executor proof)"


def check_cognee():
    if config.mode("cognee") == "stub":
        return "STUB", "not explicitly enabled with credentials"
    client = clients.CogneeLive()
    client.DATASET = "proofloop_healthcheck"
    client.ingest([{"session_id": "sess_0000_00_00_healthcheck", "constraint": "healthcheck"}])
    hits = client.search("healthcheck")
    if not hits:
        raise clients.ApiError(0, "healthcheck readback empty")
    return "GREEN", "synthetic healthcheck add/cognify/search; remote test data remains"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-live", action="store_true", help="call explicitly enabled services; may use credits")
    args = parser.parse_args()
    if not args.probe_live:
        for service, info in config.status().items():
            print(f"{service}: {info['label']}")
        print("No connectivity checked. --probe-live may use credits and create synthetic remote data.")
        return 0
    red = False
    for name, check in [("senso", check_senso), ("openrouter", check_openrouter), ("cognee", check_cognee)]:
        try:
            state, message = check()
        except clients.ApiError:
            state, message, red = "RED", "probe failed; no live execution claim", True
        print(f"{name:11s} {state:5s} {message}")
    print("gate        LOCAL measured deterministic replay checks")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
