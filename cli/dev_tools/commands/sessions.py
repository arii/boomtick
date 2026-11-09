"""UX, session, skill, worktree, RAG, and multi-repo commands."""

import os
import sys
import click
from dev_tools.multi_repo import (
    discover_ecosystem_repos,
    exec_in_repos,
    get_repo_summary,
    warm_ecosystem_context,
)
from dev_tools.commands.core import _gate_json_option
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import err
from dev_tools.commands.core import out


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
    res = orch.run_ux_audit(
        route=route, all_routes=all_routes, desktop=desktop, mobile=mobile
    )
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


# --- Local Session Commands (parity with MCP agent tools) ---


@cli.group(name="session")
def session_group():
    """Local worktree session inspection and supervision."""


@session_group.command(name="status")
@click.argument("session_id")
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.pass_context
def session_status(ctx, session_id, root_path):
    """Show state, checkpoint, changed files and verification."""
    from dev_tools.services import local_sessions as ls

    try:
        root = ls.repo_root_for(root_path)
        session = ls.load_session(root, session_id)
        summary = ls.status_summary(session)
        if not ctx.obj["JSON"]:
            click.echo(
                f"Session {summary['sessionId']}: {summary['state']} "
                f"@ {summary['lastCheckpoint']}"
            )
            for name in summary["changedFiles"]:
                click.echo(f"  M {name}")
        out(
            ctx, f"Session {session_id}: {summary['state']}.", data={"session": summary}
        )
    except ls.SessionNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "session status", e)


@session_group.command(name="logs")
@click.argument("session_id")
@click.option("--tail", type=int, default=100, help="Lines of log to show")
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
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
        out(
            ctx,
            f"Session {session_id} logs ({total} total).",
            data={"sessionId": session_id, "logs": lines, "totalLines": total},
        )
    except ls.SessionNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "session logs", e)


@session_group.command(name="supervise", hidden=True)
@click.argument("session_id")
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
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
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
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
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.pass_context
def skill_read(ctx, name, root_path):
    """Print a skill's SKILL.md content."""
    from dev_tools.services import local_sessions as ls

    try:
        content = ls.read_skill(ls.repo_root_for(root_path), name)
        if not ctx.obj["JSON"]:
            click.echo(content)
        out(ctx, f"Skill {name}.", data={"skill": name, "content": content})
    except ls.SkillNotFound as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "skill read", e)


@cli.group(name="worktree")
def worktree_group():
    """Managed git worktrees under .worktrees (parity with MCP tools)."""


@worktree_group.command(name="create")
@click.argument("name", required=False)
@click.option(
    "--base",
    "base_branch",
    default="main",
    help="Base branch for the new worktree branch",
)
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.option(
    "--repo-root",
    "root_path",
    default=None,
    help="Repo root override (alias for --path)",
)
@click.option(
    "--issue",
    "issue_id",
    default=None,
    help="Issue number: provision warm issue worktree instead",
)
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
                click.echo(
                    f"{status['worktreeId']} {status['branch']} {status['path']}"
                )
            out(
                ctx,
                f"Worktree {status['worktreeId']} created.",
                data={"status": "ready", **status},
            )
            return
        wid, path, branch = wt.create(root, name, base_branch)
        if not ctx.obj["JSON"]:
            click.echo(f"{wid} {branch} {path}")
        out(
            ctx,
            f"Worktree {wid} created.",
            data={"worktreeId": wid, "path": path, "branch": branch},
        )
    except wt.WorktreeError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree create", e)


@worktree_group.command(name="list")
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.pass_context
def worktree_list(ctx, root_path):
    """List managed worktrees with branch, age and dirtiness."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import worktrees as wt

    try:
        items = wt.list_worktrees(ls.repo_root_for(root_path))
        if not ctx.obj["JSON"]:
            for item in items:
                click.echo(
                    f"{item['worktreeId']} {item['branch']} "
                    f"({item['changedFilesCount']} changed) "
                    f"{item['path']}"
                )
        out(ctx, f"{len(items)} worktree(s).", data={"worktrees": items})
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree list", e)


@worktree_group.command(name="remove")
@click.argument("worktree_id")
@click.option("--force", is_flag=True, help="Remove even with uncommitted changes")
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.pass_context
def worktree_remove(ctx, worktree_id, force, root_path):
    """Remove a managed worktree (refuses dirty ones unless --force)."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import worktrees as wt

    try:
        freed = wt.remove(ls.repo_root_for(root_path), worktree_id, force)
        if not ctx.obj["JSON"]:
            click.echo(f"removed {worktree_id}")
        out(
            ctx,
            f"Worktree {worktree_id} removed.",
            data={"status": "removed", "worktreeId": worktree_id, "freedBytes": freed},
        )
    except wt.WorktreeError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "worktree remove", e)


@cli.group(name="rag")
def rag_group():
    """Vector index: build incrementally, query with hybrid ranking."""


@rag_group.command(name="index")
@click.option(
    "--repo-root",
    "repo_root",
    default=None,
    help="Repo root to index (default: git root)",
)
@click.option(
    "--incremental/--full",
    default=True,
    help="Diff last indexed SHA (default) or rebuild everything",
)
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
            click.echo(
                f"indexed {len(data['updated_files'])} file(s), "
                f"{data['added_chunks']} chunk(s) "
                f"at {data['head_sha'][:8]}"
            )
        out(ctx, "index ready.", data=data)
    except Exception as e:
        _handle_unexpected_error(ctx, "rag index", e)


@rag_group.command(name="query")
@click.option(
    "--repo-root",
    "repo_root",
    default=None,
    help="Repo root whose index to query (default: git root)",
)
@click.option("--query", "query", required=True, help="Natural-language query text")
@click.option("--top-k", "top_k", default=8, type=int, help="Maximum hits to return")
@_gate_json_option
@click.pass_context
def rag_query(ctx, repo_root, query, top_k):
    """Query the repo vector index with hybrid ranking."""
    from dev_tools.services import local_sessions as ls
    from dev_tools.services import vector_store as vs

    try:
        root = ls.repo_root_for(repo_root)
        hits = vs.query_index(root, query, top_k=top_k)
        data = {"status": "success", "query": query, "hits": hits, "count": len(hits)}
        if not ctx.obj["JSON"]:
            for hit in hits:
                click.echo(
                    f"{hit['filepath']}:{hit['start_line']}: {hit['content'][:120]}"
                )
        out(ctx, f"{len(hits)} hit(s).", data=data)
    except Exception as e:
        _handle_unexpected_error(ctx, "rag query", e)


@cli.command(name="init")
@click.option(
    "--repo-root",
    "repo_root",
    default=None,
    help="Repo root to initialize (default: git root)",
)
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
        data = {
            "status": "ready",
            "head_sha": head_sha,
            "deps_synced": synced,
            "deps_note": deps_note,
            "main_note": main_note,
            "rag_indexed_sha": rag.get("last_indexed_sha", ""),
            "updated_files": rag.get("updated_files", []),
        }
        if not ctx.obj["JSON"]:
            click.echo(
                f"ready at {head_sha[:8]} "
                f"(deps synced: {synced}, "
                f"{len(data['updated_files'])} file(s) indexed)"
            )
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


def _register_multi_repo_commands(group):
    @group.command(name="list")
    @click.option(
        "--all",
        "include_all",
        is_flag=True,
        help="Include all auto-discovered sibling directories",
    )
    @click.pass_context
    def list_cmd(ctx, include_all):
        """List ecosystem repositories and local paths."""
        try:
            repos = discover_ecosystem_repos(
                explicit_config={} if include_all else None
            )
            repo_list = [
                {"name": name, "path": str(path)} for name, path in repos.items()
            ]
            if not ctx.obj.get("JSON", False):
                click.echo(f"Found {len(repo_list)} ecosystem repositories:")
                for r in repo_list:
                    click.echo(f"  • {r['name']:<25} {r['path']}")
            out(
                ctx,
                f"Discovered {len(repo_list)} repositories",
                data={"repos": repo_list, "total": len(repo_list)},
            )
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo list", e)

    @group.command(name="status")
    @click.option(
        "--repo",
        "-r",
        "filter_repos",
        multiple=True,
        help="Filter to specific repository name(s)",
    )
    @click.pass_context
    def status_cmd(ctx, filter_repos):
        """Show git, branch, and agent context status across ecosystem repositories."""
        try:
            filters = list(filter_repos) if filter_repos else None
            repos = discover_ecosystem_repos(filter_repos=filters)
            summaries = [get_repo_summary(name, path) for name, path in repos.items()]

            if not ctx.obj.get("JSON", False):
                click.echo(
                    f"{'Repository':<25} {'Branch':<20} {'Commit':<10} {'Dirty':<8} {'Context':<8}"
                )
                click.echo("-" * 75)
                for s in summaries:
                    dirty_str = "dirty" if s["is_dirty"] else "clean"
                    ctx_str = "yes" if s["has_context"] else "missing"
                    click.echo(
                        f"{s['repo']:<25} {s['branch']:<20} {s['commit']:<10} {dirty_str:<8} {ctx_str:<8}"
                    )

            out(
                ctx,
                f"Status for {len(summaries)} repositories",
                data={"repos": summaries, "total": len(summaries)},
            )
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo status", e)

    @group.command(name="context-warm")
    @click.option(
        "--repo",
        "-r",
        "filter_repos",
        multiple=True,
        help="Filter to specific repository name(s)",
    )
    @click.option(
        "--force", is_flag=True, help="Force re-generation of context even if not stale"
    )
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
                    click.echo(
                        f"  {status_icon} {r['repo']:<25} ({r['strategy']}, {r['duration_seconds']}s)"
                    )
                    if not r["passed"] and r.get("output"):
                        click.echo(f"     Error: {r['output']}")

            if res["status"] == "success":
                out(
                    ctx,
                    f"Context warmed across {res['total_repos']} repositories",
                    data=res,
                )
            else:
                err(
                    ctx,
                    f"Failed to warm context on {res['total_failed']} repositories",
                    data=res,
                )
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo context-warm", e)

    @group.command(name="exec")
    @click.argument("command")
    @click.option(
        "--repo",
        "-r",
        "filter_repos",
        multiple=True,
        help="Filter to specific repository name(s)",
    )
    @click.option(
        "--fail-fast/--continue-on-error",
        default=False,
        help="Stop on first error or continue",
    )
    @click.pass_context
    def exec_cmd(ctx, command, filter_repos, fail_fast):
        """Execute a shell command sequentially across ecosystem repositories."""
        try:
            filters = list(filter_repos) if filter_repos else None
            repos = discover_ecosystem_repos(filter_repos=filters)
            res = exec_in_repos(repos, command, continue_on_error=not fail_fast)

            if not ctx.obj.get("JSON", False):
                click.echo(
                    f"Executed '{command}' across {res['total_repos']} repositories:"
                )
                for r in res["results"]:
                    status_icon = "✅" if r["passed"] else "❌"
                    click.echo(
                        f"\n{status_icon} [{r['repo']}] (exit {r['exit_code']}, {r['duration_seconds']}s)"
                    )
                    if r["stdout"]:
                        click.echo(r["stdout"])
                    if r["stderr"]:
                        click.echo(f"Error output:\n{r['stderr']}")

            if res["status"] == "success":
                out(
                    ctx,
                    f"Command completed across {res['total_repos']} repositories",
                    data=res,
                )
            else:
                err(
                    ctx,
                    f"Command failed on {res['total_failed']} repositories",
                    data=res,
                )
        except Exception as e:
            _handle_unexpected_error(ctx, "multi-repo exec", e)


_register_multi_repo_commands(multi_repo_group)


_register_multi_repo_commands(repos_group)
