"""AI review and agent-fleet command groups."""

import glob
import json
import os
import sys
import importlib.util
from pathlib import Path
import click
from dev_tools.utils import get_or_create_log_dir, log_info
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import err
from dev_tools.commands.core import json_option
from dev_tools.commands.core import limit_option
from dev_tools.commands.core import out


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
    recommendation : {res.get("recommendation")}
    reviewComment  : {res.get("reviewComment", "")[:500]}""")

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
@click.option(
    "--pr", "--pr-number", "pr", required=True, type=int, help="The PR number."
)
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
@click.option(
    "--worktree", required=True, help="Existing worktree path for the session"
)
@click.option("--brief", required=True, help="Task brief for the executor")
@click.option("--model", default=None, help="Executor model override")
@click.option(
    "--repo", "-r", default=None, help="Target GitHub repository (e.g. owner/repo)"
)
@click.option(
    "--path", "root_path", default=None, help="Repo root override (default: git root)"
)
@click.option(
    "--detach/--foreground",
    default=False,
    help="Return immediately and supervise in background",
)
@click.pass_context
def run(ctx, worktree, brief, model, repo, root_path, detach):
    """Dispatch a local worktree session (fully local, no cloud API)."""
    from dev_tools.services import local_sessions as ls

    try:
        root = ls.repo_root_for(root_path)
        wt = (
            worktree if os.path.isabs(worktree) else os.path.join(os.getcwd(), worktree)
        )
        if not os.path.isdir(wt):
            err(ctx, f"Worktree path does not exist: {worktree}")
            return
        session = ls.new_session(wt, brief, model=model, repo=repo)
        ls.save_session(session)
        sid = session["sessionId"]
        if ls.exec_disabled():
            out(
                ctx,
                f"Session {sid} recorded (execution disabled).",
                data={"session": ls.status_summary(session), "executed": False},
            )
            return
        if detach:
            pid = ls.spawn_detached(root, sid)
            out(
                ctx,
                f"Session {sid} dispatched (supervisor pid {pid}).",
                data={"session": ls.status_summary(session), "supervisor_pid": pid},
            )
            return
        if not ctx.obj["JSON"]:
            click.echo(f"Session {sid} running in {wt}")
            code = ls.run_executor(root, session, stream=click.echo)
            click.echo(f"Session {sid} finished: {session['state']}")
        else:
            code = ls.run_executor(root, session)
        out(
            ctx,
            f"Session {sid} finished: {session['state']}.",
            data={"session": ls.status_summary(session), "exit_code": code},
        )
        if code:
            sys.exit(code)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent run", e)


@agent_group.command(name="submit-pr")
@click.option("--worktree", required=True, help="Worktree path holding the branch")
@click.option("--title", required=True, help="PR title")
@click.option("--body", default="", help="PR body")
@click.option("--base", default="main", help="Base branch for the PR")
@click.option(
    "--draft/--no-draft", default=True, help="Open as a draft for human review"
)
@click.option(
    "--issue",
    "issue_number",
    type=int,
    default=None,
    help="Gate changed files against this issue's scope",
)
@click.option(
    "--repo", "-r", default=None, help="Target GitHub repository (e.g. owner/repo)"
)
@click.option(
    "--skip-scope-check",
    is_flag=True,
    help="Bypass the scope gate (mirrors CI's [skip-scope-check])",
)
@click.pass_context
def submit_pr(
    ctx, worktree, title, body, base, draft, issue_number, repo, skip_scope_check
):
    """Push a worktree branch and open a PR (scope-gated with --issue)."""
    from dev_tools.services import submit_pr as sp

    try:
        wt = (
            worktree if os.path.isabs(worktree) else os.path.join(os.getcwd(), worktree)
        )
        issue_text = None
        if issue_number is not None:
            orch = ctx.obj["ORCHESTRATOR"]
            extra = {"repo": repo} if repo else {}
            details = orch.get_issue_details(issue_number, **extra)
            issue_text = details.get("title", "") + "\n" + (details.get("body") or "")
        res = sp.submit(
            wt,
            title,
            body,
            base,
            draft,
            repo,
            issue_text,
            skip_scope_check,
            issue=issue_number,
        )
        if not ctx.obj["JSON"]:
            click.echo(f"submitted {res['branch']} -> {res['url']}")
        out(ctx, f"PR submitted: {res['url']}.", data=res)
    except sp.SubmitError as e:
        err(ctx, str(e), code=1)
    except Exception as e:
        _handle_unexpected_error(ctx, "agent submit-pr", e)


@agent_group.command(name="verify-fleet")
@click.option(
    "--repos",
    multiple=True,
    default=None,
    help="Partner repositories to audit (default: tech-dancer, hrm, glossy)",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Output machine-readable JSON status"
)
@click.pass_context
def verify_fleet(ctx, repos, as_json):
    """Verify deep-agent assignment across partner repos."""
    from dev_tools import multi_repo as mr
    from dev_tools.services import local_sessions as ls

    try:
        from dev_tools.utils import get_github_client

        report = mr.verify_partner_deep_agents(
            get_github_client(), ls.repo_root_for(None), list(repos) or None
        )
        if not ctx.obj["JSON"] and not as_json:
            for name, info in report.items():
                click.echo(
                    f"{name}: reachable={info['reachable']} "
                    f"registered={info['registered']} "
                    f"issues={info['open_issues_count']} "
                    f"agent={info['agent_assigned_issues']} "
                    f"prs={info['open_agent_prs']} "
                    f"worktrees={info['active_worktrees']} "
                    f"healthy={info['healthy']}"
                )
        out(ctx, f"Verified {len(report)} partner repo(s).", data={"repos": report})
    except Exception as e:
        _handle_unexpected_error(ctx, "agent verify-fleet", e)


@agent_group.command(name="run-local")
@click.option(
    "--pr",
    "--pr-number",
    "pr_number",
    required=False,
    type=int,
    help="Pull Request number to evaluate.",
)
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
@click.option(
    "--pr",
    "--pr-number",
    "pr_number",
    required=True,
    type=int,
    help="Pull Request number",
)
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
        res = orch.plan_issue_audit(
            issue_numbers=list(issue_numbers), all_open=all_open, limit=limit
        )
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
        out(
            ctx,
            f"Workflow audit plan generated. Summary: {res['status_file']}",
            data=res,
        )
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
@click.option(
    "--dry-run/--execute",
    default=True,
    help="Preview mergeable PRs or merge each approved PR",
)
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
                    status_msg = (
                        "READY"
                        if item.get("is_eligible")
                        else f"REFUSED: {item.get('reason')}"
                    )
                    click.echo(f"  {status_icon} #{pr_num}: {title} [{status_msg}]")
                else:
                    status_icon = "✅" if item.get("merged") else "❌"
                    status_msg = item.get("message")
                    click.echo(f"  {status_icon} #{pr_num}: {title} [{status_msg}]")

        out(
            ctx,
            f"Evaluated {res['total_evaluated']} PRs ({res['eligible_count']} eligible).",
            data=res,
        )
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
