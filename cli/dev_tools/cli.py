"""Unified Tech-Dancer DevTools CLI (thin aggregator)."""
import json
import sys
from dev_tools.config import get_config
from dev_tools.utils import log_error
from dev_tools.commands import (ai_agent, gates_audit, gates_spec, gh_issue, gh_pr, gh_review, mcp_repo, ops, sessions)
from dev_tools.commands.core import (LazyOrchestrator, cli, err, json_option, limit_option, out)
from dev_tools.commands.gates_audit import _prune_walk_dirs
__all__ = ["LazyOrchestrator", "PROJECT_CONFIG", "_prune_walk_dirs", "ai_agent", "cli", "err", "gates_audit", "gates_spec", "get_config", "gh_issue", "gh_pr", "gh_review", "json_option", "limit_option", "main", "mcp_repo", "ops", "out", "sessions"]


def __getattr__(name: str):
    if name == "PROJECT_CONFIG":
        return get_config()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def main():
    # click entry point automatically handles sys.argv
    try:
        cli.main(obj={})
    except Exception as e:
        # If we are in JSON mode, we should ideally output JSON error.
        # Detecting JSON mode from sys.argv since click context isn't available here yet if it failed early.
        # Note: {get_config().cli_alias} subcommands are JSON by default.
        is_json = "--no-json" not in sys.argv

        if is_json:
            error_payload = {"status": "error", "message": str(e), "type": e.__class__.__name__}
            # CLIError and some others might have a custom 'code' attribute
            code = getattr(e, "code", 1)
            error_payload["code"] = code
            # JSON errors remain on stdout to maintain the contract for piped machine consumers
            # (e.g. boomtick-mcp) which may discard stderr via 2>/dev/null.
            print(json.dumps(error_payload, indent=2))
        else:
            log_error(str(e))
            code = getattr(e, "code", 1)

        sys.exit(code)


if __name__ == "__main__":
    main()
