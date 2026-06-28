import os
import subprocess
import json
import sys
from tdw_services.utils import log_info
import base64
import requests
import time
from typing import Optional, List, Dict, Any

class GitHubClient:
    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        from utils import get_github_token
        self.token = token or get_github_token()
        if not self.token:
            raise ValueError("Missing GITHUB_TOKEN environment variable.")
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO")
        if not self.repo:
            self.repo = self._detect_repo()
        self.base_url = "https://api.github.com"
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def _detect_repo(self) -> str:
        try:
            proc = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], capture_output=True, text=True)
            url = proc.stdout.strip()
            import re
            match = re.search(r'[:/]([^/]+/[^/.]+)(\.git)?$', url)
            return match.group(1) if match else url
        except Exception:
            return ""


    def _request(self, method: str, path: str, json_data: Optional[Dict] = None, params: Optional[Dict] = None, is_text: bool = False, accept: Optional[str] = None, allow_redirects: bool = True) -> Any:
        url = f"{self.base_url}{path}"
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
                timeout=30,
                allow_redirects=allow_redirects
            )
            response.raise_for_status()
            if is_text:
                return response.text
            return response.json()
        except requests.exceptions.RequestException as e:
             raise Exception(f"GitHub API Error: {e}")

    def fetch_pr_files(self, number: int) -> List[Dict[str, Any]]:
        """Fetches the list of files changed in a PR."""
        return self._request('GET', f'/repos/{self.repo}/pulls/{number}/files')

    def fetch_pr_details(self, number: int) -> Dict[str, Any]:
        return self._request('GET', f'/repos/{self.repo}/pulls/{number}')

    def fetch_pr_diff(self, number: int) -> str:
        return self._request('GET', f'/repos/{self.repo}/pulls/{number}', is_text=True)

    def fetch_prs_for_commit(self, commit_sha: str) -> List[Dict[str, Any]]:
        return self._request('GET', f'/repos/{self.repo}/commits/{commit_sha}/pulls')

    def fetch_check_runs(self, ref: str) -> List[Dict[str, Any]]:
        try:
            data = self._request('GET', f'/repos/{self.repo}/commits/{ref}/check-runs')
            return [{
                'id': run.get('id'),
                'name': run.get('name'),
                'status': run.get('status'),
                'conclusion': run.get('conclusion'),
                'url': run.get('html_url'),
                'external_id': run.get('external_id')
            } for run in data.get('check_runs', [])]
        except Exception:
            return []

    def fetch_check_suites(self, ref: str) -> List[Dict[str, Any]]:
        try:
            data = self._request('GET', f'/repos/{self.repo}/commits/{ref}/check-suites')
            return data.get('check_suites', [])
        except Exception:
            return []

    def fetch_check_runs_for_suite(self, suite_id: int) -> List[Dict[str, Any]]:
        try:
            data = self._request('GET', f'/repos/{self.repo}/check-suites/{suite_id}/check-runs')
            return data.get('check_runs', [])
        except Exception:
            return []

    def list_pull_requests(self, state: str = 'open', limit: int = 100, labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        prs = []
        page = 1
        per_page = min(limit, 100)

        while len(prs) < limit:
            params = {
                "state": state,
                "per_page": per_page,
                "page": page
            }
            data = self._request('GET', f'/repos/{self.repo}/pulls', params=params)

            if not data:
                break

            for pr in data:
                if labels:
                    pr_labels = [l.get('name') for l in pr.get('labels', [])]
                    if not all(label in pr_labels for label in labels):
                        continue

                # Map REST API response to GH CLI compatible format
                prs.append({
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "author": {"login": pr.get("user", {}).get("login")},
                    "headRefName": pr.get("head", {}).get("ref"),
                    "baseRefName": pr.get("base", {}).get("ref"),
                    "isDraft": pr.get("draft"),
                    "mergeStateStatus": pr.get("mergeable_state"),
                    "updatedAt": pr.get("updated_at"),
                    "url": pr.get("html_url")
                })
                if len(prs) >= limit:
                    break

            if len(data) < per_page:
                break
            page += 1

        return prs

    def create_pull_request(self, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        data = {
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }
        return self._request('POST', f'/repos/{self.repo}/pulls', json_data=data)

    def fetch_check_run_logs(self, check_run_id: int, external_id: Optional[str] = None) -> str:
        """Fetches logs for a specific check run, using external_id (job_id) if available. Gracefully fallback to check_run_id if external_id 404s."""
        # Ensure we have a valid ID and it's a string for the URL path
        job_id = str(external_id) if external_id is not None else str(check_run_id)
        try:
            # GitHub API returns a 302 redirect to a URL that expires after a few minutes
            # Using 'application/vnd.github.v3.raw' ensures we get the plain text logs
            return self._request('GET', f'/repos/{self.repo}/actions/jobs/{job_id}/logs', is_text=True, accept="application/vnd.github.v3.raw", allow_redirects=True)
        except Exception as e:
            error_msg = str(e)
            if external_id is not None and "404" in error_msg:
                # Fallback to query by raw check_run_id
                job_id = str(check_run_id)
                try:
                    return self._request('GET', f'/repos/{self.repo}/actions/jobs/{job_id}/logs', is_text=True, accept="application/vnd.github.v3.raw")
                except Exception as fallback_e:
                    return f"Failed to fetch logs for job {job_id} after fallback: {str(fallback_e)}"
            return f"Failed to fetch logs for job {job_id}: {error_msg}"

    def create_issue_comment(self, number: int, body: str) -> Dict[str, Any]:
        return self._request('POST', f'/repos/{self.repo}/issues/{number}/comments', json_data={'body': body})

    def create_issue(self, title: str, body: str) -> Dict[str, Any]:
        """Creates a new GitHub issue."""
        return self._request('POST', f'/repos/{self.repo}/issues', json_data={'title': title, 'body': body})

    def fetch_issue_details(self, number: int) -> Dict[str, Any]:
        """Fetches the details of a GitHub issue."""
        return self._request('GET', f'/repos/{self.repo}/issues/{number}')

    def update_issue(self, number: int, body: str) -> Dict[str, Any]:
        """Updates the body of a GitHub issue."""
        return self._request('PATCH', f'/repos/{self.repo}/issues/{number}', json_data={'body': body})

    def create_review(self, number: int, body: str, comments: List[Dict[str, Any]], event: str) -> Dict[str, Any]:
        data = {
            "body": body,
            "event": event,
            "comments": comments
        }
        return self._request('POST', f'/repos/{self.repo}/pulls/{number}/reviews', json_data=data)

    def download_zipball(self, ref: str, dest: str = "repo.zip") -> None:
        """A stateless download helper for the Orchestrator"""
        url = f"{self.base_url}/repos/{self.repo}/zipball/{ref}"
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        subprocess.run(["unzip", "-o", dest], check=True)
