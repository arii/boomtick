import sys
import os
from tdw_services.utils import log_info
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
import click
from tdw_services.orchestrator import Orchestrator
from tdw_services.utils import get_or_create_log_dir

# Import legacy utils for backwards compatibility during migration
from repo_utils import walk_tsx, find_patterns_in_file, get_bundle_size, get_any_count
from scope_check import verify_pr_scope
import os
from utils import get_github_client, get_repo_name, CLIError, run_command, set_gha_variable, get_gha_variable
from dev_tools_sdk.config import load_project_config

PROJECT_CONFIG = load_project_config()

# CLI Group
@click.group()
@click.option('--json/--no-json', 'json_output', default=True, help='Output results in JSON format (default: True)')
@click.pass_context
def cli(ctx, json_output):
    """Unified Tech-Dancer DevTools CLI"""
    ctx.ensure_object(dict)
    # If the user explicitly passed --no-json (if supported) or we want to detect if it's a TTY
    # But for now, we follow the requirement to be JSON by default for machine consumption.
    ctx.obj['JSON'] = json_output
    ctx.obj['ORCHESTRATOR'] = Orchestrator()

# --- Utility Helpers ---
def out(ctx, msg, data=None):
    if ctx.obj['JSON']:
        payload = {"status": "success"}
        if data: payload.update(data)
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(msg)

def err(ctx, msg, code=1, data=None):
    if ctx.obj['JSON']:
        payload = {"status": "error", "message": msg, "code": code}
        if data: payload.update({"data": data})
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(f"❌ Error: {msg}", err=True)
    sys.exit(code)

def _handle_unexpected_error(ctx, command_name, e):
    from tdw_services.utils import log_error
    log_error(f"Unexpected error in {command_name}: {e}")
    err(ctx, f"An unexpected error occurred in {command_name}.")

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
# REPO COMMAND GROUP
# ==========================================
@cli.group()
def repo():
    """Repository Operations"""
    pass

@repo.command()
@click.option('--grep')
@click.option('--worktree')
@click.pass_context
def run_playwright(ctx, grep, worktree):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_playwright(grep=grep, worktree_path=worktree)
    out(ctx, f"Playwright run complete.", data=res)

@repo.command()
@click.argument('pr_number', type=int)
@click.option('--all', 'include_all', is_flag=True, help='Include logs for successful runs')
@click.option('--clean', is_flag=True, help='Clean and extract failing details from logs')
@click.pass_context
def ci_logs(ctx, pr_number, include_all, clean):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.get_ci_logs(pr_number, include_all=include_all)
    out(ctx, f"Fetched CI logs for PR #{pr_number}", data=res)


@repo.command()
@click.argument('pr_number', type=int)
@click.option('--grep', help='Filter logs by pattern')
@click.pass_context
def logs(ctx, pr_number, grep):
    orch = ctx.obj['ORCHESTRATOR']
    logs_content = orch.stream_ci_logs(pr_number, grep=grep)
    out(ctx, f"Fetched logs for PR #{pr_number}", data={"logs": logs_content})

# ==========================================
# GH COMMAND GROUP
# ==========================================
@cli.group()
def gh():
    """GitHub Operations"""
    pass

@gh.command()
@click.option('--state', default='open')
@click.option('--limit', type=int, default=100)
@click.option('--include-drafts/--no-include-drafts', default=True)
@click.option('--labels')
@click.pass_context
def search_prs(ctx, state, limit, include_drafts, labels):
    orch = ctx.obj['ORCHESTRATOR']
    label_list = labels.split(',') if labels else None
    res = orch.list_prs(state=state, limit=limit, include_drafts=include_drafts, labels=label_list)
    out(ctx, f"Found {len(res['prs'])} PRs.", data=res)

@gh.command()
@click.argument('pr_number', type=int)
@click.option('--base', default=PROJECT_CONFIG.base_branch_name)
@click.pass_context
def merge_conflicts(ctx, pr_number, base):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.get_merge_conflicts(pr_number, base_branch=base)
    out(ctx, f"Checked merge conflicts for PR #{pr_number}", data=res)

@gh.command()
@click.argument('pr_number', type=int)
@click.pass_context
def pr_diff(ctx, pr_number):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.get_pr_diff_shapen(pr_number)
    out(ctx, f"Fetched diff for PR #{pr_number}", data=res)

@gh.command()
@click.argument('pr_number', type=int)
@click.pass_context
def view(ctx, pr_number):
    orch = ctx.obj['ORCHESTRATOR']
    pr = orch.github.fetch_pr_details(pr_number)
    out(ctx, f"PR #{pr.get('number')}: {pr.get('title')}\nState: {pr.get('state')}", data={"pr": pr})

@gh.command()
@click.argument('file', required=False)
@click.option('--base')
@click.pass_context
def resolve(ctx, file, base):
    orch = ctx.obj['ORCHESTRATOR']
    if file:
        if orch.resolve_conflict(file):
            out(ctx, f"✅ Resolved conflicts in {file}", data={"resolved_file": file})
        else:
            err(ctx, f"Failed to resolve conflicts in {file}")
    else:
        resolved = orch.resolve_conflicts_headless()
        out(ctx, f"✅ Resolved {len(resolved)} files.", data={"resolved": resolved})

@gh.command()
@click.option('--check-dirs', default=os.environ.get('AUDIT_CHECK_DIRS', ','.join(PROJECT_CONFIG.audit_check_dirs)), help='Comma-separated list of directories to audit')
@click.pass_context
def audit(ctx, check_dirs):
    """Run a headless UI audit on the codebase."""
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.get_audit_results(targets=check_dirs.split(','))
    out(ctx, "Headless audit complete.", data=res)

@gh.command()
@click.argument('pr_number', type=int)
@click.option('--fetch', is_flag=True)
@click.option('--audit', 'run_audit', is_flag=True)
@click.option('--submit', is_flag=True)
@click.option('--cleanup', is_flag=True)
@click.option('--dry-run/--execute', default=True)
@click.option('--base')
@click.option('--event')
@click.pass_context
def audit_pr(ctx, pr_number, fetch, run_audit, submit, cleanup, dry_run, base, event):
    orch = ctx.obj['ORCHESTRATOR']
    try:
        res = orch.audit_pr(pr_number, fetch=fetch, audit=run_audit, submit=submit, cleanup=cleanup, dry_run=dry_run, event=event)
        out(ctx, f"✅ Audit PR #{pr_number} action complete.", data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)

@gh.command()
@click.option('--title', required=True, help='Issue title')
@click.option('--file', help='Path to file containing issue body')
@click.option('--body', help='Literal body text')
@click.pass_context
def create_issue(ctx, title, file, body):
    """Create a new GitHub issue."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        content = _get_body_content(ctx, orch, file, body)
        res = orch.create_issue(title, content)
        out(ctx, f"✅ Successfully created issue: {res.get('html_url')}", data={"issue": res})
    except CLIError as e:
        err(ctx, str(e), code=e.code)
    except Exception as e:
        _handle_unexpected_error(ctx, "create-issue", e)

@gh.command()
@click.argument('issue_number', type=int)
@click.pass_context
def issue_view(ctx, issue_number):
    """View details of a GitHub issue."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        issue = orch.get_issue_details(issue_number)
        msg = f"Issue #{issue.get('number')}: {issue.get('title')}\nState: {issue.get('state')}\n\n{issue.get('body')}"
        out(ctx, msg, data={"issue": issue})
    except CLIError as e:
        err(ctx, str(e), code=e.code)
    except Exception as e:
        _handle_unexpected_error(ctx, "issue-view", e)

@gh.command()
@click.argument('issue_number', type=int)
@click.option('--file', help='Path to file containing new issue body')
@click.option('--body', help='Literal body text')
@click.pass_context
def issue_update(ctx, issue_number, file, body):
    """Update a GitHub issue's body."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        content = _get_body_content(ctx, orch, file, body)
        res = orch.update_issue_body(issue_number, content)
        out(ctx, f"✅ Successfully updated issue #{issue_number}", data={"issue": res})
    except CLIError as e:
        err(ctx, str(e), code=e.code)
    except Exception as e:
        _handle_unexpected_error(ctx, "issue-update", e)

@gh.command()
@click.argument('issue_number', type=int)
@click.option('--file', help='Path to file containing comment body')
@click.option('--body', help='Literal body text')
@click.pass_context
def issue_comment(ctx, issue_number, file, body):
    """Post a comment to a GitHub issue."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        content = _get_body_content(ctx, orch, file, body)
        res = orch.post_comment(issue_number, content)
        out(ctx, f"✅ Successfully posted comment to issue #{issue_number}", data={"comment": res})
    except CLIError as e:
        err(ctx, str(e), code=e.code)
    except Exception as e:
        _handle_unexpected_error(ctx, "issue-comment", e)

@gh.command()
@click.option('--issue-number', type=int)
@click.option('--all-open', is_flag=True)
@click.option('--post-comments', is_flag=True)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def validate_issue(ctx, issue_number, all_open, post_comments, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.validate_issue(issue_number=issue_number, all_open=all_open, post_comments=post_comments, dry_run=dry_run)
    if not ctx.obj['JSON']:
        for issue in res['issues']:
            click.echo(f"{'✅' if not issue['findings'] else '❌'} #{issue['number']}: {issue['title'][:60]}")
            for f in issue['findings']: click.echo(f"   ❌ {f}")
            for w in issue['warnings']: click.echo(f"   ⚠️  {w}")
    if res['status'] == 'error':
        err(ctx, f"Found {res['total_findings']} blocking findings.", data=res)
    else:
        out(ctx, "✅ Issue validation complete.", data=res)

@gh.command()
@click.argument('target_branch')
@click.argument('pr_numbers', nargs=-1, type=int)
@click.pass_context
def aggregate(ctx, target_branch, pr_numbers):
    """Aggregate multiple PRs into a single branch."""
    if not pr_numbers:
        err(ctx, "Provide at least one PR number to aggregate.")
    orch = ctx.obj['ORCHESTRATOR']
    try:
        res = orch.aggregate_prs(target_branch, list(pr_numbers))
        out(ctx, res['message'], data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)

@gh.command()
@click.pass_context
def conflicts(ctx):
    orch = ctx.obj['ORCHESTRATOR']
    conflicts: List[Dict[str, Any]] = orch.handle_detect_conflicts()
    if not ctx.obj['JSON']:
        if not conflicts: click.echo("✅ No potential merge conflicts detected.")
        for c in conflicts:
            click.echo(f"⚠️  {' ↔ '.join(f'#{p}' for p in c['prs'])} share {len(c['files'])} file(s):")
            for f in sorted(c['files'])[:10]: click.echo(f"    - {f}")
    out(ctx, f"Found {len(conflicts)} potential conflicts.", data={"conflicts": conflicts})

@gh.command()
@click.option('--pr', required=True, type=int, help="The PR number to resolve conflicts for.")
@click.option('--allow-unrelated', is_flag=True, help="Allow merging unrelated histories.")
@click.option('--strategy', type=click.Choice(['ours', 'theirs']), help="Merge strategy option (-X ours/theirs).")
@click.option('--push', is_flag=True, help="Automatically push the resolution to origin.")
@click.pass_context
def resolve_conflicts(ctx, pr, allow_unrelated, strategy, push):
    """Resolve merge conflicts for a PR in a separate worktree."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        res = orch.resolve_pr_conflicts(pr, allow_unrelated=allow_unrelated, strategy=strategy, push=push)
        out(ctx, res['message'], data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)

@gh.command()
@click.argument('diff_input', required=False)
@click.pass_context
def verify_versions(ctx, diff_input):
    """Verify version changes in a diff for downgrades or hard blocks."""
    import subprocess
    import tempfile
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'verify_versions.py')

    if not diff_input:
        # If no input provided, try to get diff against main
        try:
            diff_input = run_command(["git", "diff", PROJECT_CONFIG.base_branch])
        except Exception as e:
            err(ctx, f"Failed to get git diff: {e}")

    # Use a temporary file to avoid E2BIG/ARG_MAX issues with large diffs
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
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
                    status = "error" if any(f['severity'] == 'error' for f in findings) else "success"
                    out(ctx, f"Found {len(findings)} version issues.", data={"status": status, "findings": findings})
                    if status == "error":
                        sys.exit(1)
                else:
                    out(ctx, "✅ No version issues detected.", data={"status": "success", "findings": []})
            except json.JSONDecodeError:
                err(ctx, f"Invalid validator output: {proc.stdout}")
        else:
            err(ctx, f"Validator failed: {proc.stderr}")
    except Exception as e:
        err(ctx, f"Error running validator: {e}")

@gh.command()
@click.option('--pr', type=int)
@click.pass_context
def detect_conflicts(ctx, pr):
    orch = ctx.obj['ORCHESTRATOR']
    conflicts = orch.handle_detect_conflicts(pr_num=pr)
    if not ctx.obj['JSON']:
        if not conflicts: click.echo("✅ No potential merge conflicts detected.")
        for c in conflicts:
            click.echo(f"⚠️  {' ↔ '.join(f'#{p}' for p in c['prs'])} share {len(c['files'])} file(s):")
            for f in sorted(c['files'])[:10]: click.echo(f"    - {f}")
    out(ctx, f"Found {len(conflicts)} potential conflicts.", data={"conflicts": conflicts})


@gh.command()
@click.option('--body', help="The comment body text.")
@click.option('--author-association', required=True, help="The author association (e.g. OWNER, MEMBER).")
@click.pass_context
def parse_comment(ctx, body, author_association):
    """Parse a comment body and return intended actions."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        # Security: Allow reading body from COMMENT_BODY env var to avoid shell injection in CI
        content = body if body else os.environ.get("COMMENT_BODY")
        if not content:
            err(ctx, "Comment body is required (use --body or COMMENT_BODY env var)")

        actions = orch.parse_comment(content, author_association)
        out(ctx, "Comment parsed successfully.", data={"actions": actions})
    except Exception as e:
        _handle_unexpected_error(ctx, "parse-comment", e)

@gh.command()
@click.option('--pr', required=True, type=int, help="The PR number to comment on.")
@click.option('--file', type=str, help="Path to the file containing the comment body.")
@click.option('--body', type=str, help="Literal comment text.")
@click.pass_context
def post_comment(ctx, pr, file, body):
    """Post a comment to a PR."""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        content = _get_body_content(ctx, orch, file, body)
        res = orch.post_comment(pr, content)
        out(ctx, f"✅ Successfully posted comment to PR #{pr}", data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)
    except Exception as e:
        _handle_unexpected_error(ctx, "post-comment", e)

@gh.command()
@click.pass_context
def status_board(ctx):
    orch = ctx.obj['ORCHESTRATOR']
    prs = orch.handle_status_board()
    if not ctx.obj['JSON']:
        click.echo("# Active Agent Work Board\n| Branch | Issue | Status |")
        for pr in prs:
            click.echo(f"| {pr['branch']} | {pr['issue']} | {pr['status']} |")
    out(ctx, f"Found {len(prs)} open PRs.", data={"work": prs})

@gh.command()
@click.option('--find')
@click.option('--migrate', nargs=2, type=str)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def migrate_tokens(ctx, find, migrate, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    matches = orch.migrate_tokens(find=find, migrate=migrate, dry_run=dry_run)
    out(ctx, f"Found {len(matches)} matches.", data={"matches": matches})

@gh.command()
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def update_issues(ctx, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    updates = orch.update_issues(dry_run=dry_run)
    out(ctx, f"Found {len(updates)} updates.", data={"updates": updates})

@gh.command()
@click.option('--check-responses', is_flag=True)
@click.option('--cleanup-comments', is_flag=True)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def manage_reviews(ctx, check_responses, cleanup_comments, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    prs = orch.manage_reviews(check_responses=check_responses, cleanup_comments=cleanup_comments, dry_run=dry_run)
    out(ctx, f"Checked {len(prs)} PRs.", data={"prs": prs})

@gh.command()
@click.pass_context
def audit_gate(ctx):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.handle_audit_gate()
    msg = f"UI Anti-Pattern Audit: Current={res['current']}, Baseline={res['baseline']}"
    if res['status'] == 'error':
        err(ctx, msg, data=res)
    else:
        out(ctx, msg, data=res)

@gh.command()
@click.option('--pr', required=True, type=int)
@click.option('--status', required=True)
@click.option('--auditor', required=True)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def track_review(ctx, pr, status, auditor, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.track_review(pr, status, auditor, dry_run=dry_run)
    out(ctx, f"✅ Updated tracking for PR #{pr}", data=res)

@gh.command()
@click.option('--baseline-file')
@click.option('--update', is_flag=True)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def ratchet_any(ctx, baseline_file, update, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.ratchet_any(update=update, baseline_file=baseline_file, dry_run=dry_run)
    msg = f"TypeScript 'any' Ratchet: Current={res['current']}, Baseline={res['baseline']}"
    if res['status'] == 'error':
        err(ctx, msg, data=res)
    else:
        out(ctx, msg, data=res)

@gh.command()
@click.option('--baseline-file')
@click.option('--threshold', type=int, default=50)
@click.option('--update', is_flag=True)
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def bundle_size(ctx, baseline_file, threshold, update, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.check_bundle_size(update=update, baseline_file=baseline_file, threshold=threshold, dry_run=dry_run)
    msg = f"Bundle Size Check: Current={res['size_kb']}KB, Baseline={res['baseline_kb']}KB"
    if res['status'] == 'error':
        err(ctx, msg, data=res)
    else:
        out(ctx, msg, data=res)

@cli.command()
@click.pass_context
def doctor(ctx):
    """Runtime Consistency Check"""
    orch = ctx.obj['ORCHESTRATOR']
    try:
        res = orch.runtime_check()
        out(ctx, f"✅ Runtime OK: node {res['node']}, pnpm {res['pnpm']}", data=res)
    except CLIError as e:
        err(ctx, str(e), code=e.code)

@gh.command()
@click.pass_context
def verify_metrics(ctx):
    """Verify CI metrics against established thresholds."""
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.verify_ci_metrics()
    if res['status'] == 'error':
        err(ctx, res['message'], data=res)
    else:
        out(ctx, res['message'], data=res)

@gh.command()
@click.pass_context
def summary_report(ctx):
    """Generate a markdown report of CI metrics for GHA Step Summary."""
    orch = ctx.obj['ORCHESTRATOR']
    report = orch.generate_ci_summary_report()
    # Always print as raw text to stdout for GHA redirection
    click.echo(report)

@gh.command()
@click.pass_context
def pre_submit(ctx):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.pre_submit_checks()
    out(ctx, "Pre-submit checks complete.", data={"results": res})

@gh.command()
@click.option('--limit', type=int, default=50, help='Limit the number of open PRs to process')
@click.option('--no-cache', is_flag=True, default=False, help='Bust the cache and force fetching data from GitHub')
@click.pass_context
def overlaps(ctx, limit, no_cache):
    """Identify and propose consolidation of PRs with high functional or structural overlap."""
    import subprocess
    import sys
    import os

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dev_tools', 'pr_overlap.py')
    cmd = [sys.executable, script_path, '--limit', str(limit)]
    if no_cache:
        cmd.append('--no-cache')

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
    pass

@ux.command()
@click.option('--route', help='Specific route to audit')
@click.option('--all-routes', is_flag=True, help='Audit all discovered routes')
@click.option('--desktop', is_flag=True, help='Audit desktop viewports')
@click.option('--mobile', is_flag=True, help='Audit mobile viewports')
@click.pass_context
def audit(ctx, route, all_routes, desktop, mobile):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_ux_audit(route=route, all_routes=all_routes, desktop=desktop, mobile=mobile)
    out(ctx, "UX Audit complete.", data=res)

@ux.command()
@click.pass_context
def report(ctx):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.generate_ux_report()
    out(ctx, "UX Report generated.", data=res)

@ux.command()
@click.option('--route', help='Specific route for Lighthouse')
@click.pass_context
def lighthouse(ctx, route):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_lighthouse(route=route)
    out(ctx, "Lighthouse audit complete.", data=res)

@ux.command()
@click.option('--route', help='Specific route for screenshots')
@click.pass_context
def screenshots(ctx, route):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_ux_audit(route=route, screenshots_only=True)
    out(ctx, "Screenshots captured.", data=res)

@ux.command()
@click.option('--route', help='Specific route for image audit')
@click.pass_context
def images(ctx, route):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_ux_audit(route=route, images_only=True)
    out(ctx, "Image audit complete.", data=res)

@ux.command()
@click.option('--route', help='Specific route for contrast check')
@click.pass_context
def contrast(ctx, route):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_ux_audit(route=route, contrast_only=True)
    out(ctx, "Contrast check complete.", data=res)

@ux.command()
@click.option('--route', help='Specific route for overflow check')
@click.pass_context
def overflow(ctx, route):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.run_ux_audit(route=route, overflow_only=True)
    out(ctx, "Overflow check complete.", data=res)

@cli.command()
@click.pass_context
def build(ctx):
    """Build the project after runtime check"""
    orch = ctx.obj['ORCHESTRATOR']
    orch.runtime_check()
    run_command(["pnpm", "run", "build"])
    out(ctx, "✅ Build complete")

@cli.command()
@click.pass_context
def lint(ctx):
    """Lint the project after runtime check"""
    orch = ctx.obj['ORCHESTRATOR']
    orch.runtime_check()
    run_command(["pnpm", "run", "lint"])
    out(ctx, "✅ Lint complete")

@cli.group()
def test():
    """Testing Operations"""
    pass

@test.command(name='cli')
@click.pass_context
def test_cli(ctx):
    """Run CLI package tests"""
    orch = ctx.obj['ORCHESTRATOR']
    orch.runtime_check()
    # pytest options are now in pyproject.toml
    import subprocess
    import sys
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
    pass

@ai.command()
@click.argument('pr_number', type=int)
@click.option('--no-cache', is_flag=True, default=False, help='Bust the diff cache and force a fresh review call')
@click.pass_context
def review(ctx, pr_number, no_cache):
    import glob

    # Optionally bust the review cache so stale results are not silently returned
    if no_cache:
        review_dir = get_or_create_log_dir("reviews")
        pattern = os.path.join(review_dir, f"review_cache_{pr_number}_*.json")
        removed = glob.glob(pattern)
        for f in removed:
            import os as _os
            _os.remove(f)
        if removed:
            log_info(f"🗑  Removed {len(removed)} cached diff file(s): {removed}")
        else:
            log_info("ℹ️  No cache files found to remove.")

    orch = ctx.obj['ORCHESTRATOR']
    res = orch.review_pr(pr_number)

    # Surface errors clearly
    if isinstance(res, dict) and res.get('recommendation') == 'Not Approved' and not res.get('reviewComment', '').strip().startswith('CI'):
        # Likely an error result – dump full dict to stderr for diagnosis
        log_info(f"""⚠️  Review returned 'Not Approved' (may indicate an error).
    recommendation : {res.get('recommendation')}
    reviewComment  : {res.get('reviewComment', '')[:500]}""")

    out(ctx, f"✅ Generated review for PR #{pr_number}", data=res)

@ai.command()
@click.argument('file')
@click.pass_context
def analyze(ctx, file):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.analyze_file(file)
    out(ctx, f"✅ Analyzed {file}", data={"result": res})

@ai.command()
@click.option('--pr', required=True, type=int)
@click.option('--command', required=True)
@click.option('--comment-id')
@click.pass_context
def comment(ctx, pr, command, comment_id):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.handle_comment_command(pr, command, comment_id)
    if res.get('status') == 'error':
        err(ctx, res.get('message'), data=res)
    else:
        out(ctx, res.get('message'), data=res)

# ==========================================
# AGENT COMMAND GROUP
# ==========================================
@cli.group(name='agent')
def agent_group():
    """Agent Operations"""
    pass

@agent_group.command()
@click.argument('branch')
@click.argument('task')
@click.pass_context
def dispatch(ctx, branch, task):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.dispatch_jules_review(branch, task)
    out(ctx, f"✅ Dispatched task on branch {branch}", data=res)



@agent_group.command()
@click.pass_context
def sync(ctx):
    """Sync active agent sessions."""
    orch = ctx.obj['ORCHESTRATOR']
    sessions = orch.jules.list_sessions()

    if not ctx.obj['JSON']:
        if not sessions:
            click.echo("No active agent sessions found.")
        else:
            click.echo(f"{'Session ID':<20} | {'Status':<15} | {'Created':<25}")
            click.echo("-" * 65)
            for s in sessions:
                sid = s.get('name', 'N/A').split('/')[-1]
                state = s.get('state', 'UNKNOWN')
                created = s.get('createTime', 'N/A')
                click.echo(f"{sid:<20} | {state:<15} | {created:<25}")

    out(ctx, "Agent sync complete.", data={"sessions": sessions})

@agent_group.command()
@click.option('--pr-number', type=int)
@click.option('--branch')
@click.option('--api-key')
@click.option('--dry-run/--execute', default=True)
@click.pass_context
def fix_ci(ctx, pr_number, branch, api_key, dry_run):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.fix_ci(pr_number=pr_number, branch=branch, api_key=api_key, dry_run=dry_run)
    agent_name = res.get('agent_name', 'Jules')
    out(ctx, f"🚀 Initialized {agent_name} session for branch `{res['branch']}`", data=res)

@agent_group.command()
@click.option('--log')
@click.option('--file')
@click.option('--pr', type=int)
@click.pass_context
def repair_context(ctx, log, file, pr):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.repair_context(log=log, log_file=file, pr_number=pr)
    out(ctx, f"Generated {len(res)} prompts.", data={"prompts": res})

@agent_group.command()
@click.option('--logs')
@click.option('--stdin', is_flag=True)
@click.option('--worktree', is_flag=True)
@click.pass_context
def repair(ctx, logs, stdin, worktree):
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.repair_local(logs_path=logs, stdin=stdin, worktree=worktree)
    if res['status'] == 'success':
        out(ctx, res['message'], data=res)
    else:
        err(ctx, res['message'], data=res)

@agent_group.command()
@click.argument('session_id')
@click.pass_context
def messages(ctx, session_id):
    """Get message history for a Jules session."""
    orch = ctx.obj['ORCHESTRATOR']
    msgs = orch.jules.get_messages(session_id)
    if not ctx.obj['JSON']:
        if not msgs:
            click.echo(f"No messages found for session {session_id}")
        else:
            for m in msgs:
                role = m['role'].upper()
                click.echo(f"[{m['time']}] {role}:")
                click.echo(m['content'])
                click.echo("-" * 40)
    out(ctx, f"Messages retrieved for {session_id}", data={"messages": msgs})

@agent_group.command()
@click.argument('session_id')
@click.argument('message')
@click.pass_context
def send(ctx, session_id, message):
    """Send a message to an active Jules session."""
    orch = ctx.obj['ORCHESTRATOR']
    res = orch.jules.send_message(session_id, message)
    if res.get('status') == 'success':
        out(ctx, f"✅ Message sent to session {session_id}", data=res)
    else:
        err(ctx, f"Failed to send message: {res.get('message')}", data=res)

# Register aliases for backwards compatibility
@cli.group(name='jules')
def jules_group():
    """Agent Operations (alias for agent)"""
    pass

for group in [jules_group]:
    group.add_command(dispatch)
    group.add_command(sync)
    group.add_command(fix_ci)
    group.add_command(repair_context)
    group.add_command(repair)
    group.add_command(messages)
    group.add_command(send)


if __name__ == "__main__":
    cli(obj={})
