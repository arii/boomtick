#!/usr/bin/env python3
"""
repair.py - Agentic CI Repair via Orchestrator
Part of the Tech-Dancer 'Self-Healing' CI pipeline.
"""

import os
import sys
import json
import re

from tdw_services.orchestrator import Orchestrator
from dev_tools.utils import extract_failing_info

MAX_RETRIES = 3

def log(msg):
    print(f"🤖 [Repair Agent] {msg}")

def parse_eslint_json(json_path: str) -> list:
    if not os.path.exists(json_path):
        return []
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        findings = []
        for file_entry in data:
            file_path = file_entry['filePath']
            if file_path.startswith(os.getcwd()):
                file_path = os.path.relpath(file_path, os.getcwd())

            for msg in file_entry.get('messages', []):
                if msg.get('severity') >= 2: # Error
                    findings.append({
                        "file": file_path,
                        "line": msg.get('line'),
                        "message": f"{msg.get('message')} ({msg.get('ruleId')})",
                        "type": "eslint"
                    })
        return findings
    except:
        return []

def agent_loop(file_path, initial_errors):
    current_errors = initial_errors
    orch = Orchestrator()

    for attempt in range(MAX_RETRIES):
        log(f"Attempt {attempt + 1} for {file_path}")

        success = orch.repair_ci(file_path, current_errors)
        if not success:
            log(f"Failed to apply fix for {file_path}")
            break

        import subprocess
        res = subprocess.run(["pnpm", "run", "type-check"], capture_output=True, text=True)
        new_findings = extract_failing_info(res.stdout + res.stderr)
        new_errors = [f["message"] for f in new_findings if f["file"] == file_path]

        if not new_errors:
            log(f"✅ Fixed all identified errors in {file_path}")
            return True
        else:
            log(f"⚠️ Still has {len(new_errors)} errors in {file_path}. Retrying...")
            current_errors = new_errors

    return False

def main():
    json_findings = []
    if "--eslint-json" in sys.argv:
        idx = sys.argv.index("--eslint-json")
        json_findings = parse_eslint_json(sys.argv[idx+1])

    logs = sys.stdin.read() if "--stdin" in sys.argv else ""
    if not logs and len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], "r") as f:
            logs = f.read()

    findings = json_findings + extract_failing_info(logs)

    if not findings:
        log("No actionable errors found.")
        sys.exit(0)

    files_to_fix = {}
    for f in findings:
        if f["file"] not in files_to_fix:
            files_to_fix[f["file"]] = []
        files_to_fix[f["file"]].append(f["message"])

    for file_path, errors in files_to_fix.items():
        if not os.path.exists(file_path):
            continue
        agent_loop(file_path, errors)

if __name__ == "__main__":
    main()
