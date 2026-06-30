from __future__ import annotations

import argparse
import json

from .config import load_project_config
from .orchestrator import Orchestrator


def pr_number(value: str) -> int:
    """Validate that the PR number is a positive integer."""
    try:
        pr_id = int(value)
        if pr_id <= 0:
            raise ValueError
        return pr_id
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid PR number: {value}. Must be a positive integer.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="td-sdk-cli", description="Dev Tools SDK CLI")
    root = parser.add_subparsers(dest="group", required=True)

    gh_parser = root.add_parser("gh", help="GitHub operations")
    gh_subparsers = gh_parser.add_subparsers(dest="command", required=True)
    gh_view = gh_subparsers.add_parser("view", help="Display PR summary")
    gh_view.add_argument("pr", type=pr_number)
    gh_resolve = gh_subparsers.add_parser("resolve", help="Attempt conflict resolution")
    gh_resolve.add_argument("pr", type=pr_number)
    gh_resolve.add_argument("--execute", action="store_true", help="Apply non-dry-run behavior")
    gh_audit = gh_subparsers.add_parser("audit", help="Run audit-focused review")
    gh_audit.add_argument("pr", type=pr_number)

    ai_parser = root.add_parser("ai", help="AI operations")
    ai_subparsers = ai_parser.add_subparsers(dest="command", required=True)
    ai_review = ai_subparsers.add_parser("review", help="Run local-first AI review")
    ai_review.add_argument("pr", type=pr_number)
    ai_analyze = ai_subparsers.add_parser("analyze", help="Analyze a file path")
    ai_analyze.add_argument("path")

    agent_parser = root.add_parser("agent", aliases=["jules"], help="Agent operations")
    agent_subparsers = agent_parser.add_subparsers(dest="command", required=True)
    agent_dispatch = agent_subparsers.add_parser("dispatch", help="Dispatch review task")
    agent_dispatch.add_argument("pr", type=pr_number)
    agent_subparsers.add_parser("sync", help="Sync active agent sessions")

    env = root.add_parser("env", help="Environment checks")
    env_sub = env.add_subparsers(dest="command", required=True)
    env_sub.add_parser("verify", help="Verify runtime integrations")

    root.add_parser("repair", help="Run local repair triage")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    orchestrator = Orchestrator(load_project_config())

    if args.group == "gh" and args.command == "view":
        print(json.dumps(orchestrator.view_pr(args.pr), indent=2))
        return 0
    if args.group == "gh" and args.command == "resolve":
        print(orchestrator.resolve_pr(args.pr, dry_run=not args.execute))
        return 0
    if args.group == "gh" and args.command == "audit":
        print(json.dumps(orchestrator.audit_pr(args.pr), indent=2))
        return 0

    if args.group == "ai" and args.command == "review":
        result = orchestrator.review_pr(args.pr)
        print(f"engine={result.engine}")
        print(result.output)
        return 0
    if args.group == "ai" and args.command == "analyze":
        print(orchestrator.analyze_file(args.path))
        return 0

    if args.group in ("agent", "jules") and args.command == "dispatch":
        status = orchestrator.dispatch_jules_review(args.pr)
        print(f"status={status}")
        return 0
    if args.group in ("agent", "jules") and args.command == "sync":
        print(json.dumps(orchestrator.sync_jules(), indent=2))
        return 0

    if args.group == "env" and args.command == "verify":
        print(json.dumps(orchestrator.env_verify(), indent=2))
        return 0

    if args.group == "repair":
        print(orchestrator.repair_local_state())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
