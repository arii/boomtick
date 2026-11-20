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
    if config.mode("senso") != "live":
        return "OFF", "not enabled (PROOFLOOP_LIVE_SERVICES=senso and SENSO_API_KEY)"
    result = clients.SensoLive().health()
    if result["status"] != 200:
        raise clients.ApiError(result["status"], "health request not successful")
    return "GREEN", "GET /org/me succeeded (does not prove ingest/search)"


def check_llm():
    backend = config.llm_backend()
    if backend is None:
        return "OFF", "not enabled (twt needs PROOFLOOP_LIVE_SERVICES=twt; openrouter needs llm + key)"
    clients.llm_chat("Reply with the word ok.", max_tokens=16)
    return "GREEN", f"one completion via {backend} succeeded (not proof of replay quality)"


def check_cognee():
    if config.mode("cognee") != "live":
        return "OFF", "not enabled (PROOFLOOP_LIVE_SERVICES=cognee, COGNEE_API_URL, COGNEE_API_KEY)"
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
    for name, check in [("senso", check_senso), ("llm", check_llm), ("cognee", check_cognee)]:
        try:
            state, message = check()
        except clients.ApiError:
            state, message, red = "RED", "probe failed; no live execution claim", True
        print(f"{name:11s} {state:5s} {message}")
    print("gate        LOCAL scores real LLM answers on replay tasks (needs llm)")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
