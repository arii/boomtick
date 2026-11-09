"""GitHub issue commands."""

import os
import subprocess
import sys
import click
from dev_tools.utils import verify_ci_metrics
from dev_tools.commands.core import _get_body_content
from dev_tools.commands.core import _handle_unexpected_error
from dev_tools.commands.core import err
from dev_tools.commands.core import get_config
from dev_tools.commands.core import json_option
from dev_tools.commands.core import limit_option
from dev_tools.commands.core import out
from dev_tools.commands.gh_pr import gh


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
@click.option(
    "--issue-number",
    "issue_number_opt",
    type=int,
    help="The GitHub issue number to view",
)
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def issue_view(ctx, issue_number_arg, issue_number_opt, repo):
    """View details of a GitHub issue."""
    issue_number = (
        issue_number_arg if issue_number_arg is not None else issue_number_opt
    )
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
@click.option(
    "--labels", help="Comma-separated list of labels to set (replaces existing labels)"
)
@click.option("--add-labels", help="Comma-separated list of labels to add")
@click.option("--remove-labels", help="Comma-separated list of labels to remove")
@click.option("--state", type=click.Choice(["open", "closed"]))
@click.option("--repo", help="Target repository override (e.g. owner/repo)")
@click.pass_context
def issue_update(
    ctx, issue_number, file, body, labels, add_labels, remove_labels, state, repo
):
    """Update a GitHub issue's body, labels, and/or state."""
    orch = ctx.obj["ORCHESTRATOR"]

    label_list = [l.strip() for l in labels.split(",")] if labels else None
    add_label_list = [l.strip() for l in add_labels.split(",")] if add_labels else None
    remove_label_list = (
        [l.strip() for l in remove_labels.split(",")] if remove_labels else None
    )

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
    out(
        ctx,
        f"✅ Successfully posted comment to issue #{issue_number}",
        data={"comment": res},
    )


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
            issue_number=issue_number,
            all_open=all_open,
            post_comments=post_comments,
            dry_run=dry_run,
        )

    if not ctx.obj["JSON"]:
        for issue in res["issues"]:
            issue_ref = (
                f"#{issue['number']}" if issue["number"] else f"File: {issue['title']}"
            )
            title_display = f": {issue['title'][:60]}" if issue["number"] else ""
            click.echo(
                f"{'✅' if not issue['findings'] else '❌'} {issue_ref}{title_display}"
            )
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
@click.option(
    "--repo", "-r", default=None, help="Target GitHub repository (e.g. owner/repo)"
)
@click.option(
    "--path",
    "root_path",
    default=None,
    help="Checkout for scope existence checks (default: git root)",
)
@click.option(
    "--write/--no-write",
    default=False,
    help="Write the improved body back to the issue",
)
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
            orch.update_issue(issueNumber=issue_number, body=improved, **extra)
        if not ctx.obj["JSON"]:
            if report["ready"]:
                click.echo(f"issue #{issue_number} is agent-ready")
            else:
                click.echo(
                    f"issue #{issue_number} NOT ready: "
                    f"missing headers {report['missing_headers']}, "
                    f"{len(report['scope'])} scope path(s)"
                )
            if not write:
                click.echo("--- improved body ---")
                click.echo(improved)
        out(
            ctx,
            f"issue #{issue_number} ready: {report['ready']}.",
            data={"issue": issue_number, "wrote": write, "body": improved, **report},
        )
        if not report["ready"]:
            sys.exit(1)
    except Exception as e:
        _handle_unexpected_error(ctx, "gh spec-issue", e)


@gh.command()
@click.option("--body", help="The comment body text.")
@click.option(
    "--author-association",
    required=True,
    help="The author association (e.g. OWNER, MEMBER).",
)
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
@click.option(
    "--pr",
    "--pr-number",
    "pr",
    required=True,
    type=int,
    help="The PR number to comment on.",
)
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
