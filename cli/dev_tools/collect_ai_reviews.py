import sys
import os
import json
from typing import List, Dict, Any

try:
    from tdw_services.services.github import GitHubClient
    from dev_tools.dev_tools_sdk.config import load_project_config
except ImportError:
    print("Error: Could not import tdw_services or dev_tools_sdk. Ensure you have run `pip install -e dev-tools/` and your PYTHONPATH is set correctly (e.g., `export PYTHONPATH=$PYTHONPATH:$(pwd)/dev-tools`).")
    sys.exit(1)

# Configuration-driven allow-list for AI review bot sources
PROJECT_CONFIG = load_project_config()
ALLOWED_AI_BOTS = PROJECT_CONFIG.allowed_bots

def detect_ai_source(body: str) -> str:
    """Parses comment body to detect the AI source."""
    body_lower = body.lower()
    if "github models" in body_lower or "github-models" in body_lower:
        return "github-models"
    elif "gemini" in body_lower:
        return "gemini"
    elif "repoauditor" in body_lower or "technical audit" in body_lower:
        return "repo-auditor"
    return "unknown"

def is_ai_review(body: str) -> bool:
    """Checks if a comment body matches AI review signatures."""
    return "AI Review" in body or "Gemini Code Review Agent" in body or "<!-- ai-review-count" in body

def filter_ai_comments(comments: List[Dict[str, Any]], pr_number: int, comment_type: str) -> List[Dict[str, Any]]:
    """Filters generic comments to extract only AI reviews."""
    fetched_comments = []
    for comment in comments:
        user_login: str = comment.get('user', {}).get('login', '')

        # Generic bot check or specific allow-list
        is_bot = 'bot' in user_login.lower() or user_login in ALLOWED_AI_BOTS

        if is_bot:
            body = comment.get('body', '')
            if is_ai_review(body):
                source = detect_ai_source(body)

                # If the user is a human but it doesn't have a clear AI signature,
                # we'll fallback to their username if it's unknown.
                if source == "unknown" and user_login not in ALLOWED_AI_BOTS and 'bot' not in user_login.lower():
                    source = f"user-{user_login}"
                elif source == "unknown":
                    source = "github-actions" # generic bot

                fetched_comments.append({
                    'type': comment_type,
                    'pr': pr_number,
                    'bot': user_login,
                    'source': source,
                    'body': body,
                    'html_url': comment.get('html_url', '')
                })
    return fetched_comments

def fetch_comments_for_pr(client: GitHubClient, repo: str, pr_number: int, endpoint: str, comment_type: str) -> List[Dict[str, Any]]:
    """Fetches comments for a given PR endpoint and applies filtering."""
    try:
        comments = client._request('GET', f'/repos/{repo}/{endpoint}/{pr_number}/comments')
        return filter_ai_comments(comments, pr_number, comment_type)
    except Exception as e:
        print(f"Error fetching {comment_type} comments for PR #{pr_number}: {e}")
        return []

def collect_reviews(client: GitHubClient, repo: str, pr_limit: int = 50) -> List[Dict[str, Any]]:
    """Main workflow to collect reviews from recent PRs."""
    print("Fetching PRs...")
    prs = client._request('GET', f'/repos/{repo}/pulls?state=all&per_page=100')

    ai_comments: List[Dict[str, Any]] = []
    print(f"Collecting AI review comments from the last {pr_limit} PRs...")

    for pr in prs[:pr_limit]:
        pr_number = pr['number']
        ai_comments.extend(fetch_comments_for_pr(client, repo, pr_number, 'issues', 'issue'))
        ai_comments.extend(fetch_comments_for_pr(client, repo, pr_number, 'pulls', 'review'))

    return ai_comments

def main() -> None:
    try:
        client = GitHubClient()
        repo = client.repo

        if not isinstance(repo, str) or not repo:
            raise ValueError("GitHub repository could not be determined or is not a string.")

        ai_comments = collect_reviews(client, repo)

        with open('ai_reviews_summary.json', 'w') as f:
            json.dump(ai_comments, f, indent=2)

        print(f"Done! Collected {len(ai_comments)} AI review comments in ai_reviews_summary.json")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
