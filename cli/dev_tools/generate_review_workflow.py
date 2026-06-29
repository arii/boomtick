#!/usr/bin/env python3
import argparse
import sys
import os
from tdw_services.orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="Generate deterministic review workflow plan.")
    parser.add_argument("--pr", required=True, type=int, help="Pull Request number")
    parser.add_argument("--issue", required=False, type=int, help="Issue number")
    args = parser.parse_args()

    orch = Orchestrator()
    try:
        res = orch.generate_review_workflow(args.pr, args.issue)
        print(f"Workflow plan generated: {res['plan_path']}")
    except Exception as e:
        print(f"Error generating workflow plan: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
