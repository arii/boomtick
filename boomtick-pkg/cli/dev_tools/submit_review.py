import os
import sys
import json
import re
from typing import Dict, Any, List
from tdw_services.utils import log_info, log_warn
from utils import get_github_token, get_github_client, get_repo_name, CLIError

def validate_review_payload(payload: Dict[str, Any]):
    """
    Validates that the review payload is not just boilerplate or empty.
    """
    if not isinstance(payload, dict):
        raise CLIError("Review rejected: Invalid payload format (expected dict).")

    body = payload.get("body", "")
    if not isinstance(body, str):
        body = str(body)

    comments = payload.get("comments", [])
    if not isinstance(comments, list):
        raise CLIError("Review rejected: 'comments' must be a list.")

    # Robust placeholder detection using regex to handle minor variants
    placeholders = [
        r"<findings\s*/?>",
        r"<summary\s*/?>",
        r"<filename\s*/?>",
        r"<feedback\s*/?>",
        r"<Approved\s*\|\s*Approved\s*with\s*Minor\s*Changes\s*\|\s*Not\s*Approved>"
    ]

    # Check body for placeholders
    for p in placeholders:
        if re.search(p, body, re.IGNORECASE):
             raise CLIError(f"Review rejected: Contains boilerplate placeholder matching '{p}'")

    # Check for real comments (not placeholders)
    real_comments = []
    for c in comments:
        if not isinstance(c, dict):
            continue

        c_body = str(c.get("body", ""))
        c_path = str(c.get("path", ""))

        # Check if comment fields contain placeholders
        is_placeholder = False
        for p in placeholders:
            if re.search(p, c_body, re.IGNORECASE) or re.search(p, c_path, re.IGNORECASE):
                is_placeholder = True
                break

        if is_placeholder:
            # We don't necessarily want to reject the WHOLE review if one comment has a placeholder
            # but usually it means the whole thing is slop. Following the stricter path:
            raise CLIError(f"Review rejected: Comment contains boilerplate placeholder.")

        if c_body.strip() and c_path != "<filename>":
            real_comments.append(c)

    # Check for empty/meaningless body
    # Remove markdown headers and comments to see if anything else remains
    clean_body = body
    clean_body = re.sub(r'^#+.*$', '', clean_body, flags=re.MULTILINE)
    clean_body = re.sub(r'<!--.*?-->', '', clean_body, flags=re.DOTALL)

    # Also remove the "selection" line if it wasn't replaced
    clean_body = re.sub(r'Approved\s*\|\s*Approved\s*with\s*Minor\s*Changes\s*\|\s*Not\s*Approved', '', clean_body, flags=re.IGNORECASE)

    clean_body = clean_body.strip()

    if not clean_body and not real_comments:
        raise CLIError("Review rejected: No meaningful content found in body or comments.")

def submit_review(pr_number, filepath, cleanup=False, dry_run=True, event_override=None, is_json=False):
    """
    Submits a PR review from a markdown file containing a JSON payload.
    """
    if not os.path.exists(filepath):
        raise CLIError(f"Review file missing: {filepath}")

    with open(filepath, 'r') as f:
        content = f.read()

    json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if not json_match:
        raise CLIError("Could not find JSON block in review document")

    try:
        payload = json.loads(json_match.group(1))
    except json.JSONDecodeError as e:
        raise CLIError(f"Failed to parse JSON block: {str(e)}")

    # Validate payload before proceeding
    validate_review_payload(payload)

    repo_name = get_repo_name()
    if not repo_name:
        raise CLIError("Could not detect repository name")

    repo = get_github_client().get_repo(repo_name)
    pr = repo.get_pull(int(pr_number))

    # CI Status Check Integration: Block approvals on failing CI
    from tdw_services.services.github import GitHubClient
    gh_client = GitHubClient()
    check_runs = gh_client.fetch_check_runs(pr.head.sha)
    failing_checks = [run.get('name') for run in check_runs if run.get('conclusion') == 'failure']

    event = event_override or ("REQUEST_CHANGES" if "Not Approved" in payload.get("body","") else "APPROVE" if "Approved" in payload.get("body","") else "COMMENT")

    if failing_checks and event == "APPROVE":
        event = "COMMENT"
        warning = f"> ⚠️ **BLOCKING CI FAILURE**: Approval overridden to COMMENT because the following checks are failing: {', '.join(failing_checks)}. Please resolve CI issues before approval.\n\n"
        payload["body"] = warning + payload.get("body", "")

    if not dry_run:
        import github
        def try_create_review(review_body, review_comments, review_event):
            try:
                pr.create_review(body=review_body, comments=review_comments, event=review_event)
            except github.GithubException as e:
                if e.status == 422:
                    error_msg = json.dumps(e.data) if getattr(e, 'data', None) else str(e)
                    if "Can not approve your own pull request" in error_msg and review_event != "COMMENT":
                        log_warn("Cannot approve own PR. Retrying as COMMENT...")
                        try_create_review(review_body, review_comments, "COMMENT")
                        return
                    if review_comments:
                        log_warn("Failed to post inline comments due to line resolution error. Retrying with body comments...")
                        fallback_body = review_body
                        fallback_body += "\n\n### Inline Comments (Fallback due to Github line resolution errors)\n"
                        for comment in review_comments:
                            fallback_body += f"- **{comment.get('path')}:{comment.get('line')}**: {comment.get('body')}\n"
                        try_create_review(fallback_body, [], review_event)
                        return
                raise e

        try_create_review(payload.get("body",""), payload.get("comments",[]), event)
        if event == "REQUEST_CHANGES":
            labels = [l.name for l in pr.labels]
            if "needs-design-system-fix" not in labels and any(k in payload.get("body","").lower() for k in ['tailwind', 'token']):
                pr.add_to_labels("needs-design-system-fix")

        if not is_json:
            log_info(f"✅ Submitted {event} for PR #{pr_number}")

        if cleanup:
            if os.path.exists(filepath):
                os.remove(filepath)
            ctx = filepath.replace('pr-review-', 'pr-context-')
            if os.path.exists(ctx):
                os.remove(ctx)
    else:
        if not is_json:
            log_info(f"[DRY-RUN] Would submit {event} for PR #{pr_number}")

    return {"status": "success", "event": event, "pr": pr_number}
