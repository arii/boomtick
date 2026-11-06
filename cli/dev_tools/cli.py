# pylint: disable=f-string-without-interpolation,function-redefined,import-outside-toplevel,line-too-long,missing-docstring,no-value-for-parameter,protected-access,redefined-outer-name,subprocess-run-check,too-many-arguments,too-many-lines,too-many-locals,too-many-positional-arguments,unused-argument,use-dict-literal
import glob
import json
import os
import subprocess
import sys
import tempfile
import importlib.util
import re
from pathlib import Path
from dataclasses import asdict

import click
from dev_tools.config import get_config
from dev_tools.utils import (
    CLIError,
    get_or_create_log_dir,
    log_error,
    log_info,
    log_warn,
    mask_sensitive_data,
    run_command,
    verify_ci_metrics,
)
from dev_tools.multi_repo import (
    discover_ecosystem_repos,
    exec_in_repos,
    get_repo_summary,
    warm_ecosystem_context,
)


class LazyOrchestrator:
    """Lazy proxy for the Orchestrator to defer heavy imports and initialization."""

    def __init__(self, factory):
        # Use super().__setattr__ to avoid recursion during initialization
        super().__setattr__("_factory", factory)
        super().__setattr__("_instance", None)

    def _get_instance(self):
        if self._instance is None:
            super().__setattr__("_instance", self._factory())
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_instance(), name)

    def __setattr__(self, name, value):
        if name in ("_instance", "_factory"):
            super().__setattr__(name, value)
        else:
            setattr(self._get_instance(), name, value)

    def __dir__(self):
        return dir(self._get_instance())


DEFAULT_GH_API_LIMIT = 10


def __getattr__(name: str):
    if name == "PROJECT_CONFIG":
        return get_config()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def limit_option(default_val=DEFAULT_GH_API_LIMIT, help_text="Limit the number of items to process"):
    def decorator(f):
        return click.option("--limit", type=int, default=default_val, help=help_text)(f)

    return decorator


def json_option(f):
    """
    Decorator to add --json option to subcommands.
    Allows --json to be placed after the command (e.g., 'td command --json').
    Automatically updates ctx.obj['JSON'] if the option is provided.
    """
    import functools

    f = click.option("--json/--no-json", "json_output", default=None, help="Output results in JSON format")(f)

    @click.pass_context
    @functools.wraps(f)
    def wrapper(ctx, *args, **kwargs):
        json_output = kwargs.pop("json_output", None)
        if json_output is not None and ctx.obj is not None:
            ctx.obj["JSON"] = json_output
        return ctx.invoke(f, *args, **kwargs)

    return wrapper


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], ignore_unknown_options=True, allow_extra_args=True)

# CLI Group


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("--json/--no-json", "json_output", default=True, help="Output results in JSON format")
@click.option("--no-cache", is_flag=True, default=False, help="Bypass the disk cache for GitHub API calls")
@click.pass_context
def cli(ctx, json_output, no_cache):
    """Unified Tech-Dancer DevTools CLI"""
    ctx.ensure_object(dict)

    # If the user explicitly passed --no-json (if supported) or we want to detect if it's a TTY
    # But for now, we follow the requirement to be JSON by default for machine consumption.
    ctx.obj["JSON"] = json_output
    ctx.obj["NO_CACHE"] = no_cache

    def orchestrator_factory():
        from dev_tools.orchestrator import Orchestrator

        return Orchestrator(no_cache=no_cache)

    ctx.obj["ORCHESTRATOR"] = LazyOrchestrator(orchestrator_factory)


# --- Utility Helpers ---


def out(ctx, msg, data=None):
    if ctx.obj["JSON"]:
        payload = {"status": "success"}
        if data:
            payload.update(data)
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(msg)


def err(ctx, msg, code=1, data=None):
    # Ensure sensitive data is masked in the error message
    masked_msg = mask_sensitive_data(msg)
    if ctx.obj["JSON"]:
        payload = {"status": "error", "message": masked_msg, "code": code}
        if data:
            payload.update({"data": data})
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(f"❌ Error: {masked_msg}", err=True)
    sys.exit(code)


def _handle_unexpected_error(ctx, command_name, error):
    """Centralized error handling for unexpected exceptions."""
    message = f"Unexpected error in {command_name}: {str(error)}"
    err(ctx, message, code=1)



def _gate_json_option(func):
    """Per-command --json/--no-json passthrough (group flag is global)."""
    import click as _click

    @_click.option("--json/--no-json", "json_output", default=None,
                   help="Override JSON output for this command")
    @_click.pass_context
    def wrapper(ctx, json_output, *args, **kwargs):
        if json_output is not None:
            ctx.obj["JSON"] = json_output
        return ctx.invoke(func, *args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def _get_body_content(ctx, orch, file, body):
    if file and body:
        err(ctx, "Provide --file or --body, not both")
    if not file and not body:
        err(ctx, "Provide either --file or --body")

    content = body if body is not None else (orch._read_safe_file(file) if file else None)
    if content is None:
        err(ctx, "Provide --file or --body")
    return content


# ==========================================
# MCP COMMAND GROUP
# ==========================================


@cli.group()
def mcp():
    """MCP Discovery and Server Operations"""


@mcp.command(name="install")
@click.option("--host", "-h", "hosts", multiple=True, help="Target specific host (antigravity, claude, cursor, codex)")
@click.option("--path", "custom_path", help="Custom path to host settings JSON file")
@click.option("--command", "mcp_command", default="boomtick-mcp", help="Command to run MCP server")
@click.option("--dry-run/--execute", default=True, help="Preview changes without updating files")
@click.pass_context
def mcp_install(ctx, hosts, custom_path, mcp_command, dry_run):
    """Detect agent host environments and register boomtick-mcp."""
    from dev_tools.handlers.mcp_installer import detect_and_install_mcp

    target_config = {"command": mcp_command}
    host_list = list(hosts) if hosts else None
    res = detect_and_install_mcp(
        hosts=host_list,
        dry_run=dry_run,
        target_config=target_config,
        custom_path=custom_path,
    )

    if not ctx.obj.get("JSON", False):
        click.echo(f"MCP Installation ({'Dry Run' if dry_run else 'Executed'}):")
        for r in res.get("results", []):
            click.echo(f"  • {r['path']}: {r['status']} - {r['message']}")

    out(ctx, "MCP registration check complete.", data=res)


@mcp.command(name="setup")
@click.option("--host", "-h", "hosts", multiple=True, help="Target specific host (antigravity, claude, cursor, codex)")
@click.option("--path", "custom_path", help="Custom path to host settings JSON file")
@click.option("--command", "mcp_command", default="boomtick-mcp", help="Command to run MCP server")
@click.option("--dry-run/--execute", default=True, help="Preview changes without updating files")
@click.pass_context
def mcp_setup(ctx, hosts, custom_path, mcp_command, dry_run):
    """Alias for 'td mcp install'."""
    ctx.invoke(mcp_install, hosts=hosts, custom_path=custom_path, mcp_command=mcp_command, dry_run=dry_run)


# ==========================================
# CONFIG COMMAND GROUP
# ==========================================


@cli.group()
def config():
    """Configuration Operations"""


@config.command(name="view")
@json_option
@click.pass_context
def config_view(ctx):
    """View the current project configuration as JSON."""
    # ctx.obj might be None if the command is called directly or during unit tests
    is_json = ctx.obj.get("JSON", True) if ctx.obj is not None else True

    try:
        conf = get_config()
        if is_json:
            click.echo(json.dumps(asdict(conf), indent=2))
        else:
            click.echo("Current configuration:")
            click.echo(json.dumps(asdict(conf), indent=2))
    except (ValueError, CLIError) as e:
        err(ctx, str(e))


# ==========================================
# REPO COMMAND GROUP
# ==========================================


@cli.group()
def repo():
    """Repository Operations"""


@repo.command()
@click.option("--grep")
@click.option("--worktree")
@click.pass_context
def run_playwright(ctx, grep, worktree):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_playwright(grep=grep, worktree_path=worktree)
    out(ctx, f"Playwright run complete.", data=res)


@repo.command()
@click.argument("pr_number", type=int)
@click.option("--all", "include_all", is_flag=True, help="Include logs for successful runs")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def ci_logs(ctx, pr_number, include_all, repo):
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.get_ci_logs(pr_number, include_all=include_all, **extra_kwargs)
    out(ctx, f"Fetched CI logs for PR #{pr_number}", data=res)


@repo.command()
@click.argument("pr_number", type=int)
@click.option("--grep", help="Filter logs by pattern")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def logs(ctx, pr_number, grep, repo):
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    logs_content = orch.stream_ci_logs(pr_number, grep=grep, **extra_kwargs)
    out(ctx, f"Fetched logs for PR #{pr_number}", data={"logs": logs_content})


@repo.command(name="workflow-runs")
@click.option("--branch", help="Filter by branch")
@click.option("--event", help="Filter by event (e.g. push, pull_request)")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def workflow_runs(ctx, branch, event, repo):
    """List recent GitHub Actions workflow runs."""
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    runs = orch.github.fetch_workflow_runs(branch=branch, event=event, **extra_kwargs)
    out(ctx, f"Fetched {len(runs)} workflow runs.", data={"workflow_runs": runs})


@repo.command()
@click.argument("filepath")
@click.option("--patch-file")
@click.option("--patch-body")
@click.pass_context
def apply_patch(ctx, filepath, patch_file, patch_body):
    """Apply a patch to a file using resilient git apply."""
    from dev_tools.utils import apply_patch as _apply
    from dev_tools.utils import sanitize_path

    orch = ctx.obj["ORCHESTRATOR"]

    # Security: sanitize inputs
    filepath = sanitize_path(filepath)
    if not filepath:
        err(ctx, "Invalid filepath provided.")
        return  # Explicit return for security

    content = patch_body
    if patch_file:
        safe_patch_path = sanitize_path(patch_file)
        if not safe_patch_path:
            err(ctx, "Invalid patch-file path provided.")
            return  # Explicit return for security
        try:
            # Use Orchestrator helper for safe file reading
            content = orch._read_safe_file(safe_patch_path)
        except Exception as e:
            err(ctx, f"Failed to read patch file: {str(e)}")

    if not content:
        err(ctx, "Provide either --patch-file or --patch-body")
        return  # Explicit return for security

    # Basic diff format validation
    if not any(marker in content for marker in ["--- ", "+++ ", "@@ "]):
        err(ctx, "Invalid patch format. Content does not appear to be a unified diff.")
        return

    try:
        _apply(filepath, content)
        out(ctx, f"✅ Applied patch to {filepath}")
    except Exception as e:
        err(ctx, f"Failed to apply patch: {str(e)}")


# ==========================================
# GH COMMAND GROUP
# ==========================================


@cli.group()
def gh():
    """GitHub Operations"""


@gh.command()
@json_option
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open")
@limit_option(help_text="Limit the number of PRs to process")
@click.option("--include-drafts/--no-include-drafts", default=True)
@click.option("--labels")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def search_prs(ctx, state, limit, include_drafts, labels, repo):
    orch = ctx.obj["ORCHESTRATOR"]
    label_list = [l.strip() for l in labels.split(",")] if labels else None
    extra_kwargs = {"repo": repo} if repo else {}

    res = orch.list_prs(state=state, limit=limit, includeDrafts=include_drafts, labels=label_list, **extra_kwargs)
    out(ctx, f"Found {len(res['prs'])} PRs.", data=res)


@gh.command(name="search-issues")
@json_option
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open")
@limit_option(help_text="Limit the number of issues to process")
@click.option("--labels")
@click.pass_context
def search_issues(ctx, state, limit, labels):
    """Search for GitHub issues (excluding pull requests) in the repository."""
    orch = ctx.obj["ORCHESTRATOR"]
    label_list = [l.strip() for l in labels.split(",")] if labels else None

    res = orch.list_issues(state=state, limit=limit, labels=label_list)
    out(ctx, f"Found {len(res['issues'])} issues.", data=res)


@gh.command()
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to check merge conflicts for.")
@click.option("--base", default=None, help="Base branch (defaults to configured base branch)")
@click.pass_context
def merge_conflicts(ctx, pr_number_arg, pr_number_opt, base):
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    if base is None:
        base = get_config().base_branch_name
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.get_merge_conflicts(pr_number, base_branch=base)
    out(ctx, f"Checked merge conflicts for PR #{pr_number}", data=res)


@gh.command()
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to sync.")
@click.pass_context
def sync_pr(ctx, pr_number_arg, pr_number_opt):
    """Reliably pull the latest remote PR state to local, overwriting messy rebases."""
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.sync_pr(pr_number)
    out(ctx, res["message"], data=res)


@gh.command()
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to fetch diff for.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def pr_diff(ctx, pr_number_arg, pr_number_opt, repo):
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.get_pr_diff_shapen(pr_number, **extra_kwargs)
    out(ctx, f"Fetched diff for PR #{pr_number}", data=res)


@gh.command()
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to view.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def view(ctx, pr_number_arg, pr_number_opt, repo):
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    pr = orch.github.fetch_pr_details(pr_number, **extra_kwargs)
    # Normalize for tool consumption
    normalized_pr = {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "headRefName": pr.get("head", {}).get("ref"),
        "baseRefName": pr.get("base", {}).get("ref"),
        "html_url": pr.get("html_url"),
    }
    out(
        ctx,
        f"PR #{normalized_pr['number']}: {normalized_pr['title']}\nState: {normalized_pr['state']}",
        data={"pr": normalized_pr},
    )


@gh.command()
@click.argument("file", required=False)
@click.option("--base")
@click.option(
    "--strategy",
    type=click.Choice(["ours", "theirs", "union"]),
    help="Deterministic resolution strategy (ours, theirs, or union).",
)
@click.pass_context
def resolve(ctx, file, base, strategy):
    orch = ctx.obj["ORCHESTRATOR"]
    if file:
        if orch.resolve_conflict(file, strategy=strategy):
            out(ctx, f"✅ Resolved conflicts in {file}", data={"resolved_file": file})
        else:
            err(ctx, f"Failed to resolve conflicts in {file}")
    else:
        resolved = orch.resolve_conflicts_headless(strategy=strategy)
        out(ctx, f"✅ Resolved {len(resolved)} files.", data={"resolved": resolved})


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
        check_dirs = os.environ.get("AUDIT_CHECK_DIRS") or ",".join(get_config().audit_check_dirs)
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.get_audit_results(targets=check_dirs.split(","))
    out(ctx, "Headless audit complete.", data=res)


@gh.command()
@json_option
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to audit.")
@click.option("--fetch", is_flag=True)
@click.option("--audit", "run_audit", is_flag=True)
@click.option("--submit", is_flag=True)
@click.option("--cleanup", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@click.option("--base")
@click.option("--event")
@click.pass_context
def audit_pr(ctx, pr_number_arg, pr_number_opt, fetch, run_audit, submit, cleanup, dry_run, base, event):
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
@click.option("--title", required=True, help="Issue title")
@click.option("--file", help="Path to file containing issue body")
@click.option("--body", help="Literal body text")
@click.option("--repo", help="Target GitHub repository (e.g. owner/repo)")
@click.pass_context
def create_issue(ctx, title, file, body, repo):
    """Create a new GitHub issue."""
    orch = ctx.obj["ORCHESTRATOR"]

    content = _get_body_content(ctx, orch, file, body)
    res = orch.create_issue(title, content, repo=repo)
    out(ctx, f"✅ Successfully created issue: {res['issue'].get('html_url')}", data=res)


@gh.command()
@click.argument("issue_number_arg", required=False, type=int)
@click.option("--issue-number", "issue_number_opt", type=int, help="The GitHub issue number to view")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def issue_view(ctx, issue_number_arg, issue_number_opt, repo):
    """View details of a GitHub issue."""
    issue_number = issue_number_arg if issue_number_arg is not None else issue_number_opt
    if issue_number is None:
        err(ctx, "Provide --issue-number or a positional issue number")

    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    issue = orch.get_issue_details(issue_number, **extra_kwargs)
    msg = f"Issue #{issue.get('number')}: {issue.get('title')}\nState: {issue.get('state')}\n\n{issue.get('body')}"
    out(ctx, msg, data={"issue": issue})


@gh.command()
@click.argument("issue_number", type=int)
@click.option("--file", help="Path to file containing new issue body")
@click.option("--body", help="Literal body text")
@click.option("--labels", help="Comma-separated list of labels to set (replaces existing labels)")
@click.option("--add-labels", help="Comma-separated list of labels to add")
@click.option("--remove-labels", help="Comma-separated list of labels to remove")
@click.option("--state", type=click.Choice(["open", "closed"]))
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def issue_update(ctx, issue_number, file, body, labels, add_labels, remove_labels, state, repo):
    """Update a GitHub issue's body, labels, and/or state."""
    orch = ctx.obj["ORCHESTRATOR"]

    label_list = [l.strip() for l in labels.split(",")] if labels else None
    add_label_list = [l.strip() for l in add_labels.split(",")] if add_labels else None
    remove_label_list = [l.strip() for l in remove_labels.split(",")] if remove_labels else None

    content = None
    if file or body:
        content = _get_body_content(ctx, orch, file, body)

    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.update_issue(
        issueNumber=issue_number,
        body=content,
        labels=label_list,
        addLabels=add_label_list,
        removeLabels=remove_label_list,
        state=state,
        **extra_kwargs,
    )
    out(ctx, f"✅ Successfully updated issue #{issue_number}", data=res)


@gh.command()
@click.argument("issue_number", type=int)
@click.option("--file", help="Path to file containing comment body")
@click.option("--body", help="Literal body text")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def issue_comment(ctx, issue_number, file, body, repo):
    """Post a comment to a GitHub issue."""
    orch = ctx.obj["ORCHESTRATOR"]
    content = _get_body_content(ctx, orch, file, body)
    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.post_comment(issue_number, content, **extra_kwargs)
    out(ctx, f"✅ Successfully posted comment to issue #{issue_number}", data={"comment": res})


@gh.command()
@click.option("--issue-number", type=int)
@click.option("--all-open", is_flag=True)
@click.option("--post-comments", is_flag=True)
@click.option("--dry-run/--execute", default=True)
@click.option("--file", default=None, help="Path to local issue draft to validate")
@click.pass_context
def validate_issue(ctx, issue_number, all_open, post_comments, dry_run, file=None):
    orch = ctx.obj["ORCHESTRATOR"]

    if file:
        content = orch._read_safe_file(file)
        # For local files, we use title 'Draft: Local' to satisfy frontmatter check
        res_content = orch.validate_content("Draft: Local", content)
        res = {
            "status": "success" if not res_content["findings"] else "error",
            "issues": [
                {
                    "number": 0,
                    "title": file,
                    "findings": res_content["findings"],
                    "warnings": res_content["warnings"],
                }
            ],
            "total_findings": len(res_content["findings"]),
        }
    else:
        res = orch.validate_issue(
            issue_number=issue_number, all_open=all_open, post_comments=post_comments, dry_run=dry_run
        )

    if not ctx.obj["JSON"]:
        for issue in res["issues"]:
            issue_ref = f"#{issue['number']}" if issue["number"] else f"File: {issue['title']}"
            title_display = f": {issue['title'][:60]}" if issue["number"] else ""
            click.echo(f"{'✅' if not issue['findings'] else '❌'} {issue_ref}{title_display}")
            for f in issue["findings"]:
                click.echo(f"   ❌ {f}")
            for w in issue["warnings"]:
                click.echo(f"   ⚠️  {w}")
    if res["status"] == "error":
        err(ctx, f"Found {res['total_findings']} blocking findings.", data=res)
    else:
        out(ctx, "✅ Issue validation complete.", data=res)


@gh.command()
@click.option("--file", help="Path to write the generated markdown scaffold.")
@click.pass_context
def scaffold_issue(ctx, file):
    """Output a markdown skeleton containing the required headers."""
    sections = get_config().spec_sections

    output = "# Issue Title\n\n"
    for section in sections:
        output += f"# {section}\n\n[Provide content for {section}]\n\n"

    if file:
        with open(file, "w", encoding="utf-8") as f:
            f.write(output)
        click.echo(f"Scaffold successfully written to {file}")
        return

    if ctx.obj.get("JSON"):
        out(ctx, "Issue scaffold generated.", data={"template": output})
    else:
        click.echo(output)


@gh.command(name="spec-issue")
@click.argument("issue_number", type=int)
@click.option("--repo", "-r", default=None,
              help="Target GitHub repository (e.g. owner/repo)")
@click.option("--path", "root_path", default=None,
              help="Checkout for scope existence checks (default: git root)")
@click.option("--write/--no-write", default=False,
              help="Write the improved body back to the issue")
@click.pass_context
def spec_issue(ctx, issue_number, repo, root_path, write):
    """Rewrite an issue as an agent-implementable spec (exit 0 iff ready).

    Appends ## Agent scope (allowed files, scope-gate enforced) and
    ## Validation (detected gate commands). Chain with && to dispatch
    only issues that meet the bar.
    """
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import spec_issue as spec
    try:
        orch = ctx.obj["ORCHESTRATOR"]
        extra = {"repo": repo} if repo else {}
        details = orch.get_issue_details(issue_number, **extra)
        title = details.get("title", "")
        body = details.get("body") or ""
        root = ls.repo_root_for(root_path)
        improved, report = spec.render_body(title, body, root)
        if write:
            orch.update_issue(issueNumber=issue_number, body=improved,
                              **extra)
        if not ctx.obj["JSON"]:
            if report["ready"]:
                click.echo(f"issue #{issue_number} is agent-ready")
            else:
                click.echo(f"issue #{issue_number} NOT ready: "
                           f"missing headers {report['missing_headers']}, "
                           f"{len(report['scope'])} scope path(s)")
            if not write:
                click.echo("--- improved body ---")
                click.echo(improved)
        out(ctx, f"issue #{issue_number} ready: {report['ready']}.",
            data={"issue": issue_number, "wrote": write,
                  "body": improved, **report})
        if not report["ready"]:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "gh spec-issue", e)


@gh.command()
@click.option("--title", required=True)
@click.option("--body", required=True)
@click.option("--head", required=True)
@click.option("--base", default=None, help="Base branch")
@click.option("--draft", is_flag=True)
@click.option("--repo", help="Target repository override")
@click.pass_context
def create_pr(ctx, title, body, head, base, draft, repo):
    """Create a new pull request."""
    base = base or get_config().base_branch_name
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.create_pull_request(title, body, head, base, draft=draft, repo=repo)
    out(ctx, f"✅ Created PR: {res.get('html_url')}", data={"pr": res})


@gh.command()
@click.argument("branch")
@click.pass_context
def checkout(ctx, branch):
    """Checkout a branch."""
    run_command(["git", "checkout", branch])
    out(ctx, f"✅ Checked out branch {branch}")


@gh.command()
@click.argument("target_branch")
@click.argument("pr_numbers", nargs=-1, type=int)
@click.pass_context
def aggregate(ctx, target_branch, pr_numbers):
    """Aggregate multiple PRs into a single branch."""
    if not pr_numbers:
        err(ctx, "Provide at least one PR number to aggregate.")
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.aggregate_prs(target_branch, list(pr_numbers))
    out(ctx, res["message"], data=res)


def _render_conflicts(ctx, conflicts):
    if not ctx.obj["JSON"]:
        if not conflicts:
            click.echo("✅ No file overlap between open PRs detected.")
        for c in conflicts:
            prs_str = ' ↔ '.join(f'#{p}' for p in c['prs'])
            files_count = len(c['files'])
            click.echo(f"⚠️  {prs_str} share {files_count} file(s):")
            for f in sorted(c["files"])[:10]:
                click.echo(f"    - {f}")
    out(ctx, f"Found {len(conflicts)} file overlap group(s).", data={"conflicts": conflicts})


@gh.command()
@click.option("--pr", "--pr-number", "pr", required=True, type=int, help="The PR number to resolve conflicts for.")
@click.option("--allow-unrelated", is_flag=True, help="Allow merging unrelated histories.")
@click.option(
    "--strategy",
    type=click.Choice(["ours", "theirs"]),
    help="Merge strategy option (-X ours/theirs).",
)
@click.option("--push", is_flag=True, help="Automatically push the resolution to origin.")
@click.option(
    "--continue",
    "continue_resolve",
    is_flag=True,
    help="Finalize and push an in-progress conflict resolution.",
)
@click.pass_context
def resolve_conflicts(ctx, pr, allow_unrelated, strategy, push, continue_resolve):
    """Resolve merge conflicts for a PR in a separate worktree."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.resolve_pr_conflicts(
            pr,
            allow_unrelated=allow_unrelated,
            strategy=strategy,
            push=push,
            continue_resolve=continue_resolve,
        )
        out(ctx, res["message"], data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)


@gh.command()
@click.argument("diff_input", required=False)
@click.pass_context
def verify_versions(ctx, diff_input):
    """Verify version changes in a diff for downgrades or hard blocks."""
    from dev_tools.utils import resolve_resource_path

    try:
        script_path = resolve_resource_path("verify_versions.py")
    except FileNotFoundError:
        # Absolute fallback if packaging failed
        script_path = os.path.join(os.path.dirname(__file__), "verify_versions.py")

    if not diff_input:
        # If no input provided, try to get diff against main
        try:
            diff_input = run_command(["git", "diff", get_config().base_branch])
        except Exception as e:
            _handle_unexpected_error(ctx, "check-diff", e)

    # Use a temporary file to avoid E2BIG/ARG_MAX issues with large diffs
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
        tmp.write(diff_input)
        tmp_path = tmp.name

    cmd = [sys.executable, script_path, tmp_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        os.unlink(tmp_path)
        if proc.stdout:
            try:
                findings = json.loads(proc.stdout)
                if findings:
                    status = "error" if any(f["severity"] == "error" for f in findings) else "success"
                    out(
                        ctx,
                        f"Found {len(findings)} version issues.",
                        data={"status": status, "findings": findings},
                    )
                    if status == "error":
                        sys.exit(1)
                else:
                    out(
                        ctx,
                        "✅ No version issues detected.",
                        data={"status": "success", "findings": []},
                    )
            except json.JSONDecodeError:
                err(ctx, f"Invalid validator output: {proc.stdout}")
        else:
            err(ctx, f"Validator failed: {proc.stderr}")
    except Exception as e:
        _handle_unexpected_error(ctx, "verify-versions", e)


@gh.command()
@click.option("--pr", "--pr-number", "pr", type=int, help="PR number to detect file overlap for")
@click.option("--all", "all_prs", is_flag=True, help="Detect file overlap for all open PRs")
@click.pass_context
def detect_conflicts(ctx, pr, all_prs):
    """Detect file overlap between open PRs (shared touched paths). This is NOT merge-conflict detection — for mergeability use GitHub mergeStateStatus/mergeable."""
    if pr is not None and all_prs:
        err(ctx, "Provide either --pr or --all, not both")
    if pr is None and not all_prs:
        click.echo("💡 Suggestion: Use 'td gh detect-conflicts --all' to explicitly scan all open PRs.", err=True)
        all_prs = True
    orch = ctx.obj["ORCHESTRATOR"]
    conflicts = orch.handle_detect_conflicts(pr_num=pr, all_prs=all_prs)
    _render_conflicts(ctx, conflicts)


@gh.command()
@click.option("--body", help="The comment body text.")
@click.option("--author-association", required=True, help="The author association (e.g. OWNER, MEMBER).")
@click.pass_context
def parse_comment(ctx, body, author_association):
    """Parse a comment body and return intended actions."""
    orch = ctx.obj["ORCHESTRATOR"]
    # Security: Allow reading body from COMMENT_BODY env var to avoid shell injection in CI
    content = body if body else os.environ.get("COMMENT_BODY")
    if not content:
        err(ctx, "Comment body is required (use --body or COMMENT_BODY env var)")

    actions = orch.parse_comment(content, author_association)
    out(ctx, "Comment parsed successfully.", data={"actions": actions})


@gh.command()
@click.option("--pr", "--pr-number", "pr", required=True, type=int, help="The PR number to comment on.")
@click.option("--file", type=str, help="Path to the file containing the comment body.")
@click.option("--body", type=str, help="Literal comment text.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def post_comment(ctx, pr, file, body, repo=None):
    """Post a comment to a PR."""
    orch = ctx.obj["ORCHESTRATOR"]
    content = _get_body_content(ctx, orch, file, body)
    res = orch.post_comment(pr, content, repo=repo)
    out(ctx, f"✅ Successfully posted comment to PR #{pr}", data=res)


@gh.command(name="read-pr-reviews")
@click.option("--pr", "--pr-number", "pr_number", required=True, type=int, help="The PR number to fetch top-level reviews for.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def read_pr_reviews(ctx, pr_number, repo):
    """Fetch top-level reviews for a PR."""
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    reviews = orch.github.fetch_reviews(pr_number, **extra_kwargs)
    out(ctx, f"Fetched {len(reviews)} reviews for PR #{pr_number}", data={"reviews": reviews, "review_count": len(reviews)})


@gh.command(name="list-pr-commits")
@click.option("--pr", "--pr-number", "pr_number", required=True, type=int, help="The PR number to list commits for.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def list_pr_commits(ctx, pr_number, repo):
    """List commits for a PR."""
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    raw_commits = orch.github.fetch_pr_commits(pr_number, **extra_kwargs)
    commits = [
        {
            "sha": c.get("sha"),
            "author": c.get("commit", {}).get("author", {}).get("name") or c.get("author", {}).get("login"),
            "date": c.get("commit", {}).get("author", {}).get("date"),
            "message": c.get("commit", {}).get("message"),
        }
        for c in raw_commits
    ] if isinstance(raw_commits, list) else []
    out(ctx, f"Fetched {len(commits)} commits for PR #{pr_number}", data={"commits": commits})


@gh.command(name="pr-view")
@click.argument("pr_number_arg", required=False, type=int)
@click.option("--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to fetch state for.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def pr_view(ctx, pr_number_arg, pr_number_opt, repo):
    """Fetch a single PR state snapshot (state, draft, reviews, checks, mergeable)."""
    pr_number = pr_number_arg if pr_number_arg is not None else pr_number_opt
    if pr_number is None:
        err(ctx, "Provide --pr/--pr-number or a positional PR number")
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.get_pr_view_shapen(pr_number, **extra_kwargs)
    out(ctx, f"Fetched state for PR #{pr_number}", data=res)


@gh.command(name="run-jobs")
@click.argument("run_id_arg", required=False, type=int)
@click.option("--run", "--run-id", "run_id_opt", type=int, help="The workflow run ID to list jobs for.")
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def run_jobs(ctx, run_id_arg, run_id_opt, repo):
    """List jobs for a workflow run."""
    run_id = run_id_arg if run_id_arg is not None else run_id_opt
    if run_id is None:
        err(ctx, "Provide --run/--run-id or a positional run ID")
    if run_id <= 0:
        err(ctx, "Run ID must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    res = orch.get_run_jobs_shapen(run_id, **extra_kwargs)
    out(ctx, f"Fetched {len(res.get('jobs', []))} jobs for run {run_id}", data=res)


@gh.command(name="read-pr-comments")
@click.option("--pr", "--pr-number", "pr_number", required=True, type=int, help="The PR number to fetch comments for.")
@click.pass_context
def read_pr_comments(ctx, pr_number):
    """Fetch and display standard and review comments for a PR."""
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")

    orch = ctx.obj["ORCHESTRATOR"]

    res = orch.get_pr_comments(prNumber=pr_number)

    # Response contract validation

    if ctx.obj["JSON"]:
        out(ctx, f"Fetched comments for PR #{pr_number}", data=res)
    else:
        pr = res["pr"]
        click.echo(f"PR #{pr['number']}: {pr['title']}")
        click.echo("--- Comments ---")
        for comment in res.get("comments", []):
            body = click.unstyle(comment.get("body", ""))
            click.echo(f"[{comment['user']}]: {body}")
            click.echo("-" * 20)

        click.echo("\n--- Review Comments ---")
        for comment in res.get("review_comments", []):
            path = comment.get("path")
            line = comment.get("line")
            location = f"{path}:{line}" if line else path
            body = click.unstyle(comment.get("body", ""))
            click.echo(f"[{comment['user']}] in {location}: {body}")
            click.echo("-" * 20)


@gh.command()
@limit_option(help_text="Limit the number of open PRs to process")
@click.pass_context
def status_board(ctx, limit):
    orch = ctx.obj["ORCHESTRATOR"]
    prs = orch.handle_status_board(limit=limit)
    if not ctx.obj["JSON"]:
        click.echo("# Active Agent Work Board\n| Branch | Issue | Status |")
        for pr in prs:
            click.echo(f"| {pr['branch']} | {pr['issue']} | {pr['status']} |")
    out(ctx, f"Found {len(prs)} open PRs.", data={"work": prs})


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
@click.option("--pr", "--pr-number", "pr", required=True, type=int, help="The PR number.")
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


@cli.command(name="schema")
@click.argument("command_path", required=False)
@click.option("--generate", is_flag=True, help="Generate CLI schema from Python models")
@click.pass_context
def schema_cmd(ctx, command_path, generate):
    """Retrieve the schema for a specific subcommand or all commands."""
    if generate:
        from dev_tools.schema_gen import generate_schema
        generate_schema()
        out(ctx, "✅ Schema generation complete")
        return

    # Sanitize and validate command_path to prevent injection
    # Allowed format: words separated by single spaces (no special shell characters)
    if command_path:

        # Stricter regex: words containing only lowercase alphanumeric, hyphens, and underscores,
        # separated by single spaces. No leading/trailing spaces.
        # This prevents any shell character injection and restricts to valid command tokens.
        word = r"[a-z0-9-_]+"
        pattern = f"^{word}( {word})*$"
        if not re.match(pattern, command_path):
            err(
                ctx,
                "Invalid command path. Only lowercase alphanumeric, hyphens, and underscores separated by single spaces are allowed.",
            )

    from dev_tools.schema_utils import collect_commands, get_command_by_path

    target_cmd = get_command_by_path(cli, command_path)

    # If the path matches a group but not a leaf command, target_cmd will be the group.
    # get_command_by_path returns None if not found at all.

    if not target_cmd:
        msg = "Command path not found."
        if command_path and " " not in command_path:
            # Provide a small hint for common top-level groups
            if command_path in ["gh", "repo", "config", "ux", "agent"]:
                msg += f" Did you mean 'td schema {command_path}' to see subcommands?"
        err(ctx, msg)
        return

    # Use a safe depth limit (5) for granular lookups to maintain performance
    res = collect_commands(target_cmd, prefix=command_path or "", max_depth=5)
    out(ctx, f"Schema for {command_path or 'root'}", data={"schema": res})


def _handle_gate(ctx, res, label):
    msg = f"{label}: Current={res.get('current', res.get('size_kb'))}, Baseline={res.get('baseline', res.get('baseline_kb'))}"
    if res["status"] == "error":
        err(ctx, msg, data=res)
    else:
        out(ctx, msg, data=res)


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
    res = orch.check_bundle_size(update=update, baseline_file=baseline_file, threshold=threshold, dry_run=dry_run)
    _handle_gate(ctx, res, "Bundle Size Check")


@cli.command()
@click.pass_context
def doctor(ctx):
    """Full-stack Runtime & Environment Diagnostic Check"""
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.doctor_check()

    if not ctx.obj.get("JSON"):
        click.echo("🩺 BoomTick Doctor Diagnostic Report:")
        click.echo(f"  • Node.js:            v{res.get('node')}")
        click.echo(f"  • pnpm:               {res.get('pnpm')}")
        click.echo(f"  • App ID:             {res.get('app_id')}")
        click.echo(f"  • App Private Key:    {res.get('app_private_key')}")
        click.echo(f"  • Gemini API Key:     {res.get('gemini_api_key')}")
        click.echo(f"  • Git Safe Directory: {res.get('git_safe_directory')}")

    out(ctx, f"✅ Doctor checks complete (Status: {res.get('status', 'success')})", data=res)


@gh.command()
@click.pass_context
def verify_metrics(ctx):
    """Verify CI metrics against established thresholds."""
    res = verify_ci_metrics()
    if res["status"] == "error":
        err(ctx, res["message"], data=res)
    else:
        out(ctx, res["message"], data=res)


@gh.command()
@click.pass_context
def summary_report(ctx):
    """Generate a markdown report of CI metrics for GHA Step Summary."""
    orch = ctx.obj["ORCHESTRATOR"]
    report = orch.generate_ci_summary_report()
    # Always print as raw text to stdout for GHA redirection
    click.echo(report)


@cli.command(name="preflight")
@click.option("--base", default=None, help="Base branch for merge simulation")
@click.pass_context
def preflight(ctx, base):
    """Run local preflight checks: td doctor, typecheck, linting, overlap detection, and merge simulation.

    Repo-aware: typecheck/lint are skipped when package.json lacks those scripts,
    the AST audit is skipped when no configured audit_check_dirs exist in this
    repo, and merge simulation discovers the base ref (config base, origin/main,
    main, origin/master, master) instead of assuming origin/main.
    """
    base = base or get_config().base_branch_name
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_preflight(base_branch=base)
    out(ctx, "✅ Preflight check complete.", data=res)


@gh.command()
@click.pass_context
def pre_submit(ctx):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.pre_submit_checks()
    out(ctx, "Pre-submit checks complete.", data={"results": res})


@gh.command()
@limit_option(help_text="Limit the number of open PRs to process")
@click.pass_context
def overlaps(ctx, limit):
    """Identify and propose consolidation of PRs with high functional or structural overlap."""
    from dev_tools.utils import resolve_resource_path

    try:
        script_path = resolve_resource_path("pr_overlap.py")
    except FileNotFoundError:
        # Absolute fallback if packaging failed
        script_path = os.path.join(os.path.dirname(__file__), "pr_overlap.py")
    cmd = [sys.executable, script_path, "--limit", str(limit)]

    # Check global NO_CACHE from context object
    if ctx.obj.get("NO_CACHE"):
        cmd.append("--no-cache")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        err(ctx, f"pr_overlap.py failed with exit code {e.returncode}")


# ==========================================
# UX COMMAND GROUP
# ==========================================


@cli.group()
def ux():
    """UX Audit Operations"""


@ux.command(name="audit")
@click.option("--route", help="Specific route to audit")
@click.option("--all-routes", is_flag=True, help="Audit all discovered routes")
@click.option("--desktop", is_flag=True, help="Audit desktop viewports")
@click.option("--mobile", is_flag=True, help="Audit mobile viewports")
@click.pass_context
def ux_audit(ctx, route, all_routes, desktop, mobile):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_ux_audit(route=route, all_routes=all_routes, desktop=desktop, mobile=mobile)
    out(ctx, "UX Audit complete.", data=res)


@ux.command()
@click.pass_context
def report(ctx):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.generate_ux_report()
    out(ctx, "UX Report generated.", data=res)


@ux.command()
@click.option("--route", help="Specific route for Lighthouse")
@click.pass_context
def lighthouse(ctx, route):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_lighthouse(route=route)
    out(ctx, "Lighthouse audit complete.", data=res)


@ux.command()
@click.option("--route", help="Specific route for screenshots")
@click.pass_context
def screenshots(ctx, route):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_ux_audit(route=route, screenshots_only=True)
    out(ctx, "Screenshots captured.", data=res)


@ux.command()
@click.option("--route", help="Specific route for image audit")
@click.pass_context
def images(ctx, route):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_ux_audit(route=route, images_only=True)
    out(ctx, "Image audit complete.", data=res)


@ux.command()
@click.option("--route", help="Specific route for contrast check")
@click.pass_context
def contrast(ctx, route):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_ux_audit(route=route, contrast_only=True)
    out(ctx, "Contrast check complete.", data=res)


@ux.command()
@click.option("--route", help="Specific route for overflow check")
@click.pass_context
def overflow(ctx, route):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.run_ux_audit(route=route, overflow_only=True)
    out(ctx, "Overflow check complete.", data=res)


@cli.command()
@click.pass_context
def build(ctx):
    """Build the project after runtime check"""
    orch = ctx.obj["ORCHESTRATOR"]
    orch.runtime_check()
    run_command(["pnpm", "run", "build"])
    out(ctx, "✅ Build complete")


@cli.command()
@click.pass_context
def lint(ctx):
    """Lint the project after runtime check"""
    orch = ctx.obj["ORCHESTRATOR"]
    orch.runtime_check()
    run_command(["pnpm", "run", "lint"])
    out(ctx, "✅ Lint complete")


@cli.group()
def test():
    """Testing Operations"""


@test.command(name="cli")
@click.pass_context
def test_cli(ctx):
    """Run CLI package tests"""
    orch = ctx.obj["ORCHESTRATOR"]
    orch.runtime_check()
    # pytest options are now in pyproject.toml
    # Get the directory of the current file to find the cli package root
    cli_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        subprocess.run([sys.executable, "-m", "pytest", "tests/"], cwd=cli_dir, check=True)
        out(ctx, "✅ CLI tests passed")
    except subprocess.CalledProcessError as e:
        err(ctx, f"CLI tests failed with exit code {e.returncode}")


# ==========================================
# AI COMMAND GROUP
# ==========================================


@cli.group()
def ai():
    """AI Operations"""


@ai.command()
@click.argument("pr_number", type=int)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Bust the diff cache and force a fresh review call",
)
@click.pass_context
def review(ctx, pr_number, no_cache):
    # Optionally bust the review cache so stale results are not silently returned
    if no_cache:
        review_dir = get_or_create_log_dir("reviews")
        pattern = os.path.join(review_dir, f"review_cache_{pr_number}_*.json")
        removed = glob.glob(pattern)
        for f in removed:
            os.remove(f)
        if removed:
            log_info(f"🗑  Removed {len(removed)} cached diff file(s): {removed}")
        else:
            log_info("ℹ️  No cache files found to remove.")

    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.review_pr(pr_number)

    # Surface errors clearly
    if (
        isinstance(res, dict)
        and res.get("recommendation") == "Not Approved"
        and not res.get("reviewComment", "").strip().startswith("CI")
    ):
        # Likely an error result – dump full dict to stderr for diagnosis
        log_info(f"""⚠️  Review returned 'Not Approved' (may indicate an error).
    recommendation : {res.get('recommendation')}
    reviewComment  : {res.get('reviewComment', '')[:500]}""")

    out(ctx, f"✅ Generated review for PR #{pr_number}", data=res)


@ai.command(name="get-context")
@click.pass_context
def ai_get_context(ctx):
    """Retrieve dependency and semantic context for a set of changed files."""
    try:
        raw_data = sys.stdin.read()
        if not raw_data.strip():
            err(ctx, "Empty input from stdin")
        input_data = json.loads(raw_data)
    except Exception as e:
        _handle_unexpected_error(ctx, "ai batch-context", e)

    if not isinstance(input_data, dict):
        err(ctx, "Input JSON must be a dictionary")

    if "files" not in input_data:
        err(ctx, "Input JSON missing required 'files' key")

    files_data = input_data.get("files", [])
    if not files_data:
        click.echo(json.dumps([]))
        return

    results = []

    from dev_tools.services.dependency_graph import DependencyGraph

    graph = DependencyGraph()

    for item in files_data:
        filepath = item.get("path")
        if not filepath:
            continue

        context = {
            "path": filepath,
            "dependencies": list(graph.get_dependencies(filepath)),
            "dependents": list(graph.get_dependents(filepath)),
            "semantic": [],
        }

        results.append(context)

    # Output raw JSON list for compatibility with existing consumers
    click.echo(json.dumps(results))


@ai.command()
@click.argument("file")
@click.pass_context
def analyze(ctx, file):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.analyze_file(file)
    out(ctx, f"✅ Analyzed {file}", data={"result": res})


@ai.command()
@click.option("--pr", "--pr-number", "pr", required=True, type=int, help="The PR number.")
@click.option("--command", required=True)
@click.option("--comment-id")
@click.pass_context
def comment(ctx, pr, command, comment_id):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.handle_comment_command(pr, command, comment_id)
    if res.get("status") == "error":
        err(ctx, res.get("message"), data=res)
    else:
        out(ctx, res.get("message"), data=res)


# ==========================================
# AGENT COMMAND GROUP
# ==========================================


@cli.group(name="agent")
def agent_group():
    """Agent Operations"""


@agent_group.command()
@click.option("--log")
@click.option("--file")
@click.option("--pr", "--pr-number", "pr", type=int, help="The PR number.")
@click.pass_context
def repair_context(ctx, log, file, pr):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.repair_context(log=log, log_file=file, pr_number=pr)
    out(ctx, f"Generated {len(res)} prompts.", data={"prompts": res})


@agent_group.command()
@click.option("--logs")
@click.option("--stdin", is_flag=True)
@click.option("--worktree", is_flag=True)
@click.pass_context
def repair(ctx, logs, stdin, worktree):
    orch = ctx.obj["ORCHESTRATOR"]
    res = orch.repair_local(logs_path=logs, stdin=stdin, worktree=worktree)
    if res["status"] == "success":
        out(ctx, res["message"], data=res)
    else:
        err(ctx, res["message"], data=res)


@agent_group.command(name="run")
@click.option("--worktree", required=True, help="Existing worktree path for the session")
@click.option("--brief", required=True, help="Task brief for the executor")
@click.option("--model", default=None, help="Executor model override")
@click.option("--repo", "-r", default=None, help="Target GitHub repository (e.g. owner/repo)")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.option("--detach/--foreground", default=False,
              help="Return immediately and supervise in background")
@click.pass_context
def run(ctx, worktree, brief, model, repo, root_path, detach):
    """Dispatch a local worktree session (fully local, no cloud API)."""
    from dev_tools.services import local_sessions as ls
    try:
        root = ls.repo_root_for(root_path)
        wt = worktree if os.path.isabs(worktree) else os.path.join(os.getcwd(), worktree)
        if not os.path.isdir(wt):
            err(ctx, f"Worktree path does not exist: {worktree}")
            return
        session = ls.new_session(wt, brief, model=model, repo=repo)
        ls.save_session(session)
        sid = session["sessionId"]
        if ls.exec_disabled():
            out(ctx, f"Session {sid} recorded (execution disabled).",
                data={"session": ls.status_summary(session), "executed": False})
            return
        if detach:
            pid = ls.spawn_detached(root, sid)
            out(ctx, f"Session {sid} dispatched (supervisor pid {pid}).",
                data={"session": ls.status_summary(session),
                      "supervisor_pid": pid})
            return
        if not ctx.obj["JSON"]:
            click.echo(f"Session {sid} running in {wt}")
            code = ls.run_executor(root, session, stream=click.echo)
            click.echo(f"Session {sid} finished: {session['state']}")
        else:
            code = ls.run_executor(root, session)
        out(ctx, f"Session {sid} finished: {session['state']}.",
            data={"session": ls.status_summary(session), "exit_code": code})
        if code:
            sys.exit(code)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent run", e)


@agent_group.command(name="submit-pr")
@click.option("--worktree", required=True, help="Worktree path holding the branch")
@click.option("--title", required=True, help="PR title")
@click.option("--body", default="", help="PR body")
@click.option("--base", default="main", help="Base branch for the PR")
@click.option("--draft/--no-draft", default=True,
              help="Open as a draft for human review")
@click.option("--issue", "issue_number", type=int, default=None,
              help="Gate changed files against this issue's scope")
@click.option("--repo", "-r", default=None,
              help="Target GitHub repository (e.g. owner/repo)")
@click.option("--skip-scope-check", is_flag=True,
              help="Bypass the scope gate (mirrors CI's [skip-scope-check])")
@click.pass_context
def submit_pr(ctx, worktree, title, body, base, draft, issue_number,
              repo, skip_scope_check):
    """Push a worktree branch and open a PR (scope-gated with --issue)."""
    from dev_tools.services import submit_pr as sp
    try:
        wt = worktree if os.path.isabs(worktree) \
            else os.path.join(os.getcwd(), worktree)
        issue_text = None
        if issue_number is not None:
            orch = ctx.obj["ORCHESTRATOR"]
            extra = {"repo": repo} if repo else {}
            details = orch.get_issue_details(issue_number, **extra)
            issue_text = (details.get("title", "") + "\n"
                          + (details.get("body") or ""))
        res = sp.submit(wt, title, body, base, draft, repo,
                        issue_text, skip_scope_check,
                        issue=issue_number)
        if not ctx.obj["JSON"]:
            click.echo(f"submitted {res['branch']} -> {res['url']}")
        out(ctx, f"PR submitted: {res['url']}.", data=res)
    except sp.SubmitError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent submit-pr", e)


@agent_group.command(name="run-local")
@click.option("--pr", "--pr-number", "pr_number", required=False, type=int, help="Pull Request number to evaluate.")
@click.option("--issue", "issue_number", type=int, help="Optional linked Issue number.")
@click.pass_context
def run_local(ctx, pr_number, issue_number):
    """Run a single-agent multi-role sequential workflow locally."""
    try:
        script_path = Path("scripts/run-context-agent.py").resolve()
        if not script_path.exists():
            err(ctx, f"Local orchestration script not found at {script_path}")
            return

        spec = importlib.util.spec_from_file_location("run_context_agent", script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["run_context_agent"] = module
        spec.loader.exec_module(module)

        target_str = f"PR #{pr_number}" if pr_number else "all open PRs"

        if not ctx.obj.get("JSON", False):
            click.echo("\n" * 2)
            click.echo("=" * 60)
            click.echo("   🚀  LOCAL AGENT WORKFLOW DISPATCHED  🚀   ".center(60))
            click.echo("=" * 60)
            click.echo("\n")
            click.echo(f"  Target : {target_str}")
            click.echo("\n" * 2)

        out(ctx, f"Starting local multi-role agent for {target_str}...")
        module.run_single_agent_multi_role_scratchpad(pr_number, issue_number)
        out(ctx, "✅ Local agent workflow completed successfully.")
    except Exception as e:
        _handle_unexpected_error(ctx, "agent run-local", e)


@agent_group.command(name="plan-review")
@click.option("--pr", "--pr-number", "pr_number", required=True, type=int, help="Pull Request number")
@click.option("--issue", "issue_number", type=int, help="Issue number")
@click.pass_context
def plan_review(ctx, pr_number, issue_number):
    """Generate a deterministic review workflow plan for an agent."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.generate_review_workflow(pr_number, issue_number)
        out(ctx, f"Workflow plan generated: {res['plan_path']}", data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent plan-review", e)


@agent_group.command(name="plan-aggregation")
@click.option(
    "--pr",
    "--prs",
    "--pr-number",
    "--pr-numbers",
    "pr_numbers",
    required=True,
    type=int,
    multiple=True,
    help="PR numbers to aggregate",
)
@click.option("--target", required=True, help="Target branch name for aggregation")
@click.pass_context
def plan_aggregation(ctx, pr_numbers, target):
    """Generate a deterministic aggregation workflow plan for an agent."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.generate_aggregation_workflow(list(pr_numbers), target)
        out(ctx, f"Workflow plan generated: {res['plan_path']}", data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent plan-aggregation", e)


@agent_group.command(name="plan-issue-audit")
@json_option
@click.option(
    "--issue",
    "--issues",
    "issue_numbers",
    multiple=True,
    type=int,
    help="Issue number(s) to audit (e.g. --issue 1 --issue 2)",
)
@click.option("--all-open", is_flag=True, help="Audit all open issues")
@limit_option(help_text="Limit the number of open issues to process")
@click.pass_context
def plan_issue_audit(ctx, issue_numbers, all_open, limit):
    """Generate deterministic roadmap and checklist for auditing open issues."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.plan_issue_audit(issue_numbers=list(issue_numbers), all_open=all_open, limit=limit)
        out(ctx, f"Issue audit plan generated. Summary: {res['status_file']}", data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent plan-issue-audit", e)


@agent_group.command(name="plan-workflow-audit")
@click.option("--workflow", help="Specific workflow file to audit")
@click.pass_context
def plan_workflow_audit(ctx, workflow):
    """Generate deterministic roadmap and checklist for auditing GitHub workflows."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.plan_workflow_audit(workflow=workflow)
        out(ctx, f"Workflow audit plan generated. Summary: {res['status_file']}", data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent plan-workflow-audit", e)


@agent_group.command(name="install-workflows")
@click.option("--target", default=".", help="Target directory to install workflows.")
@click.option("--dry-run/--execute", default=True, help="Run without writing files.")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing files.")
@click.pass_context
def install_workflows(ctx, target, dry_run, force):
    """Install and configure standardized GitHub Actions workflows."""
    from dev_tools.handlers.workflow_installer import install_workflows as do_install
    try:
        success = do_install(target_dir=target, dry_run=dry_run, force=force)
        if success:
            out(ctx, "✅ Workflows installation complete.", data={"status": "success"})
        else:
            err(ctx, "Workflows installation failed.")
    except Exception as e:
        _handle_unexpected_error(ctx, "agent install-workflows", e)


@agent_group.command(name="merge-approved")
@click.option("--repo", "-r", help="Target GitHub repository (e.g. owner/repo)")
@click.option("--dry-run/--execute", default=True, help="Preview mergeable PRs or merge each approved PR")
@click.pass_context
def merge_approved(ctx, repo, dry_run):
    """Deterministic merge gate for approved, green, non-draft, mergeable PRs."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.merge_approved(repo=repo, execute=not dry_run)
        if not ctx.obj.get("JSON", False):
            mode_str = "Execution" if not dry_run else "Dry Run"
            click.echo(f"Agent Merge-Approved ({mode_str}):")
            click.echo(f"  • Total Evaluated: {res['total_evaluated']}")
            click.echo(f"  • Eligible PRs:   {res['eligible_count']}")
            if not dry_run:
                click.echo(f"  • Merged PRs:     {res['merged_count']}")
            for item in res.get("results", []):
                pr_num = item.get("pr_number")
                title = item.get("title", "")
                if dry_run:
                    status_icon = "✅" if item.get("is_eligible") else "❌"
                    status_msg = "READY" if item.get("is_eligible") else f"REFUSED: {item.get('reason')}"
                    click.echo(f"  {status_icon} #{pr_num}: {title} [{status_msg}]")
                else:
                    status_icon = "✅" if item.get("merged") else "❌"
                    status_msg = item.get("message")
                    click.echo(f"  {status_icon} #{pr_num}: {title} [{status_msg}]")

        out(ctx, f"Evaluated {res['total_evaluated']} PRs ({res['eligible_count']} eligible).", data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent merge-approved", e)


@agent_group.command(name="suggest")
@click.option("--repo", "-r", help="Target GitHub repository (e.g. owner/repo)")
@click.pass_context
def suggest(ctx, repo):
    """Evaluate repository state and suggest next actions using deterministic fast-path."""
    orch = ctx.obj["ORCHESTRATOR"]
    try:
        res = orch.suggest_next_action(repo=repo)
        if not ctx.obj.get("JSON", False):
            click.echo(res.get("suggestion"))
        out(ctx, res.get("suggestion", ""), data=res)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent suggest", e)


@cli.command(name="context-warm")
@click.option("--force", is_flag=True, help="Force re-generation of context even if not stale")
@click.pass_context
def context_warm(ctx, force):
    """Pre-warm the .agent-context.json repository index."""
    context_file = ".agent-context.json"

    # Determine if the context file is stale or missing
    is_stale = not os.path.exists(context_file) or force

    if not is_stale:
        try:
            # Compare the last commit timestamp of the context file with the HEAD commit
            # This handles branch switches where the working directory might be clean but context is old
            res = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", context_file],
                capture_output=True,
                text=True,
                check=True,
            )
            context_ts = int(res.stdout.strip() or 0)

            res_head = subprocess.run(["git", "log", "-1", "--format=%ct"], capture_output=True, text=True, check=True)
            head_ts = int(res_head.stdout.strip() or 0)

            if head_ts > context_ts:
                is_stale = True
            else:
                # Also check for uncommitted changes in the working directory
                res_diff = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                is_stale = bool(res_diff.stdout.strip())
        except Exception as e:
            log_warn(f"Error checking context staleness via git: {e}")
            # Fallback to simple mtime check if git fails
            mtime = os.path.getmtime(context_file)
            if os.path.exists("package.json") and os.path.getmtime("package.json") > mtime:
                is_stale = True

    if is_stale:
        log_info("🧊 Context is stale or missing. Warming up...")
        try:
            # Use dynamic resolution from ProjectConfig for the context builder script
            script_path = get_config().context_builder_script
            if not os.path.exists(script_path):
                err(ctx, f"Context builder script not found at {script_path}")

            with open(context_file, "w", encoding="utf-8") as f:
                try:
                    subprocess.run([sys.executable, script_path], stdout=f, check=True)
                except subprocess.CalledProcessError as e:
                    err(
                        ctx,
                        f"Context builder script failed (exit {e.returncode}): {e.stderr or str(e)}",
                    )

            out(ctx, "✅ Context pre-warmed successfully.", data={"path": context_file})
        except Exception as e:
            _handle_unexpected_error(ctx, "context-warm", e)
    else:
        out(ctx, "✅ Context is up-to-date.", data={"path": context_file})


# --- Local Session Commands (parity with MCP agent tools) ---


@cli.group(name="session")
def session_group():
    """Local worktree session inspection and supervision."""


@session_group.command(name="status")
@click.argument("session_id")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.pass_context
def session_status(ctx, session_id, root_path):
    """Show state, checkpoint, changed files and verification."""
    from dev_tools.services import local_sessions as ls
    try:
        root = ls.repo_root_for(root_path)
        session = ls.load_session(root, session_id)
        summary = ls.status_summary(session)
        if not ctx.obj["JSON"]:
            click.echo(f"Session {summary['sessionId']}: {summary['state']} "
                       f"@ {summary['lastCheckpoint']}")
            for name in summary["changedFiles"]:
                click.echo(f"  M {name}")
        out(ctx, f"Session {session_id}: {summary['state']}.",
            data={"session": summary})
    except ls.SessionNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "session status", e)


@session_group.command(name="logs")
@click.argument("session_id")
@click.option("--tail", type=int, default=100, help="Lines of log to show")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.pass_context
def session_logs(ctx, session_id, tail, root_path):
    """Show the tail of a session's logs plus the total line count."""
    from dev_tools.services import local_sessions as ls
    try:
        root = ls.repo_root_for(root_path)
        session = ls.load_session(root, session_id)
        lines, total = ls.tail_logs(session, tail)
        if not ctx.obj["JSON"]:
            for line in lines:
                click.echo(line)
            click.echo(f"--- {total} total line(s) ---")
        out(ctx, f"Session {session_id} logs ({total} total).",
            data={"sessionId": session_id, "logs": lines,
                  "totalLines": total})
    except ls.SessionNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "session logs", e)


@session_group.command(name="supervise", hidden=True)
@click.argument("session_id")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.pass_context
def session_supervise(ctx, session_id, root_path):
    """Run a session's executor detached (spawned by agent run --detach)."""
    from dev_tools.services import local_sessions as ls
    try:
        root = ls.repo_root_for(root_path)
        session = ls.load_session(root, session_id)
        code = ls.run_executor(root, session)
        if code:
            sys.exit(code)
    except ls.SessionNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "session supervise", e)


@cli.group(name="skill")
def skill_group():
    """Read session playbooks from .agents/skills (no MCP needed)."""


@skill_group.command(name="list")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.pass_context
def skill_list(ctx, root_path):
    """List available skill names."""
    from dev_tools.services import local_sessions as ls
    try:
        names = ls.list_skills(ls.repo_root_for(root_path))
        if not ctx.obj["JSON"]:
            for name in names:
                click.echo(name)
        out(ctx, f"{len(names)} skill(s).", data={"skills": names})
    except Exception as e:
        _handle_unexpected_error(ctx, "skill list", e)


@skill_group.command(name="read")
@click.argument("name")
@click.option("--path", "root_path", default=None, help="Repo root override (default: git root)")
@click.pass_context
def skill_read(ctx, name, root_path):
    """Print a skill's SKILL.md content."""
    from dev_tools.services import local_sessions as ls
    try:
        content = ls.read_skill(ls.repo_root_for(root_path), name)
        if not ctx.obj["JSON"]:
            click.echo(content)
        out(ctx, f"Skill {name}.",
            data={"skill": name, "content": content})
    except ls.SkillNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "skill read", e)


@cli.group(name="worktree")
def worktree_group():
    """Managed git worktrees under .worktrees (parity with MCP tools)."""


@worktree_group.command(name="create")
@click.argument("name", required=False)
@click.option("--base", "base_branch", default="main",
              help="Base branch for the new worktree branch")
@click.option("--path", "root_path", default=None,
              help="Repo root override (default: git root)")
@click.option("--repo-root", "root_path", default=None,
              help="Repo root override (alias for --path)")
@click.option("--issue", "issue_id", default=None,
              help="Issue number: provision warm issue worktree instead")
@_gate_json_option
@click.pass_context
def worktree_create(ctx, name, base_branch, root_path, issue_id):
    """Create a managed worktree on a new branch."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import worktrees as wt
    try:
        root = ls.repo_root_for(root_path)
        if issue_id is not None:
            try:
                status = wt.create_for_issue(root, issue_id)
            except wt.WorktreeError as e:
                err(ctx, str(e), code=1)
            if not ctx.obj["JSON"]:
                click.echo(f"{status['worktreeId']} "
                           f"{status['branch']} {status['path']}")
            out(ctx, f"Worktree {status['worktreeId']} created.",
                data={"status": "ready", **status})
            return
        wid, path, branch = wt.create(root, name, base_branch)
        if not ctx.obj["JSON"]:
            click.echo(f"{wid} {branch} {path}")
        out(ctx, f"Worktree {wid} created.",
            data={"worktreeId": wid, "path": path, "branch": branch})
    except wt.WorktreeError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree create", e)


@worktree_group.command(name="list")
@click.option("--path", "root_path", default=None,
              help="Repo root override (default: git root)")
@click.pass_context
def worktree_list(ctx, root_path):
    """List managed worktrees with branch, age and dirtiness."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import worktrees as wt
    try:
        items = wt.list_worktrees(ls.repo_root_for(root_path))
        if not ctx.obj["JSON"]:
            for item in items:
                click.echo(f"{item['worktreeId']} {item['branch']} "
                           f"({item['changedFilesCount']} changed) "
                           f"{item['path']}")
        out(ctx, f"{len(items)} worktree(s).",
            data={"worktrees": items})
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree list", e)


@worktree_group.command(name="remove")
@click.argument("worktree_id")
@click.option("--force", is_flag=True,
              help="Remove even with uncommitted changes")
@click.option("--path", "root_path", default=None,
              help="Repo root override (default: git root)")
@click.pass_context
def worktree_remove(ctx, worktree_id, force, root_path):
    """Remove a managed worktree (refuses dirty ones unless --force)."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import worktrees as wt
    try:
        freed = wt.remove(ls.repo_root_for(root_path), worktree_id, force)
        if not ctx.obj["JSON"]:
            click.echo(f"removed {worktree_id}")
        out(ctx, f"Worktree {worktree_id} removed.",
            data={"status": "removed", "worktreeId": worktree_id,
                  "freedBytes": freed})
    except wt.WorktreeError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree remove", e)


@cli.group(name="rag")
def rag_group():
    """Vector index: build incrementally, query with hybrid ranking."""


@rag_group.command(name="index")
@click.option("--repo-root", "repo_root", default=None,
              help="Repo root to index (default: git root)")
@click.option("--incremental/--full", default=True,
              help="Diff last indexed SHA (default) or rebuild everything")
@_gate_json_option
@click.pass_context
def rag_index(ctx, repo_root, incremental):
    """Index (or incrementally update) the repo vector store."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import vector_store as vs
    try:
        root = ls.repo_root_for(repo_root)
        if not os.path.isdir(os.path.join(root, ".git")):
            err(ctx, f"not a git checkout: {root}", code=1)
        data = vs.update_index(root, incremental=incremental)
        if not ctx.obj["JSON"]:
            click.echo(f"indexed {len(data['updated_files'])} file(s), "
                       f"{data['added_chunks']} chunk(s) "
                       f"at {data['head_sha'][:8]}")
        out(ctx, "index ready.", data=data)
    except Exception as e:
        _handle_unexpected_error(ctx, "rag index", e)


@rag_group.command(name="query")
@click.option("--repo-root", "repo_root", default=None,
              help="Repo root whose index to query (default: git root)")
@click.option("--query", "query", required=True,
              help="Natural-language query text")
@click.option("--top-k", "top_k", default=8, type=int,
              help="Maximum hits to return")
@_gate_json_option
@click.pass_context
def rag_query(ctx, repo_root, query, top_k):
    """Query the repo vector index with hybrid ranking."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import vector_store as vs
    try:
        root = ls.repo_root_for(repo_root)
        hits = vs.query_index(root, query, top_k=top_k)
        data = {"status": "success", "query": query, "hits": hits,
                "count": len(hits)}
        if not ctx.obj["JSON"]:
            for hit in hits:
                click.echo(f"{hit['filepath']}:{hit['start_line']}: "
                           f"{hit['content'][:120]}")
        out(ctx, f"{len(hits)} hit(s).", data=data)
    except Exception as e:
        _handle_unexpected_error(ctx, "rag query", e)


@cli.command(name="init")
@click.option("--repo-root", "repo_root", default=None,
              help="Repo root to initialize (default: git root)")
@_gate_json_option
@click.pass_context
def init_repo(ctx, repo_root):
    """Initialize a repo: fast-forward main, sync deps, index RAG.

    Emits {"status", "head_sha", "deps_synced", "rag_indexed_sha",
    "updated_files"}.
    """
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import vector_store as vs
    from dev_tools.services import worktrees as wt
    try:
        root = ls.repo_root_for(repo_root)
        if not os.path.isdir(os.path.join(root, ".git")):
            err(ctx, f"not a git checkout: {root}", code=1)
        _updated, head_sha, main_note = wt.fetch_main(root)
        synced, deps_note = wt.warm_dependencies(root)
        rag = vs.update_index(root, incremental=True)
        data = {"status": "ready", "head_sha": head_sha,
                "deps_synced": synced, "deps_note": deps_note,
                "main_note": main_note,
                "rag_indexed_sha": rag.get("last_indexed_sha", ""),
                "updated_files": rag.get("updated_files", [])}
        if not ctx.obj["JSON"]:
            click.echo(f"ready at {head_sha[:8]} "
                       f"(deps synced: {synced}, "
                       f"{len(data['updated_files'])} file(s) indexed)")
        out(ctx, "repo ready.", data=data)
    except Exception as e:
        _handle_unexpected_error(ctx, "init", e)


# --- Multi-Repository Ecosystem Commands ---


@cli.group(name="multi-repo")
def multi_repo_group():
    """Multi-repository ecosystem management and orchestration."""


@cli.group(name="repos")
def repos_group():
    """Alias for multi-repo command group."""


# pylint: disable=too-many-statements
def _register_multi_repo_commands(group):
    @group.command(name="list")
    @click.option("--all", "include_all", is_flag=True, help="Include all auto-discovered sibling directories")
    @click.pass_context
    def list_cmd(ctx, include_all):
        """List ecosystem repositories and local paths."""
        try:
            repos = discover_ecosystem_repos(explicit_config={} if include_all else None)
            repo_list = [{"name": name, "path": str(path)} for name, path in repos.items()]
            if not ctx.obj.get("JSON", False):
                click.echo(f"Found {len(repo_list)} ecosystem repositories:")
                for r in repo_list:
                    click.echo(f"  • {r['name']:<25} {r['path']}")
            out(ctx, f"Discovered {len(repo_list)} repositories", data={"repos": repo_list, "total": len(repo_list)})
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo list", e)

    @group.command(name="status")
    @click.option("--repo", "-r", "filter_repos", multiple=True, help="Filter to specific repository name(s)")
    @click.pass_context
    def status_cmd(ctx, filter_repos):
        """Show git, branch, and agent context status across ecosystem repositories."""
        try:
            filters = list(filter_repos) if filter_repos else None
            repos = discover_ecosystem_repos(filter_repos=filters)
            summaries = [get_repo_summary(name, path) for name, path in repos.items()]

            if not ctx.obj.get("JSON", False):
                click.echo(f"{'Repository':<25} {'Branch':<20} {'Commit':<10} {'Dirty':<8} {'Context':<8}")
                click.echo("-" * 75)
                for s in summaries:
                    dirty_str = "dirty" if s["is_dirty"] else "clean"
                    ctx_str = "yes" if s["has_context"] else "missing"
                    click.echo(f"{s['repo']:<25} {s['branch']:<20} {s['commit']:<10} {dirty_str:<8} {ctx_str:<8}")

            out(ctx, f"Status for {len(summaries)} repositories", data={"repos": summaries, "total": len(summaries)})
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo status", e)

    @group.command(name="context-warm")
    @click.option("--repo", "-r", "filter_repos", multiple=True, help="Filter to specific repository name(s)")
    @click.option("--force", is_flag=True, help="Force re-generation of context even if not stale")
    @click.pass_context
    def context_warm_cmd(ctx, filter_repos, force):
        """Pre-warm .agent-context.json across ecosystem repositories."""
        try:
            filters = list(filter_repos) if filter_repos else None
            repos = discover_ecosystem_repos(filter_repos=filters)
            res = warm_ecosystem_context(repos, force=force)

            if not ctx.obj.get("JSON", False):
                click.echo(f"Warmed context across {res['total_repos']} repositories:")
                for r in res["results"]:
                    status_icon = "✅" if r["passed"] else "❌"
                    click.echo(f"  {status_icon} {r['repo']:<25} ({r['strategy']}, {r['duration_seconds']}s)")
                    if not r["passed"] and r.get("output"):
                        click.echo(f"     Error: {r['output']}")

            if res["status"] == "success":
                out(ctx, f"Context warmed across {res['total_repos']} repositories", data=res)
            else:
                err(ctx, f"Failed to warm context on {res['total_failed']} repositories", data=res)
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo context-warm", e)

    @group.command(name="exec")
    @click.argument("command")
    @click.option("--repo", "-r", "filter_repos", multiple=True, help="Filter to specific repository name(s)")
    @click.option("--fail-fast/--continue-on-error", default=False, help="Stop on first error or continue")
    @click.pass_context
    def exec_cmd(ctx, command, filter_repos, fail_fast):
        """Execute a shell command sequentially across ecosystem repositories."""
        try:
            filters = list(filter_repos) if filter_repos else None
            repos = discover_ecosystem_repos(filter_repos=filters)
            res = exec_in_repos(repos, command, continue_on_error=not fail_fast)

            if not ctx.obj.get("JSON", False):
                click.echo(f"Executed '{command}' across {res['total_repos']} repositories:")
                for r in res["results"]:
                    status_icon = "✅" if r["passed"] else "❌"
                    click.echo(f"\n{status_icon} [{r['repo']}] (exit {r['exit_code']}, {r['duration_seconds']}s)")
                    if r["stdout"]:
                        click.echo(r["stdout"])
                    if r["stderr"]:
                        click.echo(f"Error output:\n{r['stderr']}")

            if res["status"] == "success":
                out(ctx, f"Command completed across {res['total_repos']} repositories", data=res)
            else:
                err(ctx, f"Command failed on {res['total_failed']} repositories", data=res)
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo exec", e)


_register_multi_repo_commands(multi_repo_group)
_register_multi_repo_commands(repos_group)


def _read_spec_source(file):
    """Read spec text from a path, or stdin when file is '-'."""
    if file == "-":
        return sys.stdin.read()
    with open(file, encoding="utf-8") as handle:
        return handle.read()


def _spec_section_lines(body, *headings):
    """Raw lines of the first section whose heading matches."""
    wanted = {h.lower() for h in headings}
    capture = False
    lines = []
    for line in (body or "").splitlines():
        match = re.match(r"^#{1,3}\s+(.+?)\s*$", line.strip())
        if match:
            if capture:
                break
            capture = match.group(1).strip().lower() in wanted
            continue
        if capture:
            lines.append(line)
    return lines


def _spec_backtick_paths(body, *headings):
    """Backtick-quoted paths inside the given sections."""
    paths = []
    for line in _spec_section_lines(body, *headings):
        for path in re.findall(r"`([^`]+)`", line):
            path = path.strip()
            if path and path not in paths:
                paths.append(path)
    return paths


def _spec_checklist_items(body):
    """Checkbox acceptance criteria lines in document order."""
    items = []
    for line in (body or "").splitlines():
        match = re.match(r"^\s*[-*]\s+\[[\sxX]\]\s+(.+?)\s*$", line)
        if match:
            items.append(match.group(1))
    return items


def _spec_fenced_commands(body):
    """Bash commands from fenced blocks in the Verification section."""
    lines = _spec_section_lines(
        body, "verification", "verification commands", "validation")
    commands = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            commands.append(stripped)
    return commands


@cli.command(name="validate-issue")
@click.option("--file", "file", required=True,
              help="Path to the spec markdown file, or '-' for stdin")
@click.option("--repo-root", "repo_root", default=None,
              help="Checkout for scope existence checks (default: git root)")
@_gate_json_option
@click.pass_context
def validate_issue_spec(ctx, file, repo_root):
    """Validate a design spec file deterministically (exit 0 iff valid).

    Emits {"valid", "allowed_files", "forbidden_files",
    "verification_commands", "acceptance_criteria", "errors"}.
    """
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import spec_issue as spec
    try:
        body = _read_spec_source(file)
        title = ""
        for line in body.splitlines():
            match = re.match(r"^#\s+(.+?)\s*$", line.strip())
            if match:
                title = match.group(1)
                break
        if not title:
            for line in body.splitlines():
                if line.strip():
                    title = line.strip()
                    break
        root = ls.repo_root_for(repo_root)
        missing = spec.missing_headers(body)
        scope = spec.scope_status(title + "\n" + body, root)
        forbidden_files = _spec_backtick_paths(
            body, "forbidden files", "forbidden")
        forbidden_lower = {p.lower() for p in forbidden_files}
        actual = set()
        for dirpath, dirnames, filenames in os.walk(root):
            _prune_walk_dirs(dirnames)
            for filename in filenames:
                actual.add(os.path.relpath(
                    os.path.join(dirpath, filename), root).lower())
        allowed_files = [item["path"] for item in scope
                         if item["path"] not in forbidden_lower]
        acceptance_criteria = _spec_checklist_items(body)
        verification_commands = _spec_fenced_commands(body)
        if not verification_commands:
            verification_commands = spec.detect_gates(root)
        errors = []
        for header in missing:
            errors.append(f"missing required section: {header}")
        command_refs = " ".join(
            verification_commands).lower()
        for item in scope:
            if item["path"] in forbidden_lower:
                continue
            if item["path"] not in actual:
                if item["path"] in command_refs:
                    continue
                same_line_created = any(
                    item["path"] in line.lower()
                    and "(create)" in line.lower()
                    for line in body.splitlines())
                if not same_line_created:
                    errors.append(
                        f"allowed path not in checkout: {item['path']} "
                        "(mark with (CREATE) if it is a new file)")
        if re.search(r"\bTODO\b|\bTBD\b", body):
            errors.append("spec contains TODO/TBD placeholders")
        if not verification_commands:
            errors.append("no verification commands found")
        if not acceptance_criteria:
            errors.append("no acceptance criteria checklist found")
        data = {"valid": not errors,
                "allowed_files": allowed_files,
                "forbidden_files": forbidden_files,
                "verification_commands": verification_commands,
                "acceptance_criteria": acceptance_criteria,
                "errors": errors}
        if not ctx.obj["JSON"]:
            if data["valid"]:
                click.echo("spec is valid")
            else:
                click.echo("spec is NOT valid:")
                for error in errors:
                    click.echo(f"   ❌ {error}")
        out(ctx, f"spec valid: {data['valid']}.", data=data)
        if errors:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "validate-issue", e)


def _worktree_changed_files(worktree):
    """Paths changed vs origin/main inside worktree (relative, sorted)."""
    res = run_command(["git", "diff", "--name-only", "origin/main", "--", "."],
                      check=False, cwd=worktree)
    if res.returncode != 0:
        raise CLIError(
            f"git diff origin/main failed in {worktree}: "
            f"{res.stderr or res.stdout}")
    return sorted(p for p in (res.stdout or "").splitlines() if p.strip())


@cli.command(name="verify-scope")
@click.option("--spec-file", "spec_file", required=True,
              help="Path to the validated design spec markdown file")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to gate")
@click.option("--auto-revert", is_flag=True, default=False,
              help="Revert files outside the allowed scope")
@_gate_json_option
@click.pass_context
def verify_scope_gate(ctx, spec_file, worktree, auto_revert):
    """Gate worktree changes against a spec file (exit 0 iff in scope).

    Emits {"passed", "modified_files", "violations"}.
    """
    from dev_tools.services import scope_gate
    try:
        with open(spec_file, encoding="utf-8") as handle:
            spec_text = handle.read()
        changed = _worktree_changed_files(worktree)
        passed, allowed, disallowed = scope_gate.check_scope(
            changed, spec_text, root=worktree)
        violations = sorted(set(disallowed))
        forbidden = _spec_backtick_paths(
            spec_text, "forbidden files", "forbidden")
        forbidden_norm = set()
        for entry in forbidden:
            norm = entry.strip().lower().lstrip("./")
            forbidden_norm.add(norm)
        for path in changed:
            lowered = path.lower()
            if any(lowered == norm or lowered.endswith("/" + norm)
                   for norm in forbidden_norm):
                if path not in violations:
                    violations.append(path)
        violations = sorted(set(violations))
        passed = not violations
        reverted = []
        if auto_revert and violations:
            for path in violations:
                full = os.path.join(worktree, path)
                if os.path.isdir(full):
                    continue
                if os.path.isfile(full):
                    tracked = run_command(
                        ["git", "-C", worktree, "ls-files",
                         "--error-unmatch", "--", path],
                        check=False)
                    if tracked.returncode == 0:
                        res = run_command(
                            ["git", "-C", worktree, "checkout",
                             "--", path],
                            check=False)
                    else:
                        try:
                            os.remove(full)
                            res = None
                        except OSError:
                            continue
                        reverted.append(path)
                        continue
                    if res.returncode == 0:
                        reverted.append(path)
            _, _, still_out = scope_gate.check_scope(
                [p for p in changed if p not in reverted],
                spec_text, root=worktree)
            violations = sorted(set(still_out))
            passed = not violations
        data = {"passed": passed,
                "modified_files": changed,
                "violations": violations,
                "reverted": reverted}
        if not ctx.obj["JSON"]:
            if passed:
                click.echo("✅ scope check passed")
            else:
                click.echo("❌ scope violations:")
                for path in violations:
                    click.echo(f"   ❌ {path}")
        out(ctx, f"scope passed: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "verify-scope", e)


def _td_package_root():
    """Root of the installed td package (holds scripts/ and .agents/)."""
    return os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", ".."))


def _resolve_audit_script(worktree, *candidates, need_config=None,
                          worktree_only=False):
    """First existing audit script: worktree checkout, then td package.

    need_config names a config file (relative to the script base) that
    must also exist, so repo-specific audits never run under another
    repo's config. worktree_only disables the td package fallback for
    audits that are only meaningful with the worktree's own config.
    """
    bases = (worktree,) if worktree_only else (worktree, _td_package_root())
    for base in bases:
        if need_config and not os.path.isfile(
                os.path.join(base, need_config)):
            continue
        for candidate in candidates:
            full = os.path.join(base, candidate)
            if os.path.isfile(full):
                return full
    return None


@cli.command(name="audit-code")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to audit")
@_gate_json_option
@click.pass_context
def audit_code_gate(ctx, worktree):
    """Audit worktree changes for slop and AST violations (exit 0 iff clean).

    Emits {"passed", "slop_findings", "suppressions_added",
    "ast_violations"}.
    """
    from dev_tools.services.ast_audit import ASTAuditor
    try:
        changed = _worktree_changed_files(worktree)
        code_files = [p for p in changed
                      if p.endswith((".py", ".ts", ".tsx", ".js",
                                     ".jsx", ".mjs", ".mts"))]
        auditor = ASTAuditor()
        ast_violations = []
        for rel in code_files:
            full = os.path.join(worktree, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, encoding="utf-8", errors="ignore") as handle:
                    code = handle.read()
                for finding in auditor.audit_file(rel, code) or []:
                    ast_violations.append({
                        "file": rel,
                        "rule": finding.get("rule"),
                        "message": finding.get("message"),
                        "line": finding.get("line"),
                        "severity": finding.get("severity"),
                    })
            except Exception:
                continue
        slop_findings = []
        slop_script = _resolve_audit_script(
            worktree, os.path.join(".agents", "scripts", "audit-ai-slop.py"),
            need_config=os.path.join(".agents", "audit.config.yaml"),
            worktree_only=True)
        if slop_script:
            res = run_command(["python3", slop_script], check=False,
                              cwd=worktree, log_on_error=False)
            output = res.stdout or ""
            match = re.search(r"Total [Vv]iolations[^0-9]{0,10}(\d+)",
                              output)
            count = int(match.group(1)) if match else -1
            if res.returncode != 0 or count != 0:
                slop_findings.append({
                    "script": os.path.basename(slop_script),
                    "exit_code": res.returncode,
                    "summary": output.strip()[-2000:],
                })
        antipattern_script = _resolve_audit_script(
            worktree, os.path.join("scripts", "detect-antipatterns.mjs"))
        if antipattern_script and code_files:
            res = run_command(["node", antipattern_script, "--json"]
                              + code_files,
                              check=False, cwd=worktree,
                              log_on_error=False)
            try:
                payload = json.loads((res.stdout or "")[
                    (res.stdout or "").find("{"):])
                for path, items in (
                        payload.get("violations") or {}).items():
                    for item in items or []:
                        ast_violations.append({
                            "file": os.path.relpath(path, worktree)
                            if os.path.isabs(path) else path,
                            "rule": (item or {}).get("pattern",
                                                     "antipattern"),
                            "message": (item or {}).get("message", ""),
                            "line": (item or {}).get("line"),
                            "severity": (item or {}).get("severity"),
                        })
            except (ValueError, AttributeError):
                if res.returncode != 0:
                    slop_findings.append({
                        "script": "detect-antipatterns.mjs",
                        "exit_code": res.returncode,
                        "summary": (res.stdout or res.stderr or "")[-2000:],
                    })
        suppressions_added = []
        suppression_script = _resolve_audit_script(
            worktree,
            os.path.join("scripts", "check-suppression-inventory.mjs"))
        if suppression_script:
            res = run_command(["node", suppression_script], check=False,
                              cwd=worktree, log_on_error=False)
            output = (res.stdout or "") + (res.stderr or "")
            for line in output.splitlines():
                if "added" in line.lower() and "suppression" in line.lower():
                    suppressions_added.append(line.strip())
        passed = (not ast_violations) and (not slop_findings)
        data = {"passed": passed,
                "slop_findings": slop_findings,
                "suppressions_added": suppressions_added,
                "ast_violations": ast_violations}
        if not ctx.obj["JSON"]:
            if passed:
                click.echo("✅ audit passed")
            else:
                click.echo(
                    f"❌ audit failed: "
                    f"{len(ast_violations)} AST/antipattern violation(s), "
                    f"{len(slop_findings)} slop finding(s)")
        out(ctx, f"audit passed: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "audit-code", e)


TEST_PATH_HINTS = ("/test_", "/tests/", "test_", "_test.",
                  ".test.", ".spec.")


def _is_test_path(path):
    lowered = path.lower()
    return (any(hint in lowered for hint in TEST_PATH_HINTS)
            or os.path.basename(lowered).startswith("test"))


# Directories never worth walking for impact/scope analysis: VCS,
# dependency installs, build output, caches, and test artifacts. Pruned
# in place during os.walk (see _prune_walk_dirs) so large checkouts
# (69k+ files under .venv/, dist/, test-results/) stay fast.
SKIP_WALK_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".td_rag", ".worktrees", "test-results",
    "test_results", ".nyc_output", "coverage",
})


def _prune_walk_dirs(dirnames):
    """Drop heavy/irrelevant dirs from an os.walk traversal in place."""
    dirnames[:] = [d for d in dirnames
                   if d not in SKIP_WALK_DIRS
                   and not d.startswith(".tmp")
                   and not d.endswith(".egg-info")]
    return dirnames


def _impact_dependents(worktree, changed):
    """Files referencing a changed module (import/from/require).

    Returns {changed_path: [dependent paths]}. Best effort, read-only.
    """
    dependents = {path: [] for path in changed}
    stems = {}
    for path in changed:
        base = os.path.basename(path)
        stem, _ = os.path.splitext(base)
        stems.setdefault(stem, []).append(path)
    if not stems:
        return dependents
    for dirpath, dirnames, filenames in os.walk(worktree):
        _prune_walk_dirs(dirnames)
        for name in filenames:
            if not name.endswith((".py", ".ts", ".tsx", ".js",
                                   ".jsx", ".mjs")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, worktree)
            if rel in dependents:
                continue
            try:
                with open(full, encoding="utf-8",
                          errors="ignore") as handle:
                    content = handle.read()
            except OSError:
                continue
            for stem, owners in stems.items():
                if not stem or len(stem) < 3:
                    continue
                escaped = re.escape(stem)
                import_ref = (
                    r"(?:from|import|require)[^\n]{0,120}?" + escaped)
                path_ref = (r"(?:^|[^a-zA-Z0-9_])" + escaped +
                            r"(?:\.[a-zA-Z_]|/)")
                if (re.search(import_ref, content)
                        or re.search(path_ref, content)):
                    for owner in owners:
                        dependents[owner].append(rel)
    for owner in dependents:
        dependents[owner] = sorted(set(dependents[owner]))
    return dependents


@cli.command(name="audit-impact")
@click.option("--worktree", "worktree", required=True,
              help="Path to the worktree to analyze")
@click.option("--top-k", "top_k", default=25, type=int,
              help="Maximum impacted files to list")
@click.option("--preview-url", "preview_url", default=None,
              help="Base URL of a live preview for the visual/DOM audit "
                   "of UI changes. Falls back to PREVIEW_URL.")
@_gate_json_option
@click.pass_context
def audit_impact_gate(ctx, worktree, top_k, preview_url):
    """Blast-radius analysis for worktree changes (exit 0 iff clean).

    Emits {"impacted_files", "dependent_tests", "violations",
    "ui_changed", "visual_diff"} where violations are AST findings
    on changed files. When changed files touch UI templates/styles
    and a preview URL is available, a remote-CDP snapshot is captured
    via browserless (never a local Chrome) and attached as
    "visual_diff"; an unreachable browser fails the gate. Nonzero
    exit when any violation exists.
    """
    from dev_tools.services.ast_audit import ASTAuditor
    try:
        changed = [p for p in _worktree_changed_files(worktree)
                   if not p.startswith((".td_rag/", ".worktrees/"))]
        auditor = ASTAuditor()
        violations = []
        for rel in changed:
            if not rel.endswith((".py", ".ts", ".tsx", ".js",
                                  ".jsx", ".mjs")):
                continue
            full = os.path.join(worktree, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, encoding="utf-8",
                          errors="ignore") as handle:
                    code = handle.read()
                for finding in auditor.audit_file(rel, code) or []:
                    violations.append({
                        "file": rel,
                        "rule": finding.get("rule"),
                        "message": finding.get("message"),
                        "line": finding.get("line"),
                        "severity": finding.get("severity"),
                    })
            except Exception:
                continue
        dependents = _impact_dependents(worktree, changed)
        impacted = sorted(set(changed)
                          | {d for deps in dependents.values()
                             for d in deps})[:top_k]
        dependent_tests = sorted(
            {d for deps in dependents.values() for d in deps
             if _is_test_path(d)}
            | {p for p in changed if _is_test_path(p)})[:top_k]
        ui_extensions = {".tsx", ".jsx", ".vue", ".html",
                         ".css", ".scss"}
        ui_changed = any(Path(f).suffix in ui_extensions
                         for f in changed)
        preview = preview_url or os.environ.get("PREVIEW_URL")
        visual_diff = None
        visual_error = None
        if ui_changed and preview:
            from dev_tools.services.browser_cdp import (
                capture_dom_and_visual_snapshot)
            snap = capture_dom_and_visual_snapshot(
                target_url=preview,
                output_dir=Path(worktree) / ".td_rag" / "snapshots",
            )
            visual_diff = snap.to_dict()
            if not snap.reachable:
                visual_error = snap.error or "BROWSER_UNREACHABLE"
        passed = not violations and visual_error is None
        data = {"passed": passed,
                "impacted_files": impacted,
                "dependent_tests": dependent_tests,
                "violations": violations,
                "ui_changed": ui_changed,
                "visual_diff": visual_diff}
        if visual_error:
            data["error"] = visual_error
        if not ctx.obj["JSON"]:
            if passed:
                click.echo(
                    f"✅ impact clean: {len(impacted)} file(s), "
                    f"{len(dependent_tests)} test(s)")
            else:
                click.echo(
                    f"❌ impact: {len(violations)} violation(s) in "
                    f"{len(impacted)} file(s)")
        out(ctx, f"impact clean: {passed}.", data=data)
        if not passed:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "audit-impact", e)


def main():
    # click entry point automatically handles sys.argv
    try:
        cli(obj={})
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
