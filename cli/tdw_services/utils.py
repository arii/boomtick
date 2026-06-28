import sys
import re

def mask_sensitive_data(msg: str) -> str:
    """Redacts sensitive information like GitHub tokens from strings."""
    if not isinstance(msg, str):
        msg = str(msg)

    # Redact GitHub Tokens (Personal Access Tokens and Fine-grained Tokens)
    msg = re.sub(r'ghp_[a-zA-Z0-9]{36,}', 'ghp_***', msg)
    msg = re.sub(r'github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59,}', 'github_pat_***', msg)

    # Generic token redaction for URLs or assignments (e.g., token=ABC123xyz)
    msg = re.sub(r'(?i)(token|auth|key|secret|password|access_token)([:=])[a-zA-Z0-9._-]{10,}', r'\1\2***', msg)

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

def get_base_dir() -> str:
    """Returns the absolute path to the CLI package root."""
    import os
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def ensure_dir(*parts: str) -> str:
    """Joins path parts, ensures the directory exists, and returns the absolute path."""
    import os
    path = os.path.join(get_base_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path
