"""GitHub pull-request resource."""
import json
import subprocess
from typing import Any, Dict, List, Optional
from dev_tools.utils import CLIError, log_warn
from dev_tools.utils.git import GitUtility
from dev_tools.services.gh.core import GitHubCoreMixin



class PullsMixin(GitHubCoreMixin):
    """GitHub pull-request resource."""

    def fetch_pr_files(self, number: int, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches the list of files changed in a PR."""
        target_repo = repo or self.repo
        # PR files usually don't change once a commit is pushed, but we'll use a shorter TTL
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}/files", ttl=600)

    def fetch_pr_details(self, number: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetch details for a pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}")

    def fetch_pr_diff(self, number: int, repo: Optional[str] = None) -> str:
        """Fetch the diff for a pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/pulls/{number}", is_text=True)

    def fetch_pr_info_graphql(self, number: int) -> Dict[str, Any]:
        """
        Fetches PR details and files in a single GraphQL request.

        Returns a dictionary containing:
            - "pr": A REST-compatible dict of PR details (title, body, user, head, base).
            - "files": A list of REST-compatible file dicts (each containing "filename").
        """
        if not self.repo:
            raise CLIError("Repository not configured.")
        owner, repo_name = self.repo.split("/", 1)
        query = """
        query getPrInfo($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              title
              body
              author {
                login
              }
              headRefName
              headRefOid
              baseRefName
              files(first: 100) {
                nodes {
                  path
                }
              }
            }
          }
        }
        """
        variables = {
            "owner": owner,
            "repo": repo_name,
            "prNumber": number,
        }

        res = self._request("POST", "/graphql", json_data={"query": query, "variables": variables})

        # Check for GraphQL errors
        if "errors" in res:
            errors_str = json.dumps(res["errors"])
            raise CLIError(f"GitHub GraphQL API Error: {errors_str}", code=400, data=res)

        pr_node = res.get("data", {}).get("repository", {}).get("pullRequest")
        if not pr_node:
            raise CLIError(f"Pull Request #{number} not found via GraphQL", code=404)

        author_node = pr_node.get("author") or {}
        author_login = author_node.get("login") if author_node else "unknown"

        pr_data = {
            "number": number,
            "title": pr_node.get("title", ""),
            "body": pr_node.get("body", ""),
            "user": {"login": author_login},
            "head": {
                "ref": pr_node.get("headRefName", ""),
                "sha": pr_node.get("headRefOid", ""),
            },
            "base": {
                "ref": pr_node.get("baseRefName", ""),
            }
        }

        files_node = pr_node.get("files") or {}
        nodes = files_node.get("nodes") or []
        files_data = [{"filename": node["path"]} for node in nodes if node and "path" in node]

        return {
            "pr": pr_data,
            "files": files_data,
        }

    def fetch_prs_for_commit(self, commit_sha: str) -> List[Dict[str, Any]]:
        """List pull requests containing a commit."""
        return self._request("GET", f"/repos/{self.repo}/commits/{commit_sha}/pulls")

    def search_pull_requests(self, query: str, limit: int = 10, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """General search for pull requests using the Search API."""
        target_repo = repo or self.repo
        full_query = f"repo:{target_repo} is:pr {query}"
        data = self._request("GET", "/search/issues", params={"q": full_query, "per_page": limit})
        items = data.get("items", []) if isinstance(data, dict) else []

        return [
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "body": pr.get("body"),
                "author": {"login": pr.get("user", {}).get("login")},
                "isDraft": pr.get("draft"),
                "updatedAt": pr.get("updated_at"),
                "url": pr.get("html_url"),
            }
            for pr in items[:limit]
        ]

    def list_pull_requests(
        self, state: str = "open", limit: int = 100, labels: Optional[List[str]] = None, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists pull requests with optional server-side label filtering or standard Pulls API."""
        target_repo = repo or self.repo
        if labels:
            # Use Search API for efficient server-side label filtering
            parts = []
            if state != "all":
                parts.append(f"state:{state}")
            for label in labels:
                parts.append(f'label:"{label}"')
            query = " ".join(parts)
            return self.search_pull_requests(query, limit=limit, repo=target_repo)

        # Fallback to standard Pulls API if no labels, using internal pagination
        prs: List[Dict[str, Any]] = []
        page = 1
        per_page = min(limit, 100)

        while len(prs) < limit:
            params = {"state": state, "per_page": per_page, "page": page}
            data = self._request("GET", f"/repos/{target_repo}/pulls", params=params)

            if not data:
                break

            for pr in data:
                if labels:
                    # Depending on API endpoint (pulls vs search), labels might be strings or dicts
                    raw_labels = pr.get("labels", [])
                    pr_labels = [
                        l.get("name") if isinstance(l, dict) else (l if isinstance(l, str) else "") for l in raw_labels
                    ]
                    if not all(label in pr_labels for label in labels):
                        continue

                # Map REST API response to GH CLI compatible format
                prs.append(
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "author": {"login": pr.get("user", {}).get("login")},
                        "headRefName": pr.get("head", {}).get("ref"),
                        "baseRefName": pr.get("base", {}).get("ref"),
                        "isDraft": pr.get("draft"),
                        "mergeStateStatus": pr.get("mergeable_state"),
                        "updatedAt": pr.get("updated_at"),
                        "url": pr.get("html_url"),
                    }
                )
                if len(prs) >= limit:
                    break

            if len(data) < per_page:
                break
            page += 1

        return prs

    def merge_pull_request(
        self,
        number: int,
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
        merge_method: str = "merge",
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Merges a pull request using GitHub REST API."""
        target_repo = repo or self.repo
        payload: Dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message
        return self._request("PUT", f"/repos/{target_repo}/pulls/{number}/merge", json_data=payload)

    def create_pull_request(
        self, title: str, body: str, head: str, base: str, draft: bool = False, repo: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a PR, automatically pushing the head branch if it doesn't exist on remote."""
        target_repo = repo or self.repo
        # Security: Validate branch name to prevent injection
        if not self.BRANCH_NAME_PATTERN.match(head):
            raise CLIError(f"Invalid branch name: {head}", code=400)

        if not self.branch_exists(head, repo=target_repo):
            log_warn(f"Branch '{head}' not found on remote. Checking for local branch and pushing...")
            git_util = GitUtility(token=self.token, repo=target_repo)

            # Style: Explicitly check for local branch existence before pushing
            if not git_util.branch_exists_locally(head):
                log_warn(f"Local branch '{head}' also not found. PR creation will likely fail.")
            elif git_util.push_branch(head):
                # Invalidate branch cache
                self.invalidate_branch_cache(head, repo=target_repo)
            else:
                log_warn(self.ERROR_AUTO_PUSH_FAILED.format(head=head))

        data = {"title": title, "body": body, "head": head, "base": base, "draft": draft}
        return self._request("POST", f"/repos/{target_repo}/pulls", json_data=data)

    def mark_pr_ready(self, number: int, repo: Optional[str] = None) -> bool:
        """Promote a draft PR to ready for review via gh CLI or GraphQL."""
        target_repo = repo or self.repo
        cmd = ["gh", "pr", "ready", str(number), "-R", target_repo]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
        log_warn(f"gh pr ready failed for #{number} in {target_repo}: {res.stderr}")
        return False

    def merge_pr(
        self,
        number: int,
        repo: Optional[str] = None,
        method: str = "merge",
        delete_branch: bool = True,
        admin: bool = False,
    ) -> bool:
        """Merges a pull request using gh CLI."""
        target_repo = repo or self.repo
        cmd = ["gh", "pr", "merge", str(number), "-R", target_repo]
        if method == "squash":
            cmd.append("--squash")
        elif method == "rebase":
            cmd.append("--rebase")
        else:
            cmd.append("--merge")

        if delete_branch:
            cmd.append("--delete-branch")
        if admin:
            cmd.append("--admin")

        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
        log_warn(f"gh pr merge failed for #{number} in {target_repo}: {res.stderr}")
        return False

    def close_pr(self, number: int, repo: Optional[str] = None, comment: Optional[str] = None) -> bool:
        """Closes a pull request with an optional comment."""
        target_repo = repo or self.repo
        cmd = ["gh", "pr", "close", str(number), "-R", target_repo]
        if comment:
            cmd.extend(["--comment", comment])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
        log_warn(f"gh pr close failed for #{number} in {target_repo}: {res.stderr}")
        return False
