"""MCP, config, and repo command groups."""

import json
from dataclasses import asdict
import click
from dev_tools.utils import CLIError
from dev_tools.commands.core import cli
from dev_tools.commands.core import err
from dev_tools.commands.core import get_config
from dev_tools.commands.core import json_option
from dev_tools.commands.core import out


# ==========================================
# MCP COMMAND GROUP
# ==========================================


@cli.group()
def mcp():
    """MCP Discovery and Server Operations"""


@mcp.command(name="install")
@click.option(
    "--host",
    "-h",
    "hosts",
    multiple=True,
    help="Target specific host (antigravity, claude, cursor, codex)",
)
@click.option("--path", "custom_path", help="Custom path to host settings JSON file")
@click.option(
    "--command", "mcp_command", default="boomtick-mcp", help="Command to run MCP server"
)
@click.option(
    "--dry-run/--execute", default=True, help="Preview changes without updating files"
)
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
@click.option(
    "--host",
    "-h",
    "hosts",
    multiple=True,
    help="Target specific host (antigravity, claude, cursor, codex)",
)
@click.option("--path", "custom_path", help="Custom path to host settings JSON file")
@click.option(
    "--command", "mcp_command", default="boomtick-mcp", help="Command to run MCP server"
)
@click.option(
    "--dry-run/--execute", default=True, help="Preview changes without updating files"
)
@click.pass_context
def mcp_setup(ctx, hosts, custom_path, mcp_command, dry_run):
    """Alias for 'td mcp install'."""
    ctx.invoke(
        mcp_install,
        hosts=hosts,
        custom_path=custom_path,
        mcp_command=mcp_command,
        dry_run=dry_run,
    )


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
    out(ctx, "Playwright run complete.", data=res)


@repo.command()
@click.argument("pr_number", type=int)
@click.option(
    "--all", "include_all", is_flag=True, help="Include logs for successful runs"
)
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
