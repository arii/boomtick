import os
import sys
import subprocess
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import re
import random
from pathlib import Path
from typing import Optional, Union, List, Dict
try:
    from tdw_services.utils import log_info, log_error, log_warn
except ImportError:
    def log_info(msg): print(msg, file=sys.stderr)
    def log_error(msg): print(f"❌ Error: {msg}", file=sys.stderr)
    def log_warn(msg): print(f"⚠️  Warning: {msg}", file=sys.stderr)

class CLIError(Exception):
    def __init__(self, message, code=1, data=None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(self.message)

class APIConnectionError(Exception):
    """Custom exception for retriable API connection issues."""
    pass

def _get_model_config(env_key: str, config_attr: str, fallback: str) -> str:
    """Helper to resolve AI models from env, then project_config, then fallback."""
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    try:
        from dev_tools_sdk.config import load_project_config
        config = load_project_config()
        return getattr(config, config_attr)
    except Exception:
        return fallback

def get_ai_review_model() -> str:
    """Dynamic getter for the dedicated Code Reviewer model."""
    return _get_model_config("AI_REVIEW_MODEL", "ai_review_model", "gpt-4o")

def get_ai_synthesis_model() -> str:
    """Dynamic getter for the Synthesis model."""
    return _get_model_config("AI_SYNTHESIS_MODEL", "ai_synthesis_model", "gpt-4o-mini")

def get_ai_model() -> str:
    """Dynamic getter for the primary AI model."""
    # Special case for legacy/variant env key
    variant = os.environ.get("GITHUB_MODELS_MODEL")
    if variant and not os.environ.get("AI_MODEL"):
        return variant
    return _get_model_config("AI_MODEL", "ai_synthesis_model", "gpt-4o-mini")

def get_gemini_model() -> str:
    """Dynamic getter for the Gemini model."""
    return _get_model_config("GEMINI_MODEL", "ai_synthesis_model", "gemini-2.5-flash-lite")

def clean_llm_output(text: str) -> str:
    """Removes markdown code blocks if present."""
    match = re.search(r"```(?:\w+)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

def is_ai_available() -> bool:
    """Checks if AI API token is present."""
    return bool(os.getenv("GITHUB_TOKEN"))

def to_standard_schema(schema, uppercase: bool = False):
    """Recursively prepares a standard JSON schema.
    - Ensures top-level 'type: object' if 'properties' is present.
    - Converts type names to uppercase if uppercase=True (Gemini requirement).
    - Otherwise ensures lowercase (Standard AI model naming).
    """
    if isinstance(schema, dict):
        # Auto-inject object type if properties are defined without a type
        if "type" not in schema and "properties" in schema:
            schema = {"type": "object", **schema}

        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.upper() if uppercase else v.lower()
            else:
                new_schema[k] = to_standard_schema(v, uppercase=uppercase)
        return new_schema
    elif isinstance(schema, list):
        return [to_standard_schema(item, uppercase=uppercase) for item in schema]
    return schema

def call_ai(prompt: str, model: str = None, url: Optional[str] = None, max_retries: int = 3, schema = None) -> Optional[str]:
    """Unified helper to call AI API using LangChain ChatOpenAI with retries."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
    except ImportError:
        log_info("langchain_openai or langchain_core is not installed.")
        return None

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None

    model = model or get_ai_model()

    llm = ChatOpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=token,
        model=model,
        temperature=0.7,
        max_tokens=2048,
        max_retries=max_retries,
        model_kwargs={"response_format": {"type": "json_object"}} if schema else {}
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        log_error(f"AI Call failed: {e}")
        return None


def log_ai_run(entry: dict):
    try:
        log_dir = os.path.join(os.getcwd(), "boomtick-pkg", "cli", "logs", "ai")
        log_file = os.path.join(log_dir, "review-run.jsonl")
        os.makedirs(log_dir, exist_ok=True)
        from datetime import datetime
        entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log_error(f"Failed to append to AI run log: {e}")


def call_github_models(prompt: str, model: str = None, max_retries: int = 3, schema = None) -> Optional[str]:
    """Unified helper to call GitHub Models API (OpenAI-compatible)."""
    token = get_github_token()
    if not token: return None

    base_url = os.environ.get("GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com")
    if not base_url.endswith("/"): base_url += "/"
    target_url = urllib.parse.urljoin(base_url, "chat/completions")

    data = {"model": model or get_ai_model(), "messages": [{"role": "user", "content": prompt}], "stream": False}
    if schema:
        # OpenAI style: prompt injection + json_object mode
        norm_schema = to_standard_schema(schema, uppercase=False)
        data["response_format"] = {"type": "json_object"}
        data["messages"].insert(0, {
            "role": "system",
            "content": f"Output MUST be valid JSON matching this schema: {json.dumps(norm_schema)}"
        })

    req = urllib.request.Request(target_url, data=json.dumps(data).encode("utf-8"),
                                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})

    start_time = time.time()
    res = _call_api_with_retry(req, max_retries=max_retries)
    duration_ms = int((time.time() - start_time) * 1000)

    if res and "usage" in res:
        usage = res["usage"]
        log_ai_run({
            "type": "python-tool",
            "model": model or get_ai_model(),
            "inputTokens": usage.get("prompt_tokens", 0),
            "outputTokens": usage.get("completion_tokens", 0),
            "cacheTokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            "totalTokens": usage.get("total_tokens", 0),
            "durationMs": duration_ms,
            "cost": 0,
            "verdict": "unknown"
        })

    return res["choices"][0]["message"]["content"] if res and "choices" in res else None

def verify_ci_metrics(input_threshold: Optional[int] = None, output_threshold: Optional[int] = None, total_threshold: Optional[int] = None):
    """Verifies that the aggregated AI token usage in the current run is within limits."""
    # Use environment variables if provided, otherwise use documented defaults
    # Note: Docs specify 150k input, 50k output, 200k total.
    def get_limit(val, env_key, default):
        if val is not None: return int(val)
        try:
            return int(os.environ.get(env_key, default))
        except (ValueError, TypeError):
            return default

    input_limit = get_limit(input_threshold, "MAX_INPUT_TOKENS", 150000)
    output_limit = get_limit(output_threshold, "MAX_OUTPUT_TOKENS", 50000)
    total_limit = get_limit(total_threshold, "MAX_TOTAL_TOKENS", 200000)

    # Threshold validation
    if input_limit < 0 or output_limit < 0 or total_limit < 0:
        raise CLIError("Thresholds must be non-negative integers.")

    # Use Path for robust path resolution
    log_file = Path(os.getcwd()) / "boomtick-pkg" / "cli" / "logs" / "ai" / "review-run.jsonl"

    if not log_file.exists():
        # In multi-job CI, this might happen if logs weren't shared.
        return {"status": "warning", "message": f"No AI usage logs found at {log_file}. Ensure logs are shared between jobs."}

    total_input = 0
    total_output = 0

    try:
        with log_file.open("r") as f:
            for line in f:
                if not line.strip(): continue
                entry = json.loads(line)
                total_input += entry.get("inputTokens", 0)
                total_output += entry.get("outputTokens", 0)
    except Exception as e:
        log_error(f"Failed to read AI logs: {e}")
        return {"status": "error", "message": f"Could not verify metrics: {e}"}

    total_tokens = total_input + total_output

    result = {
        "inputTokens": total_input,
        "outputTokens": total_output,
        "totalTokens": total_tokens,
        "inputThreshold": input_limit,
        "outputThreshold": output_limit,
        "totalThreshold": total_limit
    }

    errors = []
    if total_input > input_limit:
        errors.append(f"Input tokens ({total_input}) exceeded limit ({input_limit})")
    if total_output > output_limit:
        errors.append(f"Output tokens ({total_output}) exceeded limit ({output_limit})")
    if total_tokens > total_limit:
        errors.append(f"Total tokens ({total_tokens}) exceeded limit ({total_limit})")

    if errors:
        return {
            "status": "error",
            "message": "AI Token threshold exceeded: " + "; ".join(errors),
            "metrics": result
        }

    return {"status": "success", "message": "AI Token usage is within limits.", "metrics": result}

def call_gemini(prompt: str, model: str = None, max_retries: int = 3, schema = None) -> Optional[str]:
    """Unified helper to call Gemini API using LangChain."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
    except ImportError:
        log_info("langchain_google_genai or langchain_core is not installed.")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    llm = ChatGoogleGenerativeAI(
        model=model or get_gemini_model(),
        google_api_key=api_key,
        temperature=0.7,
        max_retries=max_retries,
    )

    if schema:
        # Note: structured output handling varies by LangChain version/provider
        # For simplicity in this shim, we'll rely on prompt engineering if bind_tools isn't used
        prompt += f"\n\nOutput MUST be valid JSON matching this schema: {json.dumps(schema)}"

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        log_error(f"Gemini Call failed: {e}")
        return None

def call_ai_service(prompt: str, model: str = None, schema = None) -> Optional[str]:
    """
    Orchestrates AI calls: GitHub Models -> Gemini.
    """
    # 1. Try GitHub Models
    res = call_github_models(prompt, model=model, schema=schema)
    if res: return res

    # 2. Try Gemini
    res = call_gemini(prompt, schema=schema) # Gemini model naming is different, let it use default for now
    if res: return res

    return None

def run_command(cmd: Union[str, List[str]], shell: bool = False, check: bool = True, input_str: Optional[str] = None, log_on_error: bool = True, **kwargs) -> Union[str, subprocess.CompletedProcess]:
    """
    Unified command execution helper.
    - If check=True (default): returns stripped stdout string, raises CLIError on non-zero exit.
    - If check=False: returns CompletedProcess object.
    """
    proc = subprocess.run(
        cmd,
        shell=shell,
        input=input_str,
        capture_output=True,
        text=True,
        check=False,
        **kwargs
    )
    if proc.returncode != 0 and log_on_error:
        log_error(f"Command failed (exit {proc.returncode}): {proc.args}")
        if proc.stdout:
            log_info(f"--- stdout ---\n{proc.stdout.strip()}")
        if proc.stderr:
            log_info(f"--- stderr ---\n{proc.stderr.strip()}")

    if check:
        if proc.returncode != 0:
            raise CLIError(f"Command failed with exit code {proc.returncode}", code=proc.returncode)
        return proc.stdout.strip()

    return proc

def get_github_token() -> Optional[str]:
    """Retrieves the GitHub token from environment (prioritizing GITHUB_TOKEN)."""
    return os.getenv("GITHUB_TOKEN")

def get_repo_name() -> Optional[str]:
    """Auto-detect repo from environment variables or git remote."""
    repo = os.getenv("GITHUB_REPOSITORY") or os.getenv("GH_REPO")
    if repo:
        return repo

    try:
        # Using check=False here to avoid noisy logs for a common discovery step
        res = run_command(['git', 'config', '--get', 'remote.origin.url'], check=False, log_on_error=False)
        if res.returncode != 0:
            return os.getenv("GH_REPO")
        url = res.stdout.strip()
        if not url:
            return os.getenv("GH_REPO")
        import re
        match = re.search(r'[:/]([^/]+/[^/.]+)(\.git)?$', url)
        return match.group(1) if match else url
    except Exception:
        return None

class GHAConfigManager:
    """Manages GitHub Actions variables with local caching and robust error handling."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GHAConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        try:
            # nosemgrep: python.lang.compatibility.python37.python37-compatibility-importlib2
            from importlib.resources import files
            self.config_path = "config.json"
            self.config = json.loads(files("dev_tools").joinpath("config.json").read_text())
            return
        except Exception:
            pass
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.gh_available = None
        self.warned_auth = False
        self.warned_repo = False
        self.cache = self._load_cache()
        self._initialized = True

    def _load_cache(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    def _get_github_client_and_repo(self):
        """Helper to get GitHub client and repo name."""
        try:
            client = get_github_client()
            repo = get_repo_name()
            return client, repo
        except Exception:
            return None, None

    def get_variable(self, name: str) -> Optional[str]:
        """Retrieves a variable, checking local cache first, then the GitHub API."""
        # 1. Check local cache
        if name in self.cache:
            return str(self.cache[name])

        # 2. Fetch from GitHub API
        import requests
        token = get_github_token()
        repo = get_repo_name()
        if token and repo:
            try:
                import requests
                url = f"https://api.github.com/repos/{repo}/actions/variables/{name}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json"
                }
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    val = str(data.get("value", ""))
                    self.cache[name] = val
                    self._save_cache()
                    return val
            except Exception:
                pass

        # 3. Check gh CLI availability
        if self.gh_available is None:
            try:
                run_command(["gh", "--version"], log_on_error=False)
                self.gh_available = True
            except (CLIError, FileNotFoundError):
                self.gh_available = False

        if not self.gh_available:
            return None

        try:
            url = f"https://api.github.com/repos/{repo_name}/actions/variables/{name}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                val = response.json().get("value")
                self.cache[name] = val
                self._save_cache()
                return val
            elif response.status_code != 404:
                log_error(f"fetching GHA variable '{name}' via API: {response.status_code} {response.text}")
        except Exception as e:
            log_error(f"Unexpected error fetching GHA variable '{name}': {e}")

        return None

    def set_variable(self, name: str, value: str) -> bool:
        """Sets a variable using the GitHub API and updates local cache."""
        # 1. Update local cache
        self.cache[name] = value
        self._save_cache()

        # 2. Set via GitHub API
        import requests
        token = get_github_token()
        repo = get_repo_name()
        if token and repo:
            try:
                import requests
                url = f"https://api.github.com/repos/{repo}/actions/variables/{name}"
                payload = {"name": name, "value": str(value)}
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json"
                }
                response = requests.patch(url, json=payload, headers=headers, timeout=10)
                if response.status_code in [200, 204]:
                    return True
                elif response.status_code == 404:
                    # Create instead of update
                    create_url = f"https://api.github.com/repos/{repo}/actions/variables"
                    create_response = requests.post(create_url, json=payload, headers=headers, timeout=10)
                    if create_response.status_code in [201, 204]:
                        return True
            except Exception:
                pass

        # 3. Check gh CLI availability
        if self.gh_available is None:
            try:
                run_command(["gh", "--version"], log_on_error=False)
                self.gh_available = True
            except (CLIError, FileNotFoundError):
                self.gh_available = False

        if not self.gh_available:
            return False

        try:
            url = f"https://api.github.com/repos/{repo_name}/actions/variables/{name}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }

            # Check if variable exists first to decide between POST (create) and PATCH (update)
            response = requests.get(url, headers=headers, timeout=10)
            exists = (response.status_code == 200)

            if exists:
                res = requests.patch(url, headers=headers, json={"name": name, "value": str(value)}, timeout=10)
            else:
                create_url = f"https://api.github.com/repos/{repo_name}/actions/variables"
                res = requests.post(create_url, headers=headers, json={"name": name, "value": str(value)}, timeout=10)

            if res.status_code in [201, 204]:
                return True
            else:
                log_error(f"setting GHA variable '{name}' via API: {res.status_code} {res.text}")
                return False
        except Exception as e:
            log_error(f"setting GHA variable '{name}' via API: {e}")
            return False

def get_gha_variable(name: str) -> Optional[str]:
    """Helper function to retrieve a GHA variable via the global manager."""
    return GHAConfigManager().get_variable(name)

def set_gha_variable(name: str, value: str) -> bool:
    """Helper function to set a GHA variable via the global manager."""
    return GHAConfigManager().set_variable(name, value)

def extract_failing_info(logs: str) -> List[dict]:
    """Extracts failing test and build information from logs."""
    findings = []
    # TS Errors
    ts_errors = re.findall(r"([a-zA-Z0-9_\-\./]+\.[tj]sx?):(\d+):(\d+) - error (TS\d+): (.*)", logs)
    for file_path, line, col, code, msg in ts_errors:
        findings.append({"file": file_path, "line": line, "message": f"{code}: {msg}", "type": "typescript"})

    # Vitest Errors (Robust)
    # Matches FAIL followed by the test file, then non-greedily finds the first ❯ trace
    # (?!FAIL) ensures we don't skip over another FAIL block
    vitest_matches = re.finditer(r"FAIL\s+([^\n]+)(?:(?!FAIL).)*?❯\s+([^\n:]+):(\d+):(\d+)", logs, re.DOTALL)
    for m in vitest_matches:
        findings.append({
            "file": m.group(2),
            "line": m.group(3),
            "message": f"Test Failure in {m.group(1)}",
            "type": "vitest"
        })

    # Playwright Errors
    playwright_matches = re.finditer(r"\s*\d+\)\s+\[([^\]]+)\]\s+›\s+([^\s:]+):(\d+):(\d+)\s+›\s+(.*)", logs)
    for m in playwright_matches:
        findings.append({
            "file": m.group(2),
            "line": m.group(3),
            "message": f"Playwright [{m.group(1)}] › {m.group(5)}",
            "type": "playwright"
        })

    return findings

def clean_gha_logs(logs: str) -> str:
    """Removes GitHub Action noise from logs while preserving actual error messages."""
    if not logs:
        return ""

    lines = logs.splitlines()
    cleaned = []

    # Patterns to filter out after timestamp removal
    noise_patterns = [
        r'^\[command\].*',
        r'^##\[command\].*',
        r'^##\[warning\].*',
        r'^##\[error\]Process completed with exit code.*',
        r'^Removing credentials config.*',
        r'^Stop and remove container.*',
        r'^Remove container network.*',
        r'^Cleaning up orphan processes.*',
        r'^/usr/bin/docker.*',
    ]
    combined_noise = re.compile('|'.join(noise_patterns), re.IGNORECASE)

    for line in lines:
        # 1. Strip ANSI escape codes
        line = re.sub(r'\x1b\[[0-9;]*[mGKF]', '', line)

        # 2. Strip GHA timestamps
        line = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+', '', line)

        # 3. Filter noise
        if not combined_noise.search(line) and line.strip():
            cleaned.append(line)

    return "\n".join(cleaned)

def get_github_client():
    from github import Github, Auth
    token = get_github_token()
    if not token:
        raise CLIError("GitHub token not found", code=401)
    return Github(auth=Auth.Token(token))

def get_stack_versions(fetch_latest: bool = False) -> Dict[str, str]:
    from version_utils import get_stack_versions as _get
    return _get(fetch_latest=fetch_latest)

def compare_versions(v1: str, v2: str) -> int:
    from version_utils import compare_versions as _cmp
    return _cmp(v1, v2)

def fetch_latest_npm(package_name: str) -> Optional[str]:
    from version_utils import fetch_latest_npm as _fetch
    return _fetch(package_name)

def fetch_latest_gh_action(action_path: str) -> Optional[str]:
    from version_utils import fetch_latest_gh_action as _fetch
    return _fetch(action_path)

def fetch_latest_node() -> Optional[str]:
    from version_utils import fetch_latest_node as _fetch
    return _fetch()
