"""GitHub client core: auth, transport, and repo helpers."""
import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple
import requests
from dev_tools.utils import CLIError, log_warn
import dev_tools.services.github



class GitHubCoreMixin:
    """GitHub client core: auth, transport, and repo helpers."""

    # --- Constants ---
    ERROR_AUTO_PUSH_FAILED = "PR creation for '{head}' will likely fail because auto-push was unsuccessful."

    BRANCH_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]+$")

    def __init__(self,
        token: Optional[str] = None,
        repo: Optional[str] = None,
        no_cache: bool = False,
        use_graphql: bool = True):
        from dev_tools.config import get_config
        from dev_tools.utils import get_github_token

        self.token = token or get_github_token()
        if not self.token:
            raise ValueError("Missing GITHUB_TOKEN environment variable.")
        if repo:
            self.repo = repo
        else:
            cfg_repo = None
            try:
                cfg_repo = get_config().github_repo
            except Exception as e:
                log_warn(f"github: config repo lookup failed: {e}")
            detected_repo = cfg_repo or self._detect_repo() or os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO") or ""
            self.repo = detected_repo
        self.base_url = "https://api.github.com"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        self._branch_cache : Dict[str, bool] = {}
        self._cache = dev_tools.services.github.DiskCache(subdir="github", no_cache=no_cache)
        disable_gql_env = os.environ.get("TD_DISABLE_GRAPHQL", "").lower() in ("true", "1", "yes")
        self.use_graphql = use_graphql and not disable_gql_env
        self._node_id_cache: Dict[str, str] = {}

    def branch_exists(self, branch_name: str, repo: Optional[str] = None) -> bool:
        """Checks if a branch exists in the repository, with caching."""
        target_repo = repo or self.repo
        cache_key = f"{target_repo}:{branch_name}"
        if cache_key in self._branch_cache:
            return self._branch_cache[cache_key]

        try:
            self._request("GET", f"/repos/{target_repo}/branches/{branch_name}")
            self._branch_cache[cache_key] = True
            return True
        except (requests.exceptions.RequestException, CLIError) as e:
            # Fallback to status_code if 'code' attribute is missing (e.g. RequestException)
            code = getattr(e, "code", None)
            if code is None and hasattr(e, "response") and e.response is not None:
                code = e.response.status_code

            if code == 404:
                self._branch_cache[cache_key] = False
                return False
            raise e

    def invalidate_branch_cache(self, branch_name: str, repo: Optional[str] = None) -> None:
        """Invalidates the branch existence cache for a specific branch."""
        target_repo = repo or self.repo
        cache_key = f"{target_repo}:{branch_name}"
        if cache_key in self._branch_cache:
            del self._branch_cache[cache_key]
        if branch_name in self._branch_cache:
            del self._branch_cache[branch_name]

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation against the GitHub API."""
        return self.graphql_query(query, variables)

    def graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes a GraphQL query/mutation against the GitHub API."""
        url = f"{self.base_url}/graphql"
        payload: Dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        headers = {"Accept": "application/json"}
        try:
            response = self._session.post(
                url,
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            res_json = response.json()
            if "errors" in res_json:
                errors_msg = json.dumps(res_json["errors"])
                raise CLIError(f"GitHub GraphQL Error: {errors_msg}", code=200, data=res_json)
            return res_json
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 500
            raise CLIError(f"GitHub GraphQL Request failed: {str(e)}", code=status_code) from e
        except Exception as e:
            if isinstance(e, CLIError):
                raise
            raise CLIError(f"GitHub GraphQL Request failed: {str(e)}", code=500) from e

    def _resolve_node_ids(self, number: int, label_names: List[str]) -> Tuple[Optional[str], Dict[str, str]]:
        """Resolves the GraphQL node ID of the issue/PR and the given labels with caching."""
        issue_cache_key = f"{self.repo}:issue:{number}"
        issue_node_id = self._node_id_cache.get(issue_cache_key)

        missing_labels = [l for l in label_names if f"{self.repo}:label:{l}" not in self._node_id_cache]
        resolved_labels = {l: self._node_id_cache[f"{self.repo}:label:{l}"] for l in label_names if f"{self.repo}:label:{l}" in self._node_id_cache}

        if issue_node_id and not missing_labels:
            return issue_node_id, resolved_labels

        # We need to query
        if not self.repo:
            raise CLIError("Repository not configured.")
        owner, name = self.repo.split("/", 1)
        # Repository.labels accepts no `names` argument (it only takes
        # first/after/before/last/orderBy/query), so filter client-side
        # from the first page; label counts are small and node IDs are
        # cached after the first resolution.
        query = """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            issueOrPullRequest(number: $number) {
              __typename
              ... on Issue {
                id
              }
              ... on PullRequest {
                id
              }
            }
            labels(first: 100) {
              nodes {
                id
                name
              }
            }
          }
        }
        """
        variables = {
            "owner": owner,
            "name": name,
            "number": number,
        }
        res = self.graphql(query, variables)
        repo_data = res.get("data", {}).get("repository") or {}

        # Resolve issue node ID
        iopr = repo_data.get("issueOrPullRequest")
        if iopr:
            issue_node_id = iopr.get("id")
            if issue_node_id:
                self._node_id_cache[issue_cache_key] = issue_node_id

        # Resolve label node IDs
        labels_nodes = repo_data.get("labels", {}).get("nodes") or []
        for node in labels_nodes:
            lbl_name = node.get("name")
            lbl_id = node.get("id")
            if lbl_name and lbl_id:
                self._node_id_cache[f"{self.repo}:label:{lbl_name}"] = lbl_id
                resolved_labels[lbl_name] = lbl_id

        return issue_node_id, resolved_labels

    def _detect_repo(self) -> str:
        try:
            proc = subprocess.run(["git", "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                check=False)
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
        except (ValueError, AttributeError) as inner_e:
            log_warn(f"Failed to parse error response: {inner_e}")
