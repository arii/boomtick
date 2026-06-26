import sys

def log_info(msg: str):
    """Logs an informational message to stderr."""
    print(msg, file=sys.stderr)

def log_error(msg: str):
    """Logs an error message to stderr."""
    print(f"❌ Error: {msg}", file=sys.stderr)

def log_warn(msg: str):
    """Logs a warning message to stderr."""
    print(f"⚠️  Warning: {msg}", file=sys.stderr)

def log_debug(msg: str):
    """Logs a debug message to stderr."""
    print(f"DEBUG: {msg}", file=sys.stderr)
