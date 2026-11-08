"""GitHub checks, workflow runs, and logs."""
import json
import re
import subprocess
from typing import Any, Dict, List, Optional
import requests
from dev_tools.utils import CLIError, log_warn
from dev_tools.services.gh.pulls import PullsMixin



class ChecksMixin(PullsMixin):
    """GitHub checks, workflow runs, and logs."""

    def fetch_check_runs(self, ref: str, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch check runs for a ref."""
        target_repo = repo or self.repo
        data = self._request("GET", f"/repos/{target_repo}/commits/{ref}/check-runs")
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

    def fetch_check_suites(self, ref: str, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch check suites for a ref."""
        target_repo = repo or self.repo
        data = self._request("GET", f"/repos/{target_repo}/commits/{ref}/check-suites")
        return data.get("check_suites", [])

    def fetch_check_runs_for_suite(self, suite_id: int, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch check runs for a suite."""
        target_repo = repo or self.repo
        data = self._request("GET", f"/repos/{target_repo}/check-suites/{suite_id}/check-runs")
        return data.get("check_runs", [])

    def fetch_workflow_runs(
        self, branch: Optional[str] = None, event: Optional[str] = None, repo: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches workflow runs for the repository with optional branch/event filtering."""
        target_repo = repo or self.repo
        params: Dict[str, Any] = {}
        if branch:
            params["branch"] = branch
        if event:
            params["event"] = event
        data = self._request("GET", f"/repos/{target_repo}/actions/runs", params=params if params else None)
        return data.get("workflow_runs", []) if isinstance(data, dict) else []

    def fetch_workflow_run_jobs(self, run_id: int, repo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches jobs for a workflow run, shaped to name/conclusion/steps."""
        target_repo = repo or self.repo
        data = self._request("GET", f"/repos/{target_repo}/actions/runs/{run_id}/jobs")
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
                "html_url": job.get("html_url"),
                "steps": [
                    {
                        "number": step.get("number"),
                        "name": step.get("name"),
                        "status": step.get("status"),
                        "conclusion": step.get("conclusion"),
                    }
                    for step in (job.get("steps") or [])
                ],
            }
            for job in jobs
        ]

    def _handle_missing_logs(self, identifier: Any, is_fallback: bool = False) -> str:
        """Helper to log warning and return a warning string for missing logs."""
        label = "check run" if is_fallback else "job"
        log_warn(f"Logs for {label} {identifier} {'also ' if is_fallback else ''}not found (404).")
        return (
            f"WARNING: "
            f"Logs not "
            f"available for "
            f"{identifier} (GitHub "
            f"returned 404). "
            f"They may "
            f"have expired "
            f"or the "
            f"job is "
            f"still pending."
        )

    def fetch_check_run_logs(self,
        check_run_id: int,
        external_id: Optional[str] = None,
        repo: Optional[str] = None) -> str:
        (
            """Fetches """
            """logs for """
            """a specific """
            """check run, """
            """using external_id """
            """(job_id) if """
            """available. Gracefully """
            """fallback to """
            """check_run_id if """
            """external_id 404s."""
        )
        target_repo = repo or self.repo
        # Ensure we have a valid ID and it's a string for the URL path
        job_id = str(external_id) if external_id is not None else str(check_run_id)

        # GitHub API returns a 302 redirect to a URL that expires after a few minutes
        # Using 'application/vnd.github.v3.raw' ensures we get the plain text logs
        # Large logs can take time to fetch
        try:
            return self._request(
                "GET",
                f"/repos/{target_repo}/actions/jobs/{job_id}/logs",
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
                    log_warn((
                        f"Logs "
                        f"for job "
                        f"{external_id} not "
                        f"found ({code}). "
                        f"Falling back "
                        f"to check "
                        f"run {check_run_id}..."
                    ))
                    try:
                        return self._request(
                            "GET",
                            f"/repos/{target_repo}/actions/jobs/{check_run_id}/logs",
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


    def fetch_pr_view_details(self, number: int, repo: Optional[str] = None) -> Dict[str, Any]:
        """Fetches detailed PR evaluation fields: title, state, mergeable, statusCheckRollup, isDraft, files, body."""
        target_repo = repo or self.repo
        cmd = [
            "gh",
            "pr",
            "view",
            str(number),
            "-R",
            target_repo,
            "--json",
            "title,state,mergeable,statusCheckRollup,isDraft,files,body,number,headRefName,baseRefName",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            try:
                return json.loads(res.stdout)
            except Exception as e:
                log_warn(f"Error parsing gh pr view JSON for PR #{number}: {e}")

        # Fallback to REST API if gh pr view fails
        try:
            pr = self.fetch_pr_details(number, repo=target_repo)
            files = self.fetch_pr_files(number, repo=target_repo)
            sha = pr.get("head", {}).get("sha")
            check_runs = self.fetch_check_runs(sha, repo=target_repo) if sha else []
            rollup = [
                {
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "conclusion": c.get("conclusion"),
                }
                for c in check_runs
            ]
            mergeable_val = (
                "MERGEABLE" if pr.get("mergeable") is True
                else ("CONFLICTING" if pr.get("mergeable") is False else "UNKNOWN")
            )
            return {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": (pr.get("state") or "").upper(),
                "mergeable": mergeable_val,
                "statusCheckRollup": rollup,
                "isDraft": pr.get("draft", False),
                "files": [{"path": f.get("filename")} for f in files],
                "body": pr.get("body") or "",
                "headRefName": pr.get("head", {}).get("ref"),
                "baseRefName": pr.get("base", {}).get("ref"),
            }
        except Exception as e:
            log_warn(f"Fallback fetch_pr_view_details failed for PR #{number}: {e}")
            return {}
