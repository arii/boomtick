# pylint: disable=f-string-without-interpolation,import-outside-toplevel,invalid-name,line-too-long,missing-docstring,redefined-outer-name,reimported,subprocess-run-check,too-many-arguments,too-many-branches,too-many-locals,too-many-positional-arguments,too-many-public-methods,too-many-statements,try-except-raise
import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests  # type: ignore[import-untyped]
from dev_tools.constants import REVIEW_PLACEHOLDERS
from dev_tools.utils import CLIError, DiskCache, log_warn
from dev_tools.utils.git import GitUtility


class GitHubClient:
    # --- Constants ---
    ERROR_AUTO_PUSH_FAILED = "PR creation for '{head}' will likely fail because auto-push was unsuccessful."
    BRANCH_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]+$")

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None, no_cache: bool = False):
        from dev_tools.utils import get_github_token

        self.token = token or get_github_token()
        if not self.token:
            raise ValueError("Missing GITHUB_TOKEN environment variable.")
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO")
        if not self.repo:
            self.repo = self._detect_repo()
        self.base_url = "https://api.github.com"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        self._branch_cache : Dict[str, bool] = {}
        self._cache = DiskCache(subdir="github", no_cache=no_cache)

    def branch_exists(self, branch_name: str) -> bool:
        """Checks if a branch exists in the repository, with caching."""
        if branch_name in self._branch_cache:
            return self._branch_cache[branch_name]

        try:
            self._request("GET", f"/repos/{self.repo}/branches/{branch_name}")
            self._branch_cache[branch_name] = True
            return True
        except (requests.exceptions.RequestException, CLIError) as e:
            # Fallback to status_code if 'code' attribute is missing (e.g. RequestException)
            code = getattr(e, "code", None)
            if code is None and hasattr(e, "response") and e.response is not None:
                code = e.response.status_code

            if code == 404:
                self._branch_cache[branch_name] = False
                return False
            raise e

    def invalidate_branch_cache(self, branch_name: str) -> None:
        """Invalidates the branch existence cache for a specific branch."""
        if branch_name in self._branch_cache:
            del self._branch_cache[branch_name]

    def _detect_repo(self) -> str:
        try:
            proc = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=False)
            url = proc.stdout.strip()

            match = re.search(r"[:/]([^/]+/[^/.]+)(\.git)?$", url)
            return match.group(1) if match else url
        except Exception:
            return ""

    def _request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        is_text: bool = False,
        accept: Optional[str] = None,
        allow_redirects: bool = True,
        ttl: int = 300,
        timeout: int = 60,
    ) -> Any:
        url = f"{self.base_url}{path}"

        # Cache key based on request details
        cache_key = f"{method}:{path}:{json.dumps(params, sort_keys=True) if params else ''}:{accept}:{is_text}"

        if method == "GET":
            cached_val = self._cache.get(cache_key)
            if cached_val is not None:
                return cached_val

        headers = {}
        if accept:
            headers["Accept"] = accept
        elif is_text:
            headers["Accept"] = "application/vnd.github.v3.diff"

        try:
            response = self._session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
            response.raise_for_status()

            result = response.text if is_text else response.json()

            if method == "GET":
                self._cache.set(cache_key, result, ttl=ttl)

            return result
        except requests.exceptions.HTTPError as e:
            self._parse_github_error(e)
            raise
        except requests.exceptions.RequestException as e:
            # Provide context and a status code for consistency
            status_code = 500
            if e.response is not None:
                status_code = e.response.status_code

            raise CLIError(
                f"GitHub Request failed: {method} {path} - {str(e)}",
                code=status_code,
                data={"method": method, "path": path}
            ) from e

    def _parse_github_error(self, e: requests.exceptions.HTTPError) -> None:
        """Helper to extract detailed error message from GitHub API response."""
        try:
            if e.response is None:
                return
            error_data = e.response.json()
            if not isinstance(error_data, dict):
                return
            github_message = error_data.get("message", "")

            # Sanitize detailed errors to prevent information disclosure
            if "errors" in error_data and isinstance(error_data["errors"], list):
                sanitized_errors = []
                for err in error_data["errors"]:
                    if isinstance(err, dict):
                        # Only include safe fields: 'message', 'field', 'resource', 'code'
                        # Cast to str and truncate to avoid leaking nested structures or massive data
                        safe_err = {
                            k: str(err[k])[:200]
                            for k in ["message", "field", "resource", "code"]
                            if k in err and err[k] is not None
                        }
                        sanitized_errors.append(safe_err)

                if sanitized_errors:
                    github_message += f": {json.dumps(sanitized_errors)}"

            if github_message:
                raise CLIError(
                    f"GitHub API Error: {github_message}",
                    code=e.response.status_code,
                    data=error_data,
                ) from e
        except (ValueError, AttributeError):
            pass

    def fetch_pr_files(self, number: int) -> List[Dict[str, Any]]:
        """Fetches the list of files changed in a PR."""
        # PR files usually don't change once a commit is pushed, but we'll use a shorter TTL
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}/files", ttl=600)

    def fetch_pr_details(self, number: int) -> Dict[str, Any]:
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}")

    def fetch_pr_diff(self, number: int) -> str:
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}", is_text=True)

    def fetch_prs_for_commit(self, commit_sha: str) -> List[Dict[str, Any]]:
        return self._request("GET", f"/repos/{self.repo}/commits/{commit_sha}/pulls")

    def fetch_check_runs(self, ref: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/repos/{self.repo}/commits/{ref}/check-runs")
        return [
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "url": run.get("html_url"),
                "external_id": run.get("external_id"),
            }
            for run in data.get("check_runs", [])
        ]

    def fetch_check_suites(self, ref: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/repos/{self.repo}/commits/{ref}/check-suites")
        return data.get("check_suites", [])

    def fetch_check_runs_for_suite(self, suite_id: int) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/repos/{self.repo}/check-suites/{suite_id}/check-runs")
        return data.get("check_runs", [])

    def search_pull_requests(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """General search for pull requests using the Search API."""
        full_query = f"repo:{self.repo} is:pr {query}"
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
        self, state: str = "open", limit: int = 100, labels: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Lists pull requests with optional server-side label filtering or standard Pulls API."""
        if labels:
            # Use Search API for efficient server-side label filtering
            query = f"state:{state}"
            for label in labels:
                query += f' label:"{label}"'
            return self.search_pull_requests(query, limit=limit)

        # Fallback to standard Pulls API if no labels, using internal pagination
        prs: List[Dict[str, Any]] = []
        page = 1
        per_page = min(limit, 100)

        while len(prs) < limit:
            params = {"state": state, "per_page": per_page, "page": page}
            data = self._request("GET", f"/repos/{self.repo}/pulls", params=params)

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

    def create_pull_request(self, title: str, body: str, head: str, base: str, draft: bool = False) -> Dict[str, Any]:
        """Creates a PR, automatically pushing the head branch if it doesn't exist on remote."""
        # Security: Validate branch name to prevent injection
        if not self.BRANCH_NAME_PATTERN.match(head):
            raise CLIError(f"Invalid branch name: {head}", code=400)

        if not self.branch_exists(head):
            log_warn(f"Branch '{head}' not found on remote. Checking for local branch and pushing...")
            git_util = GitUtility(token=self.token, repo=self.repo)

            # Style: Explicitly check for local branch existence before pushing
            if not git_util.branch_exists_locally(head):
                log_warn(f"Local branch '{head}' also not found. PR creation will likely fail.")
            elif git_util.push_branch(head):
                # Invalidate branch cache
                self.invalidate_branch_cache(head)
            else:
                log_warn(self.ERROR_AUTO_PUSH_FAILED.format(head=head))

        data = {"title": title, "body": body, "head": head, "base": base, "draft": draft}
        return self._request("POST", f"/repos/{self.repo}/pulls", json_data=data)

    def _handle_missing_logs(self, identifier: Any, is_fallback: bool = False) -> str:
        """Helper to log warning and return a warning string for missing logs."""
        label = "check run" if is_fallback else "job"
        log_warn(f"Logs for {label} {identifier} {'also ' if is_fallback else ''}not found (404).")
        return f"WARNING: Logs not available for {identifier} (GitHub returned 404). They may have expired or the job is still pending."

    def fetch_check_run_logs(self, check_run_id: int, external_id: Optional[str] = None) -> str:
        """Fetches logs for a specific check run, using external_id (job_id) if available. Gracefully fallback to check_run_id if external_id 404s."""
        # Ensure we have a valid ID and it's a string for the URL path
        job_id = str(external_id) if external_id is not None else str(check_run_id)

        # GitHub API returns a 302 redirect to a URL that expires after a few minutes
        # Using 'application/vnd.github.v3.raw' ensures we get the plain text logs
        # Large logs can take time to fetch
        try:
            return self._request(
                "GET",
                f"/repos/{self.repo}/actions/jobs/{job_id}/logs",
                is_text=True,
                accept="application/vnd.github.v3.raw",
                allow_redirects=True,
                timeout=300,
            )
        except (requests.exceptions.HTTPError, CLIError) as e:
            code = getattr(e, "code", None)
            if code is None and isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                code = e.response.status_code

            # Fallback only if the error was a 404 (permanent not found) or a potentially transient network error
            # If it's a 500 or other permanent error, don't waste time retrying with the other ID
            is_transient = code in [408, 429, 502, 503, 504]
            if code == 404 or is_transient:
                if external_id is not None:
                    # Fallback to query by raw check_run_id
                    log_warn(f"Logs for job {external_id} not found ({code}). Falling back to check run {check_run_id}...")
                    try:
                        return self._request(
                            "GET",
                            f"/repos/{self.repo}/actions/jobs/{check_run_id}/logs",
                            is_text=True,
                            accept="application/vnd.github.v3.raw",
                            timeout=300,
                        )
                    except (requests.exceptions.HTTPError, CLIError) as fallback_e:
                        fallback_code = getattr(fallback_e, "code", None)
                        if (
                            fallback_code is None
                            and isinstance(fallback_e, requests.exceptions.HTTPError)
                            and fallback_e.response is not None
                        ):
                            fallback_code = fallback_e.response.status_code

                        if fallback_code == 404:
                            return self._handle_missing_logs(check_run_id, is_fallback=True)
                        raise fallback_e
                elif code == 404:
                    return self._handle_missing_logs(job_id)
            raise

    def create_issue_comment(self, number: int, body: str) -> Dict[str, Any]:
        return self._request("POST", f"/repos/{self.repo}/issues/{number}/comments", json_data={"body": body})

    def create_issue(self, title: str, body: str) -> Dict[str, Any]:
        """Creates a new GitHub issue."""
        return self._request("POST", f"/repos/{self.repo}/issues", json_data={"title": title, "body": body})

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

    def fetch_issue_details(self, number: int) -> Dict[str, Any]:
        """Fetches the details of a GitHub issue."""
        return self._request("GET", f"/repos/{self.repo}/issues/{number}")

    def list_issues(
        self, state: str = "open", limit: int = 100, labels: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Lists issues (excluding pull requests) with optional filters."""
        query = f"repo:{self.repo} is:issue state:{state}"
        if labels:
            for label in labels:
                query += f' label:"{label}"'

        data = self._request("GET", "/search/issues", params={"q": query, "per_page": limit})
        items = data.get("items", []) if isinstance(data, dict) else []

        return [self.normalize_issue(issue) for issue in items[:limit]]

    def fetch_issue_comments(self, number: int) -> List[Dict[str, Any]]:
        """Fetches the comments on an issue or pull request."""
        return self._request("GET", f"/repos/{self.repo}/issues/{number}/comments")

    def fetch_review_comments(self, number: int) -> List[Dict[str, Any]]:
        """Fetches the review comments on a pull request."""
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}/comments")

    def _get_diff_mapping(self, pr_number: int) -> Dict[str, Dict[int, int]]:
        """
        Parses the PR diff and returns a mapping of {filename: {new_line_number: diff_position}}.
        Diff position is 0-indexed starting from the first '@@' hunk header in the file.
        """
        diff_text = self.fetch_pr_diff(pr_number)
        mapping: Dict[str, Dict[int, int]] = {}
        current_file = None
        file_diff_pos = 0
        new_line_num = 0
        first_hunk_seen = False

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                current_file = None
                first_hunk_seen = False
                continue
            if line.startswith("--- "):
                continue
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                mapping[current_file] = {}
                file_diff_pos = 0
                continue
            if line.startswith("@@ "):
                if current_file is not None:
                    if not first_hunk_seen:
                        # First hunk of the file: hunk header is position 0
                        file_diff_pos = 0
                        first_hunk_seen = True
                    else:
                        # Subsequent hunk headers count as a line in the diff
                        file_diff_pos += 1

                    match = re.search(r"\+(\d+)", line)
                    if match:
                        new_line_num = int(match.group(1))
                continue

            if current_file is not None:
                file_diff_pos += 1
                if line.startswith("+"):
                    mapping[current_file][new_line_num] = file_diff_pos
                    new_line_num += 1
                elif line.startswith("-"):
                    # Deletions increment position but don't have a line number in the new file
                    pass
                elif line.startswith("\\"):
                    # "\ No newline at end of file" increments position
                    file_diff_pos += 1
                else:
                    # Context line
                    mapping[current_file][new_line_num] = file_diff_pos
                    new_line_num += 1
        return mapping

    def update_issue(
        self,
        number: int,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        state: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates a GitHub issue's body, labels, and/or state."""
        data: Dict[str, Any] = {}
        if body is not None:
            data["body"] = body
        if labels is not None:
            data["labels"] = labels
        if state is not None:
            data["state"] = state
        return self._request("PATCH", f"/repos/{self.repo}/issues/{number}", json_data=data)

    def create_review(self, number: int, body: str, comments: List[Dict[str, Any]], event: str) -> Dict[str, Any]:
        data = {"body": body, "event": event, "comments": comments}
        return self._request("POST", f"/repos/{self.repo}/pulls/{number}/reviews", json_data=data)

    def add_labels(self, number: int, labels: List[str]) -> List[Dict[str, Any]]:
        """Adds labels to an issue or pull request."""
        return self._request("POST", f"/repos/{self.repo}/issues/{number}/labels", json_data={"labels": labels})

    def remove_label(self, number: int, label_name: str) -> None:
        """Removes a label from an issue or pull request."""
        encoded_label = quote(label_name)
        return self._request("DELETE", f"/repos/{self.repo}/issues/{number}/labels/{encoded_label}")

    @staticmethod
    def validate_review_payload(payload: Dict[str, Any]):
        """
        Validates that the review payload is not just boilerplate or empty.
        """
        import re

        from dev_tools.utils import CLIError

        if not isinstance(payload, dict):
            raise CLIError("Review rejected: Invalid payload format (expected dict).")

        body = payload.get("body", "")
        if not isinstance(body, str):
            body = str(body)

        recommendation = payload.get("recommendation", "")
        if not isinstance(recommendation, str):
            recommendation = str(recommendation)

        comments = payload.get("comments", [])
        if not isinstance(comments, list):
            raise CLIError("Review rejected: 'comments' must be a list.")

        # Check recommendation for placeholders (should be explicit)
        for p in REVIEW_PLACEHOLDERS:
            if re.search(p, recommendation, re.IGNORECASE):
                raise CLIError(f"Review rejected: Recommendation contains boilerplate placeholder matching '{p}'")

        # Check for real comments (not placeholders)
        real_comments = []
        for c in comments:
            if not isinstance(c, dict):
                continue

            c_body = str(c.get("body", ""))
            c_path = str(c.get("path", ""))

            # Check if comment fields contain placeholders
            is_placeholder = False
            for p in REVIEW_PLACEHOLDERS:
                if re.search(p, c_body, re.IGNORECASE) or re.search(p, c_path, re.IGNORECASE):
                    is_placeholder = True
                    break

            if is_placeholder:
                raise CLIError("Review rejected: Comment contains boilerplate placeholder.")

            if c_body.strip() and not re.search(r"<filename\s*/?>", c_path, re.IGNORECASE):
                real_comments.append(c)

        # Check for empty/meaningless body
        clean_body = body
        clean_body = re.sub(r"^#+.*$", "", clean_body, flags=re.MULTILINE)
        # Strip all placeholders for meaningful content check
        for p in REVIEW_PLACEHOLDERS:
            clean_body = re.sub(p, "", clean_body, flags=re.IGNORECASE | re.DOTALL)

        clean_body = clean_body.strip()

        if not clean_body and not real_comments:
            raise CLIError("Review rejected: No meaningful content found in body or comments.")

    def submit_pr_review(
        self,
        pr_number: int,
        filepath: str,
        cleanup: bool = False,
        dry_run: bool = True,
        event_override: Optional[str] = None,
        is_json: bool = False,
    ):
        """
        Submits a PR review from a markdown file containing a JSON payload.
        The file should have standard Markdown at the top and a JSON block at the bottom for metadata.
        """
        import json
        import re

        from dev_tools.utils import CLIError, log_info, log_warn

        if not os.path.exists(filepath):
            raise CLIError(f"Review file missing: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all JSON blocks and identify the metadata block (must contain 'recommendation', 'comments', or 'labels')
        json_blocks = list(re.finditer(r"```json\n(.*?)\n```", content, re.DOTALL))
        if not json_blocks:
            raise CLIError("Could not find any JSON block in review document")

        # Known keys used to distinguish the metadata block from other JSON blocks (like code samples)
        METADATA_IDENTIFIER_KEYS = {"recommendation", "comments", "labels"}

        payload = None
        metadata_match = None
        for match in reversed(json_blocks):
            try:
                candidate = json.loads(match.group(1))
                if isinstance(candidate, dict) and any(k in candidate for k in METADATA_IDENTIFIER_KEYS):
                    payload = candidate
                    metadata_match = match
                    break
            except json.JSONDecodeError:
                continue

        if not payload:
            raise CLIError(
                f"Could not find a valid JSON metadata block (expected keys: {', '.join(METADATA_IDENTIFIER_KEYS)})"
            )

        # Extract Markdown body (everything above the metadata JSON block)
        if not metadata_match:
            raise CLIError("Could not determine the start of the JSON block")
        body = content[: metadata_match.start()].strip()
        # Clean up the trailing "Output JSON" instructions if present
        body = re.split(r"##\s+Output JSON", body, flags=re.IGNORECASE)[0].strip()

        # Robustly strip placeholders from the markdown body as well
        for p in REVIEW_PLACEHOLDERS:
            body = re.sub(p, "", body, flags=re.IGNORECASE | re.DOTALL).strip()

        if not body:
            raise CLIError("Review body (Markdown section) is empty. Provide findings before the JSON block.")

        # Combine extracted body (Markdown section) and payload body (JSON section)
        json_body = payload.get("body", "").strip()

        if json_body:
            # Check if JSON body contains only placeholders
            stripped_body = json_body
            for p in REVIEW_PLACEHOLDERS:
                stripped_body = re.sub(p, "", stripped_body, flags=re.IGNORECASE | re.DOTALL).strip()

            if not stripped_body:
                raise CLIError(
                    "Review rejected: JSON body contains only placeholders/boilerplate. "
                    "Ensure you provide actual feedback in the 'body' field of the JSON block."
                )

            payload["body"] = f"{body}\n\n{stripped_body}"
        else:
            payload["body"] = body

        # Validate payload before proceeding
        self.validate_review_payload(payload)

        # Map comment lines to diff positions
        try:
            diff_mapping = self._get_diff_mapping(pr_number)
            mapped_comments = []
            unmapped_comments = []

            for comment in payload.get("comments", []):
                path = comment.get("path")
                line = comment.get("line")

                if path in diff_mapping and line in diff_mapping[path]:
                    comment["position"] = diff_mapping[path][line]
                    mapped_comments.append(comment)
                else:
                    unmapped_comments.append(comment)

            payload["comments"] = mapped_comments

            if unmapped_comments:
                extra_body = "\n\n### Additional Feedback (Lines not found in diff)\n"
                for c in unmapped_comments:
                    extra_body += f"- **{c.get('path')}:{c.get('line')}**: {c.get('body')}\n"
                payload["body"] = payload.get("body", "") + extra_body

        except Exception as e:
            log_warn(f"Failed to generate diff mapping for PR #{pr_number}: {e}")

        pr_details = self.fetch_pr_details(pr_number)
        check_runs = self.fetch_check_runs(pr_details.get("head", {}).get("sha"))
        failing_checks = [str(run.get("name")) for run in check_runs if run.get("conclusion") == "failure"]

        # Determine event based on recommendation field, then fallback to body analysis
        recommendation = payload.get("recommendation", "")
        if event_override:
            event = event_override
        elif recommendation == "Approved":
            event = "APPROVE"
        elif recommendation == "Approved with Minor Changes":
            # Per code review, minor changes shouldn't automatically approve
            event = "COMMENT"
        elif recommendation == "Not Approved":
            event = "REQUEST_CHANGES"
        else:
            event = (
                "REQUEST_CHANGES"
                if "Not Approved" in payload.get("body", "")
                else "APPROVE" if "Approved" in payload.get("body", "") else "COMMENT"
            )

        if failing_checks and event == "APPROVE":
            event = "COMMENT"
            warning = f"> ⚠️ **BLOCKING CI FAILURE**: Approval overridden to COMMENT because the following checks are failing: {', '.join(failing_checks)}. Please resolve CI issues before approval.\n\n"
            payload["body"] = warning + payload.get("body", "")

        if not dry_run:

            def try_create_review(review_body, review_comments, review_event):
                try:
                    return self.create_review(pr_number, review_body, review_comments, review_event)
                except (requests.exceptions.HTTPError, CLIError) as e:
                    code = getattr(e, "code", None)
                    if code is None and isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                        code = e.response.status_code

                    if code == 422:
                        error_data = getattr(e, "data", None)
                        if error_data is None and isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
                            try:
                                error_data = e.response.json()
                            except Exception:
                                raise

                        error_msg = json.dumps(error_data) if error_data else (e.response.text if hasattr(e, "response") and e.response else str(e))

                        if "Can not approve your own pull request" in error_msg and review_event != "COMMENT":
                            log_warn("Cannot approve own PR. Retrying as COMMENT...")
                            return try_create_review(review_body, review_comments, "COMMENT")

                        # Handle individual comment failures if possible, or fallback to body
                        if review_comments:
                            log_warn(
                                f"Failed to post {len(review_comments)} inline comments. Retrying as body comments. Error: {error_msg[:200]}"
                            )
                            fallback_body = review_body
                            fallback_body += "\n\n### Inline Comments (Fallback due to line resolution errors)\n"
                            for comment in review_comments:
                                line_info = f":{comment.get('line')}" if comment.get("line") else ""
                                fallback_body += f"- **{comment.get('path')}{line_info}**: {comment.get('body')}\n"
                            return try_create_review(fallback_body, [], review_event)
                    raise e

            try_create_review(payload.get("body", ""), payload.get("comments", []), event)

            if event == "REQUEST_CHANGES":
                labels = [l.get("name") if isinstance(l, dict) else l for l in pr_details.get("labels", [])]
                if "needs-design-system-fix" not in labels and any(
                    k in payload.get("body", "").lower() for k in ["tailwind", "token"]
                ):
                    self.add_labels(pr_number, ["needs-design-system-fix"])

            if not is_json:
                log_info(f"✅ Submitted {event} for PR #{pr_number}")

            if cleanup:
                if os.path.exists(filepath):
                    os.remove(filepath)
                ctx = filepath.replace("pr-review-", "pr-context-")
                if os.path.exists(ctx):
                    os.remove(ctx)
        else:
            if not is_json:
                log_info(f"[DRY-RUN] Would submit {event} for PR #{pr_number}")

        return {"status": "success", "event": event, "pr": pr_number}

    def download_zipball(self, ref: str, dest: str = "repo.zip") -> None:
        """A stateless download helper for the Orchestrator"""
        from dev_tools.utils import sanitize_path

        # Security: Validate input to prevent command/path injection
        if not re.match(r"^[a-zA-Z0-9._/-]+$", ref):
            raise CLIError(f"Invalid ref: {ref}", code=400)

        safe_dest = sanitize_path(dest)
        if not safe_dest.endswith(".zip"):
            safe_dest += ".zip"

        url = f"{self.base_url}/repos/{self.repo}/zipball/{ref}"
        headers = {"Authorization": f"Bearer {self.token}"}
        # Increased timeout for large downloads
        response = requests.get(url, headers=headers, stream=True, timeout=300)
        response.raise_for_status()

        with open(safe_dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        from dev_tools.utils import run_command
        # unzip -o overwrite files without prompting
        run_command(["unzip", "-o", safe_dest])
