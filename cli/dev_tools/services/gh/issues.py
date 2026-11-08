"""GitHub issue resource."""
import subprocess
from typing import Any, Dict, List, Optional
from dev_tools.utils import log_warn
from dev_tools.services.gh.checks import ChecksMixin



class IssuesMixin(ChecksMixin):
    """GitHub issue resource."""

    def close_issue(self, number: int, repo: Optional[str] = None, comment: Optional[str] = None) -> bool:
        """Closes an issue with an optional comment."""
        target_repo = repo or self.repo
        cmd = ["gh", "issue", "close", str(number), "-R", target_repo]
        if comment:
            cmd.extend(["--comment", comment])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
        log_warn(f"gh issue close failed for #{number} in {target_repo}: {res.stderr}")
        return False

    def create_issue_comment(self, number: int, body: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """Create a comment on an issue."""
        target_repo = repo or self.repo
        return self._request("POST", f"/repos/{target_repo}/issues/{number}/comments", json_data={"body": body})

    def create_issue(self, title: str, body: str, repo: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new GitHub issue."""
        target_repo = repo or self.repo
        res = self._request("POST", f"/repos/{target_repo}/issues", json_data={"title": title, "body": body})
        return self._normalize_issue_response(res)

    @staticmethod
    def normalize_issue(issue: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes issue dict to standard format."""
        return {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "body": issue.get("body"),
            "state": issue.get("state"),
            "html_url": issue.get("html_url"),
            "labels": [l.get("name") if isinstance(l, dict) else l for l in issue.get("labels", [])],
            "updated_at": issue.get("updated_at"),
        }

    def _normalize_issue_response(self, raw_data: Any) -> Dict[str, Any]:
        """Transforms issue responses of varying formats into the standard IssueSummary schema."""
        if not isinstance(raw_data, dict):
            return {}
        return {
            "number": raw_data.get("number"),
            "title": raw_data.get("title"),
            "html_url": raw_data.get("html_url"),
            "state": raw_data.get("state"),
        }

    def fetch_issue_details(self, number: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches the details of a GitHub issue."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/issues/{number}")

    def list_issues(
        self, state: str = "open", limit: int = 100, labels: Optional[List[str]] = None, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists issues (excluding pull requests) with optional filters."""
        target_repo = repo or self.repo
        query = f"repo:{target_repo} is:issue"
        if state != "all":
            query += f" state:{state}"
        if labels:
            for label in labels:
                query += f' label:"{label}"'

        data = self._request("GET", "/search/issues", params={"q": query, "per_page": limit})
        items = data.get("items", []) if isinstance(data, dict) else []

        return [self.normalize_issue(issue) for issue in items[:limit]]

    def fetch_issue_comments(self, number: int, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches the comments on an issue or pull request."""
        target_repo = repo or self.repo
        return self._request("GET", f"/repos/{target_repo}/issues/{number}/comments")

    def update_issue(
        self,
        number: int,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        state: Optional[str] = None,
        repo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates a GitHub issue's body, labels, and/or state."""
        target_repo = repo or self.repo
        data: Dict[str, Any] = {}
        if body is not None:
            data["body"] = body
        if labels is not None:
            data["labels"] = labels
        if state is not None:
            data["state"] = state
        res = self._request("PATCH", f"/repos/{target_repo}/issues/{number}", json_data=data)
        return self._normalize_issue_response(res)
