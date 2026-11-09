"""GitHub pull-request commands."""

import json
import os
import subprocess
import sys
import tempfile
import click
from dev_tools.utils import CLIError, run_command
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import cli
from dev_tools.commands.core import err
from dev_tools.commands.core import get_config
from dev_tools.commands.core import json_option
from dev_tools.commands.core import limit_option
from dev_tools.commands.core import out


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

    res = orch.list_prs(
        state=state,
        limit=limit,
        includeDrafts=include_drafts,
        labels=label_list,
        **extra_kwargs,
    )
    out(ctx, f"Found {len(res['prs'])} PRs.", data=res)


@gh.command()
@click.argument("pr_number_arg", required=False, type=int)
@click.option(
    "--pr",
    "--pr-number",
    "pr_number_opt",
    type=int,
    help="The PR number to check merge conflicts for.",
)
@click.option(
    "--base", default=None, help="Base branch (defaults to configured base branch)"
)
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
@click.option(
    "--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to sync."
)
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
@click.option(
    "--pr",
    "--pr-number",
    "pr_number_opt",
    type=int,
    help="The PR number to fetch diff for.",
)
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
@click.option(
    "--pr", "--pr-number", "pr_number_opt", type=int, help="The PR number to view."
)
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
            prs_str = " ↔ ".join(f"#{p}" for p in c["prs"])
            files_count = len(c["files"])
            click.echo(f"⚠️  {prs_str} share {files_count} file(s):")
            for f in sorted(c["files"])[:10]:
                click.echo(f"    - {f}")
    out(
        ctx,
        f"Found {len(conflicts)} file overlap group(s).",
        data={"conflicts": conflicts},
    )


@gh.command()
@click.option(
    "--pr",
    "--pr-number",
    "pr",
    required=True,
    type=int,
    help="The PR number to resolve conflicts for.",
)
@click.option(
    "--allow-unrelated", is_flag=True, help="Allow merging unrelated histories."
)
@click.option(
    "--strategy",
    type=click.Choice(["ours", "theirs"]),
    help="Merge strategy option (-X ours/theirs).",
)
@click.option(
    "--push", is_flag=True, help="Automatically push the resolution to origin."
)
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
                    status = (
                        "error"
                        if any(f["severity"] == "error" for f in findings)
                        else "success"
                    )
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
@click.option(
    "--pr", "--pr-number", "pr", type=int, help="PR number to detect file overlap for"
)
@click.option(
    "--all", "all_prs", is_flag=True, help="Detect file overlap for all open PRs"
)
@click.pass_context
def detect_conflicts(ctx, pr, all_prs):
    (
        """Detect """
        """file overlap """
        """between open """
        """PRs (shared """
        """touched paths). """
        """This is """
        """NOT merge-conflict """
        """detection — """
        """for mergeability """
        """use GitHub """
        """mergeStateStatus/mergeable."""
    )
    if pr is not None and all_prs:
        err(ctx, "Provide either --pr or --all, not both")
    if pr is None and not all_prs:
        click.echo(
            "💡 Suggestion: Use 'td gh detect-conflicts --all' to explicitly scan all open PRs.",
            err=True,
        )
        all_prs = True
    orch = ctx.obj["ORCHESTRATOR"]
    conflicts = orch.handle_detect_conflicts(pr_num=pr, all_prs=all_prs)
    _render_conflicts(ctx, conflicts)


@gh.command(name="read-pr-reviews")
@click.option(
    "--pr",
    "--pr-number",
    "pr_number",
    required=True,
    type=int,
    help="The PR number to fetch top-level reviews for.",
)
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def read_pr_reviews(ctx, pr_number, repo):
    """Fetch top-level reviews for a PR."""
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    reviews = orch.github.fetch_reviews(pr_number, **extra_kwargs)
    out(
        ctx,
        f"Fetched {len(reviews)} reviews for PR #{pr_number}",
        data={"reviews": reviews, "review_count": len(reviews)},
    )


@gh.command(name="list-pr-commits")
@click.option(
    "--pr",
    "--pr-number",
    "pr_number",
    required=True,
    type=int,
    help="The PR number to list commits for.",
)
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def list_pr_commits(ctx, pr_number, repo):
    """List commits for a PR."""
    if pr_number <= 0:
        err(ctx, "PR number must be a positive integer.")
    orch = ctx.obj["ORCHESTRATOR"]
    extra_kwargs = {"repo": repo} if repo else {}
    raw_commits = orch.github.fetch_pr_commits(pr_number, **extra_kwargs)
    commits = (
        [
            {
                "sha": c.get("sha"),
                "author": c.get("commit", {}).get("author", {}).get("name")
                or c.get("author", {}).get("login"),
                "date": c.get("commit", {}).get("author", {}).get("date"),
                "message": c.get("commit", {}).get("message"),
            }
            for c in raw_commits
        ]
        if isinstance(raw_commits, list)
        else []
    )
    out(
        ctx,
        f"Fetched {len(commits)} commits for PR #{pr_number}",
        data={"commits": commits},
    )


@gh.command(name="pr-view")
@click.argument("pr_number_arg", required=False, type=int)
@click.option(
    "--pr",
    "--pr-number",
    "pr_number_opt",
    type=int,
    help="The PR number to fetch state for.",
)
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
@click.option(
    "--run",
    "--run-id",
    "run_id_opt",
    type=int,
    help="The workflow run ID to list jobs for.",
)
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
@click.option(
    "--pr",
    "--pr-number",
    "pr_number",
    required=True,
    type=int,
    help="The PR number to fetch comments for.",
)
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
