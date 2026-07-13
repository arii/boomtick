# pylint: disable=too-many-lines,import-outside-toplevel,line-too-long,missing-docstring,no-else-return,raise-missing-from,redefined-outer-name,reimported,too-many-locals,unused-argument,unused-variable
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests  # type: ignore[import-untyped]


def sanitize_path(path: str, max_length: int = 255) -> str:
    """
    Sanitizes a path to prevent traversal bugs and ensure it remains within the intended scope.
    Uses normpath to resolve .. and ensures the result doesn't escape the current directory.
    """
    if not path:
        return ""

    # 0. Length check
    if len(path) > max_length:
        path = path[:max_length]

    # 1. Null byte protection
    path = path.split("\0", 1)[0]

    # 2. Normalize path to resolve '..'
    normalized = os.path.normpath(path)

    # 3. Prevent escaping current directory
    if normalized.startswith("..") or os.path.isabs(normalized):
        # Fallback to a safe version or just strip leading dots/slashes
        normalized = normalized.lstrip("./\\")

    # 4. Character Whitelisting: Allow only alphanumeric, dots, slashes, hyphens, and underscores
    sanitized = re.sub(r"[^a-zA-Z0-9\./\-_]", "", normalized)

    # 5. Collapse multiple slashes and strip
    return re.sub(r"/+", "/", sanitized).strip("/")


def escape_md(text: Any) -> str:
    """Escapes markdown special characters using a single regex pass."""
    # Escape \, *, _, `, #, [, ], (, )
    return re.sub(r"([\\*_\`#\[\]\(\)])", r"\\\1", str(text))


def run_git_commands(
    commands: List[List[str]], cwd: Optional[str] = None
) -> List[Union[str, subprocess.CompletedProcess[str]]]:
    """Executes a sequence of git commands."""
    results = []
    for cmd in commands:
        results.append(run_command(cmd, cwd=cwd))
    return results


def sanitize_metadata(text: str) -> str:
    """
    Sanitizes metadata text (like PR titles or branch names) for safe use in filenames or markdown templates.
    """
    if not text:
        return ""
    # Replace non-alphanumeric characters (except - and _) with hyphens
    sanitized = re.sub(r"[^a-zA-Z0-9\-_]+", "-", text)
    # Collapse multiple hyphens and strip
    return re.sub(r"-+", "-", sanitized).strip("-")


def mask_sensitive_data(msg: str) -> str:
    """Redacts sensitive information like GitHub tokens from strings."""
    if not isinstance(msg, str):
        msg = str(msg)
    # Redact GitHub Tokens (Personal Access Tokens and Fine-grained Tokens)
    msg = re.sub(r"ghp_[a-zA-Z0-9]{36,}", "ghp_***", msg)
    msg = re.sub(r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59,}", "github_pat_***", msg)
    # Generic token redaction for URLs or assignments (e.g., token=ABC123xyz)
    msg = re.sub(
        r"(?i)(token|auth|key|secret|password|access_token)([:=])[a-zA-Z0-9._-]{10,}",
        r"\1\2***",
        msg,
    )
    return msg


def log_info(msg: str):
    """Logs an informational message to stderr."""
    print(mask_sensitive_data(msg), file=sys.stderr)


def log_error(msg: str):
    """Logs an error message to stderr."""
    print(f"❌ Error: {mask_sensitive_data(msg)}", file=sys.stderr)


def log_warn(msg: str):
    """Logs a warning message to stderr."""
    print(f"⚠️  Warning: {mask_sensitive_data(msg)}", file=sys.stderr)


def log_debug(msg: str):
    """Logs a debug message to stderr."""
    print(f"DEBUG: {mask_sensitive_data(msg)}", file=sys.stderr)


def _call_api_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Internal helper for making API calls with standard retry logic."""
    from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
    from urllib3.util import Retry

    # Default to 60s for standard calls, 300s for large downloads/logs
    timeout = kwargs.pop("timeout", 60)
    max_retries = kwargs.pop("max_retries", 3)

    session = requests.Session()
    retries = Retry(
        total=max_retries,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))

    response = session.request(method, url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response


def post_api_result(url: str, payload: Dict[str, Any]):
    """Standardizes API results back to a provided webhook or service."""
    _call_api_with_retry("POST", url, json=payload, timeout=10, max_retries=5)


class CLIError(Exception):
    """Base class for CLI errors with optional exit code and data."""

    def __init__(self, message, code=1, data=None):
        self.message = message
        self.code = code
        self.data = data
        super().__init__(self.message)


def get_base_dir() -> str:
    """Returns the absolute path to the CLI package root."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def resolve_resource_path(resource_name: str) -> str:
    """
    Resolves the absolute path to a package resource.
    Handles importlib_resources with fallbacks for local development.
    """
    # 1. Try the importlib_resources backport (preferred for compatibility)
    try:
        import importlib_resources as resources

        # Try resources first
        ref = resources.files("dev_tools.resources").joinpath(resource_name)
        # mypy: Traversable might not have exists() depending on version, but it's common in backports
        if hasattr(ref, "exists") and ref.exists():
            return str(ref)

        # Then try dev_tools root (for verify_versions.py etc)
        ref = resources.files("dev_tools").joinpath(resource_name)
        if ref.exists():
            return str(ref)
    except (ImportError, AttributeError, FileNotFoundError, TypeError) as e:
        log_debug(f"importlib_resources failed for '{resource_name}': {e}. Falling back.")

    # 2. Fallback to manual discovery for development/monorepo
    # Assumes structural layout:
    # Standalone: boomtick-pkg/cli/dev_tools/utils.py -> resources/
    # Monorepo: boomtick-pkg/cli/dev_tools/utils.py -> scripts/ (3 levels up)
    base_dir = Path(__file__).parent

    candidates = [
        base_dir / "resources" / resource_name,
        base_dir / resource_name,
        base_dir.parent / resource_name,
        base_dir.parent.parent.parent / "scripts" / resource_name,
    ]

    for cand in candidates:
        # Validate existence before returning to avoid broken paths
        if cand.exists():
            return str(cand.absolute())

    raise FileNotFoundError(f"Could not resolve resource: {resource_name}. Tried: {[str(c) for c in candidates]}")


def get_workspace_log_dir() -> Path:
    """Returns the path to the workspace log directory (.boomtick/logs)."""
    # Use CWD for workspace-based logging
    return Path(os.getcwd()) / ".boomtick" / "logs"


def ensure_dir(*parts: str) -> str:
    """Joins path parts, ensures the directory exists, and returns the absolute path."""
    # Prioritize workspace-based logging
    path = get_workspace_log_dir().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def safe_write_file(filepath: str, content: str):
    """
    Writes content to a file while being symlink-aware and security-conscious.
    If the filepath is a symlink, it resolves the real path and writes to the target,
    preserving the symlink, but ONLY if the target is within the repository root.
    """
    target_path = filepath
    if os.path.islink(filepath):
        target_path = os.path.realpath(filepath)
        log_info(f"Symlink detected: {filepath} -> {target_path}")

    # Security: Ensure target path is within repo root
    repo_root = os.path.abspath(os.getcwd())
    # Use realpath here to resolve symlinks and prevent escaping via symlink redirection
    abs_target = os.path.realpath(target_path)
    try:
        # commonpath is the standard way to verify a subpath remains within a parent
        if os.path.commonpath([repo_root, abs_target]) != repo_root:
            raise CLIError(
                f"Security Error: Target path {target_path} (resolved: {abs_target}) is outside of repository root."
            )
    except (ValueError, Exception) as e:
        raise CLIError(f"Security Error: Target path {target_path} is invalid or outside of repository root: {e}")

    # Ensure parent directory exists for the target
    os.makedirs(os.path.dirname(abs_target), exist_ok=True)

    try:
        with open(abs_target, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise CLIError(f"Failed to write to {abs_target}: {e}")


def apply_patch(filepath: str, patch_content: str):
    """
    Applies a patch to a file using git apply with whitespace fixing.
    Restricts application to the specific filepath for security.
    """
    import tempfile

    # Security: validate filepath - use realpath to resolve any symlink escapes
    repo_root = os.path.abspath(os.getcwd())
    abs_filepath = os.path.realpath(filepath)
    try:
        if os.path.commonpath([repo_root, abs_filepath]) != repo_root:
            raise CLIError(f"Security Error: Path {filepath} is outside of repository root.")
    except ValueError:
        raise CLIError(f"Security Error: Path {filepath} is invalid or outside of repository root.")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as tmp:
        tmp.write(patch_content)
        tmp_path = tmp.name

    try:
        # Use --include to restrict what git apply can touch
        # filepath should be relative to repo root for --include
        rel_path = os.path.relpath(abs_filepath, repo_root)
        run_command(["git", "apply", "--whitespace=fix", "--include", rel_path, tmp_path])
        log_info(f"Successfully applied patch to {filepath}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_or_create_log_dir(subdir: str) -> str:
    """Returns the path to a specific log subdirectory and ensures it exists."""
    log_dir = get_workspace_log_dir() / subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)


class DiskCache:
    """Lightweight disk-based cache for JSON-serializable data."""

    def __init__(self, subdir: str = "cache", no_cache: bool = False):
        self.cache_dir = get_or_create_log_dir(subdir)
        # Use explicit parameter or TD_NO_CACHE to bypass the cache
        self.no_cache = no_cache or os.environ.get("TD_NO_CACHE") == "true"

    def _get_path(self, key: str) -> Path:
        hashed_key = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return Path(self.cache_dir) / f"{hashed_key}.json"

    def get(self, key: str) -> Optional[Any]:
        if self.no_cache:
            return None

        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            with path.open("r") as f:
                data = json.load(f)

            expires_at = data.get("expires_at")
            if expires_at and time.time() > expires_at:
                path.unlink()
                return None

            return data.get("value")
        except Exception as e:
            log_warn(f"Failed to read cache for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        if self.no_cache:
            return

        path = self._get_path(key)
        data = {
            "value": value,
            "created_at": time.time(),
            "expires_at": (time.time() + ttl) if ttl else None,
        }

        try:
            with path.open("w") as f:
                json.dump(data, f)
        except Exception as e:
            log_warn(f"Failed to write cache for {key}: {e}")

    def delete(self, key: str):
        path = self._get_path(key)
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                log_warn(f"Failed to delete cache for {key}: {e}")

    def clear(self):
        """Clears all cached items in this subdir without removing the directory."""
        try:
            for file_path in Path(self.cache_dir).iterdir():
                if file_path.is_file():
                    file_path.unlink()
        except Exception as e:
            log_warn(f"Failed to clear cache: {e}")


class APIConnectionError(Exception):
    """Custom exception for retriable API connection issues."""


def _get_model_config(env_key: str, config_attr: str, fallback: str) -> str:
    """Helper to resolve AI models from env, then project_config, then fallback."""
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val
    try:
        from dev_tools.config import get_config

        config = get_config()
        return getattr(config, config_attr)
    except Exception:
        return fallback


def get_ai_review_model() -> str:
    """Dynamic getter for the dedicated Code Reviewer model."""
    return _get_model_config("AI_REVIEW_MODEL", "ai_review_model", "gpt-4o")


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
    """
    Removes markdown code blocks if present, or extracts from <findings> tags if present.
    This utility focuses on standard LLM formatting (tags/blocks).
    Pipeline-specific robust extraction should be handled by the caller.
    """
    if not text:
        return ""

    # Handle double-escaped newlines commonly found in AI generated JSON in markdown
    text = text.replace("\\\\n", "\\n")

    # 1. Extract from <findings> tags if present
    findings_match = re.search(r"<findings>\s*(.*?)\s*</findings>", text, re.DOTALL | re.IGNORECASE)
    if findings_match:
        text = findings_match.group(1).strip()

    # 2. Extract from ```json or ``` code blocks
    code_block_match = re.search(r"```(?:json|xml|tsx?|jsx?)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        return code_block_match.group(1).strip()

    return text.strip()


def is_ai_available() -> bool:
    """Checks if AI API token is present."""
    return bool(os.getenv("GITHUB_TOKEN"))


def to_standard_schema(schema):
    """Recursively prepares a standard JSON schema.
    - Ensures top-level 'type: object' if 'properties' is present.
    - Ensures lowercase (Standard AI model naming).
    """
    if isinstance(schema, dict):
        # Auto-inject object type if properties are defined without a type
        if "type" not in schema and "properties" in schema:
            schema = {"type": "object", **schema}

        new_schema = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                new_schema[k] = v.lower()
            else:
                new_schema[k] = to_standard_schema(v)
        return new_schema
    elif isinstance(schema, list):
        return [to_standard_schema(item) for item in schema]
    return schema


def call_ai(
    prompt: str,
    model: Optional[str] = None,
    url: Optional[str] = None,
    max_retries: int = 3,
    schema: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Unified helper to call AI API using LangChain ChatOpenAI with retries."""

    token = get_github_token()
    if not token:
        return None

    model = model or get_ai_model()

    url_target = "https://models.inference.ai.azure.com/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    if schema:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = _call_api_with_retry(
            "POST",
            url_target,
            headers=headers,
            json=payload,
            max_retries=max_retries,
            retry_status_codes=[429, 500, 502, 503, 504],
        )
        if not response:
            return None
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log_error(f"AI Call failed: {e}")
        return None


def log_ai_run(entry: dict):
    try:
        log_dir = get_or_create_log_dir("ai")
        log_file = os.path.join(log_dir, "review-run.jsonl")
        from datetime import datetime

        entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log_error(f"Failed to append to AI run log: {e}")


def call_github_models(
    prompt: str, model: Optional[str] = None, max_retries: int = 3, schema: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Unified helper to call GitHub Models API (OpenAI-compatible)."""
    token = get_github_token()
    if not token:
        return None

    base_url = os.environ.get("GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com")
    if not base_url.endswith("/"):
        base_url += "/"
    target_url = urllib.parse.urljoin(base_url, "chat/completions")

    data: Dict[str, Any] = {
        "model": model or get_ai_model(),
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if schema:
        # OpenAI style: prompt injection + json_object mode
        norm_schema = to_standard_schema(schema)
        data["response_format"] = {"type": "json_object"}
        messages = data.get("messages")
        if isinstance(messages, list):
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"Output MUST be valid JSON matching this schema: {json.dumps(norm_schema)}",
                },
            )

    start_time = time.time()
    try:
        response = _call_api_with_retry(
            "POST",
            target_url,
            json=data,
            headers={"Authorization": f"Bearer {token}"},
            max_retries=max_retries,
        )
        res = response.json()
    except Exception as e:
        log_error(f"GitHub Models call failed: {e}")
        return None

    duration_ms = int((time.time() - start_time) * 1000)

    if res and "usage" in res:
        usage = res["usage"]
        log_ai_run(
            {
                "type": "python-tool",
                "model": model or get_ai_model(),
                "inputTokens": usage.get("prompt_tokens", 0),
                "outputTokens": usage.get("completion_tokens", 0),
                "cacheTokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                "totalTokens": usage.get("total_tokens", 0),
                "durationMs": duration_ms,
                "cost": 0,
                "verdict": "unknown",
            }
        )

    return res["choices"][0]["message"]["content"] if res and "choices" in res else None


def verify_ci_metrics(
    input_threshold: Optional[int] = None,
    output_threshold: Optional[int] = None,
    total_threshold: Optional[int] = None,
):
    """Verifies that the aggregated AI token usage in the current run is within limits."""

    # Use environment variables if provided, otherwise use documented defaults
    # Note: Docs specify 150k input, 50k output, 200k total.
    def get_limit(val, env_key, default):
        if val is not None:
            return int(val)
        try:
            return int(os.environ.get(env_key, default))
        except (ValueError, TypeError):
            return default

    input_threshold = get_limit(input_threshold, "MAX_INPUT_TOKENS", 800000)
    output_threshold = get_limit(output_threshold, "MAX_OUTPUT_TOKENS", 200000)
    total_threshold = get_limit(total_threshold, "MAX_TOTAL_TOKENS", 1000000)

    # Threshold validation
    if input_threshold < 0 or output_threshold < 0 or total_threshold < 0:
        raise CLIError("Thresholds must be non-negative integers.")

    # Use Path for robust path resolution
    log_file = Path(get_or_create_log_dir("ai")) / "review-run.jsonl"

    if not log_file.exists():
        # In multi-job CI, this might happen if reviews were skipped or logs weren't shared.
        return {
            "status": "success",
            "message": "No AI usage logs found. Assuming 0 tokens used.",
            "metrics": {
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
                "inputThreshold": input_threshold,
                "outputThreshold": output_threshold,
                "totalThreshold": total_threshold,
            },
        }

    total_input = 0
    total_output = 0

    try:
        with log_file.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
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
        "inputThreshold": input_threshold,
        "outputThreshold": output_threshold,
        "totalThreshold": total_threshold,
    }

    errors = []
    if total_input > input_threshold:
        errors.append(f"Input tokens ({total_input}) exceeded limit ({input_threshold})")
    if total_output > output_threshold:
        errors.append(f"Output tokens ({total_output}) exceeded limit ({output_threshold})")
    if total_tokens > total_threshold:
        errors.append(f"Total tokens ({total_tokens}) exceeded limit ({total_threshold})")

    if errors:
        return {
            "status": "error",
            "message": "AI Token threshold exceeded: " + "; ".join(errors),
            "metrics": result,
        }

    return {"status": "success", "message": "AI Token usage is within limits.", "metrics": result}


def call_gemini(
    prompt: str, model: Optional[str] = None, max_retries: int = 3, schema: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Unified helper to call Gemini API using LangChain."""

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    if schema:
        # Note: structured output handling varies by LangChain version/provider
        # For simplicity in this shim, we'll rely on prompt engineering if bind_tools isn't used
        prompt += f"\n\nOutput MUST be valid JSON matching this schema: {json.dumps(schema)}"

    url_target = f"https://generativelanguage.googleapis.com/v1beta/models/{model or get_gemini_model()}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
        },
    }

    try:
        response = _call_api_with_retry("POST", url_target, headers=headers, json=payload, max_retries=max_retries)
        if not response:
            return None
        data = response.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        return None
    except Exception as e:
        log_error(f"Gemini Call failed: {e}")
        return None


def call_ai_service(
    prompt: str, model: Optional[str] = None, schema: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Orchestrates AI calls: GitHub Models -> Gemini.
    """
    # 1. Try GitHub Models
    res = call_github_models(prompt, model=model, schema=schema)
    if res:
        return res

    # 2. Try Gemini
    # Gemini model naming is different, let it use default for now
    res = call_gemini(prompt, schema=schema)
    if res:
        return res

    return None


def run_command(
    cmd: Union[str, List[str]],
    shell: bool = False,
    check: bool = True,
    input_str: Optional[str] = None,
    log_on_error: bool = True,
    **kwargs: Any,
) -> Union[str, subprocess.CompletedProcess[str]]:
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
        **kwargs,
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
    """Retrieves the GitHub token from environment (prioritizing GITHUB_TOKEN) or falls back to gh auth token."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    # Fallback to local gh CLI auth token
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            token = proc.stdout.strip()
            if token:
                return token
    except Exception as e:
        log_warn(f"Failed to discover GitHub token: {e}")
    return None


def get_repo_name() -> Optional[str]:
    """Auto-detect repo from environment variables or git remote."""
    repo = os.getenv("GITHUB_REPOSITORY") or os.getenv("GH_REPO")
    if repo:
        return repo

    try:
        # Using check=False here to avoid noisy logs for a common discovery step
        res = run_command(["git", "config", "--get", "remote.origin.url"], check=False, log_on_error=False)
        if not isinstance(res, subprocess.CompletedProcess):
            return os.getenv("GH_REPO")

        if res.returncode != 0:
            return os.getenv("GH_REPO")
        url = res.stdout.strip()
        if not url:
            return os.getenv("GH_REPO")
        import re

        match = re.search(r"[:/]([^/]+/[^/.]+)(\.git)?$", url)
        return match.group(1) if match else url
    except Exception as e:
        log_warn(f"Failed to detect repository name: {e}")
        return None


_gha_var_cache: Dict[str, str] = {}


def get_gha_variable(name: str) -> Optional[str]:
    """Helper function to retrieve a GHA variable via the native gh cli with lightweight memory cache."""
    if name in _gha_var_cache:
        return _gha_var_cache[name]
    try:
        proc = run_command(["gh", "variable", "get", name], check=False, log_on_error=False)
        if isinstance(proc, subprocess.CompletedProcess) and proc.returncode == 0:
            val = proc.stdout.strip()
            _gha_var_cache[name] = val
            return val
    except Exception as e:
        log_warn(f"Failed to get GHA variable {name}: {e}")
    return None


def set_gha_variable(name: str, value: str) -> bool:
    """Helper function to set a GHA variable via the native gh cli."""
    try:
        proc = run_command(["gh", "variable", "set", name, "--body", str(value)], check=False, log_on_error=False)
        if isinstance(proc, subprocess.CompletedProcess) and proc.returncode == 0:
            _gha_var_cache[name] = str(value)
            return True
        elif isinstance(proc, subprocess.CompletedProcess):
            log_warn(f"Failed to set GHA variable {name}. stderr: {proc.stderr}")
    except Exception as e:
        log_warn(f"Failed to set GHA variable {name}: {e}")
    return False


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
        findings.append(
            {
                "file": m.group(2),
                "line": m.group(3),
                "message": f"Test Failure in {m.group(1)}",
                "type": "vitest",
            }
        )

    # Playwright Errors
    playwright_matches = re.finditer(r"\s*\d+\)\s+\[([^\]]+)\]\s+›\s+([^\s:]+):(\d+):(\d+)\s+›\s+(.*)", logs)
    for m in playwright_matches:
        findings.append(
            {
                "file": m.group(2),
                "line": m.group(3),
                "message": f"Playwright [{m.group(1)}] › {m.group(5)}",
                "type": "playwright",
            }
        )

    return findings


def clean_gha_logs(logs: str) -> str:
    """Removes GitHub Action noise from logs while preserving actual error messages."""
    if not logs:
        return ""

    lines = logs.splitlines()
    cleaned = []

    # Patterns to filter out after timestamp removal
    noise_patterns = [
        r"^\[command\].*",
        r"^##\[command\].*",
        r"^##\[warning\].*",
        r"^##\[error\]Process completed with exit code.*",
        r"^Removing credentials config.*",
        r"^Stop and remove container.*",
        r"^Remove container network.*",
        r"^Cleaning up orphan processes.*",
        r"^/usr/bin/docker.*",
    ]
    combined_noise = re.compile("|".join(noise_patterns), re.IGNORECASE)

    for line in lines:
        # 1. Strip ANSI escape codes
        line = re.sub(r"\x1b\[[0-9;]*[mGKF]", "", line)

        # 2. Strip GHA timestamps
        line = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+", "", line)

        # 3. Filter noise
        if not combined_noise.search(line) and line.strip():
            cleaned.append(line)

    return "\n".join(cleaned)


def get_github_client():
    from github import Auth, Github

    token = get_github_token()
    if not token:
        raise CLIError("GitHub token not found", code=401)
    return Github(auth=Auth.Token(token))


def get_stack_versions(fetch_latest: bool = False) -> Dict[str, str]:
    from dev_tools.version_utils import get_stack_versions as _get

    return _get(fetch_latest=fetch_latest)


def compare_versions(v1: str, v2: str) -> int:
    from dev_tools.version_utils import compare_versions as _cmp

    return _cmp(v1, v2)


def fetch_latest_npm(package_name: str) -> Optional[str]:
    from dev_tools.version_utils import fetch_latest_npm as _fetch

    return _fetch(package_name)


def fetch_latest_gh_action(action_path: str) -> Optional[str]:
    from dev_tools.version_utils import fetch_latest_gh_action as _fetch

    return _fetch(action_path)


def fetch_latest_node() -> Optional[str]:
    from dev_tools.version_utils import fetch_latest_node as _fetch

    return _fetch()


def walk_tsx(root_dir="src"):
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".tsx"):
                yield os.path.join(root, file)


def find_patterns_in_file(filepath, patterns):
    findings = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")
        for i, line in enumerate(lines):
            for pattern, message in patterns:
                match = re.search(pattern, line)
                if match:
                    findings.append((i + 1, message, match.group()))
    return findings


def get_bundle_size(dist_dir="dist/assets"):
    import glob

    if not os.path.isdir(dist_dir):
        log_warn(f"Bundle directory {dist_dir} not found.")
        return 0
    js_files = glob.glob(os.path.join(dist_dir, "*.js"))
    if not js_files:
        return 0
    total_bytes = 0
    for js_file in js_files:
        try:
            total_bytes += os.path.getsize(js_file)
        except OSError as e:
            log_error(f"getting size for {js_file}: {e}")
            raise CLIError(f"Failed to calculate bundle size: {e}")
    return (total_bytes + 1023) // 1024


def get_any_count(search_dir="src"):
    import shlex

    if not os.path.isdir(search_dir):
        log_warn(f"Search directory {search_dir} not found.")
        return 0
    safe_dir = shlex.quote(search_dir)
    cmd = f"grep -rn ': any\\b\\|as any\\b' {safe_dir} --include='*.tsx' --include='*.ts'"
    res = run_command(cmd, check=False, shell=True, log_on_error=False)
    if res.returncode == 0:
        return len(res.stdout.strip().split("\n")) if res.stdout.strip() else 0
    elif res.returncode == 1:
        return 0
    else:
        log_error(f"running grep: {res.stderr.strip()}")
        raise CLIError(f"Grep failed with exit code {res.returncode}")


def get_changed_files():
    from dev_tools.config import get_config

    config = get_config()
    base = config.base_branch
    res = run_command(["git", "diff", "--name-only", base], check=False, log_on_error=False)
    if res.returncode == 0:
        return res.stdout.strip().splitlines()
    res = run_command(["git", "diff", "--name-only", "HEAD"], check=False, log_on_error=False)
    if res.returncode == 0:
        return res.stdout.strip().splitlines()
    return []


def verify_pr_scope(file_list: Optional[List[str]] = None) -> Optional[str]:
    from dev_tools.config import get_config

    if file_list is None:
        file_list = get_changed_files()
    config = get_config()
    core_dirs = config.core_dirs
    threshold = config.monolithic_pr_threshold
    core_files = [f for f in file_list if any(f.startswith(d) for d in core_dirs)]
    if len(core_files) > threshold:
        return f"PR scope warning: Touching {len(core_files)} core files in {core_dirs}. Consider splitting this monolithic PR to avoid merge conflicts (AGENTS.md §23)."
    content_scopes = config.content_scopes
    from typing import Set

    active_scopes: Set[str] = set()
    for f in file_list:
        for scope_name, prefix in content_scopes.items():
            if f.startswith(prefix):
                active_scopes.add(scope_name)
    if len(active_scopes) > 1:
        scope_names = ", ".join(sorted(content_scopes.keys()))
        return f"Content scope warning: Mixed content domains detected ({', '.join(active_scopes)}). PRs should be split by scope: {scope_names} (AGENTS.md §21)."
    has_content = len(active_scopes) > 0
    code_files = [f for f in file_list if f.startswith("src/") and not any(f.startswith(d) for d in core_dirs)]
    if has_content and len(code_files) > 2:
        return "PR scope warning: Mixing significant code changes with content updates. Consider splitting content corrections from feature development."
    return None
