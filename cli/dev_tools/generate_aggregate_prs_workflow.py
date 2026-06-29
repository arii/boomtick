#!/usr/bin/env python3
import sys
import os
from tdw_services.orchestrator import Orchestrator

def main():
    orch = Orchestrator()
    try:
        res = orch.generate_aggregate_prs_workflow()
        print(f"Workflow plan generated: {res['plan_path']}")
    except Exception as e:
        print(f"Error generating workflow plan: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
