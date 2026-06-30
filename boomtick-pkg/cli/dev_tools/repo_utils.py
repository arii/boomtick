import os
import re
import sys
import glob
import shlex
from typing import Optional, List, Tuple, Union
from collections import defaultdict

# Import run_command from utils
from utils import run_command, CLIError
try:
    from tdw_services.utils import log_error, log_warn
except ImportError:
    def log_error(msg): print(f"❌ Error: {msg}", file=sys.stderr)
    def log_warn(msg): print(f"⚠️  Warning: {msg}", file=sys.stderr)

# Use existing github_utils if possible, but we'll add common repo walking/matching logic here
def walk_tsx(root_dir='src'):
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.tsx'):
                yield os.path.join(root, file)

def find_patterns_in_file(filepath, patterns):
    """
    patterns: List of (regex_str, message)
    Returns: List of (line_num, message, match_str)
    """
    findings = []
    with open(filepath, 'r') as f:
        content = f.read()
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for pattern, message in patterns:
                match = re.search(pattern, line)
                if match:
                    findings.append((i + 1, message, match.group()))
    return findings

def get_bundle_size(dist_dir='dist/assets'):
    """Returns bundle size in KB."""
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

    # Return size in KB (rounded up to match du -k behavior roughly)
    return (total_bytes + 1023) // 1024

def get_any_count(search_dir='src'):
    """Returns count of 'any' usages in TS/TSX files."""
    if not os.path.isdir(search_dir):
        log_warn(f"Search directory {search_dir} not found.")
        return 0

    safe_dir = shlex.quote(search_dir)
    # Using check=False because grep exits non-zero on no matches
    cmd = f"grep -rn ': any\\b\\|as any\\b' {safe_dir} --include='*.tsx' --include='*.ts'"
    res = run_command(cmd, check=False, shell=True, log_on_error=False)

    if res.returncode == 0:
        return len(res.stdout.strip().split('\n')) if res.stdout.strip() else 0
    elif res.returncode == 1:
        return 0
    else:
        log_error(f"running grep: {res.stderr.strip()}")
        raise CLIError(f"Grep failed with exit code {res.returncode}")
