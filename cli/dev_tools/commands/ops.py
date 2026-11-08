"""Schema, doctor, build, lint, test, and context commands."""
import os
import subprocess
import sys
import re
import click
from dev_tools.utils import log_info, log_warn, run_command
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import err
from dev_tools.commands.core import get_config
from dev_tools.commands.core import out


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
                (
                    "Invalid "
                    "command path. "
                    "Only lowercase "
                    "alphanumeric, hyphens, "
                    "and underscores "
                    "separated by "
                    "single spaces "
                    "are allowed."
                ),
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
