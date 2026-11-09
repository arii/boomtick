"""GitHub review, audit-gate, and token commands."""

import os
import re
import click
from dev_tools.commands.core import _handle_gate
from dev_tools.commands.core import err
from dev_tools.commands.core import get_config
from dev_tools.commands.core import json_option
from dev_tools.commands.core import limit_option
from dev_tools.commands.core import out
from dev_tools.commands.gh_pr import gh


@gh.command()
@click.option(
    "--check-dirs",
    default=None,
    help="Comma-separated list of directories to audit",
)
@click.pass_context
def audit(ctx, check_dirs):
    """Run a headless UI audit on the codebase."""
    if check_dirs is None:
        check_dirs = os.environ.get("AUDIT_CHECK_DIRS") or ",".join(
            get_config().audit_check_dirs
        )
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.get_audit_results(targets=check_dirs.split(","))
    out(ctx, "Headless audit complete.", data=res)


@gh.command()
@json_option
@click.argument("pr_number_arg", required=False, type=int)
@click.option(
    "--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to audit."
)
@click.option("--fetch", is_flag=True)
@click.option("--audit", "run_audit", is_flag=True)
@click.option("--submit", is_flag=True)
@click.option("--cleanup", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@click.option("--base")
@click.option("--event")
@click.pass_context
def audit_pr(
    ctx,
    pr_number_arg,
    pr_number_opt,
    fetch,
    run_audit,
    submit,
    cleanup,
    dry_run,
    base,
    event,
):
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.audit_pr(
        pr_number,
        fetch=fetch,
        audit=run_audit,
        submit=submit,
        cleanup=cleanup,
        dry_run=dry_run,
        event=event,
    )
    out(ctx, f"✅ Audit PR #{pr_number} action complete.", data=res)


@gh.command()
@click.option("--find")
@click.option("--migrate", nargs=2, type=str)
@click.option("--dry-run/--execute", default=True)
@click.pass_context
def migrate_tokens(ctx, find, migrate, dry_run):
    orch = ctx.obj["ORCHESTRATOR"]
    matches = orch.migrate_tokens(find=find, migrate=migrate, dry_run=dry_run)
    out(ctx, f"Found {len(matches)} matches.", data={"matches": matches})


@gh.command()
@click.option("--check-responses", is_flag=True)
@click.option("--cleanup-comments", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@limit_option(help_text="Limit the number of PRs to process")
@click.pass_context
def manage_reviews(ctx, check_responses, cleanup_comments, dry_run, limit):
    orch = ctx.obj["ORCHESTRATOR"]
    prs = orch.manage_reviews(
        check_responses=check_responses,
        cleanup_comments=cleanup_comments,
        dry_run=dry_run,
        limit=limit,
    )
    out(ctx, f"Checked {len(prs)} PRs.", data={"prs": prs})


@gh.command()
@click.pass_context
def audit_gate(ctx):
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.handle_audit_gate()
        if not res or "status" not in res:
            err(ctx, "Audit gate returned invalid or empty result.")
            return
        _handle_gate(ctx, res, "UI Anti-Pattern Audit")
    except Exception as e:
        err(ctx, f"Error processing audit gate: {e}")


@gh.command()
@click.option(
    "--pr", "--pr-number", "pr", required=True, type=int, help="The PR number."
)
@click.option("--status", required=True)
@click.option("--auditor", required=True)
@click.option("--dry-run/--execute", default=True)
@click.pass_context
def track_review(ctx, pr, status, auditor, dry_run):
    # Validate untrusted user input status and auditor
    if not re.match(r"^[a-zA-Z0-9_\-\s]+$", status):
        err(ctx, "Invalid status format.")
        return
    if not re.match(r"^[a-zA-Z0-9_\-]+$", auditor):
        err(ctx, "Invalid auditor format.")
        return

    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.track_review(pr, status, auditor, dry_run=dry_run)
        out(ctx, f"✅ Updated tracking for PR #{pr}", data=res)
    except Exception as e:
        err(ctx, f"Error updating tracking for PR #{pr}: {e}")


@gh.command()
@click.option("--baseline-file")
@click.option("--update", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@click.pass_context
def ratchet_any(ctx, baseline_file, update, dry_run):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.ratchet_any(update=update, baseline_file=baseline_file, dry_run=dry_run)
    _handle_gate(ctx, res, "TypeScript 'any' Ratchet")


@gh.command()
@click.option("--baseline-file")
@click.option("--threshold", type=int, default=50)
@click.option("--update", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@click.pass_context
def bundle_size(ctx, baseline_file, threshold, update, dry_run):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.check_bundle_size(
        update=update, baseline_file=baseline_file, threshold=threshold, dry_run=dry_run
    )
    _handle_gate(ctx, res, "Bundle Size Check")
