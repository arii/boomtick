#!/usr/bin/env python3
"""
Robust Python test runner that assumes the environment is already pre-warmed,
failing fast if pytest or other developer tools are missing.
"""
import os
import sys
import subprocess

# Ensure we can import from the local scripts package
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from lib.env_utils import get_venv_paths

def is_pytest_available(python_exe):
    """Checks if pytest is installed/available via the given python executable."""
    try:
        res = subprocess.run([python_exe, "-m", "pytest", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return res.returncode == 0
    except Exception:
        return False

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Check if the current python running this script already has pytest
    if is_pytest_available(sys.executable):
        pytest_cmd = [sys.executable, "-m", "pytest"]
    else:
        # 2. Check if local .venv has pytest
        venv_path, python_bin = get_venv_paths(repo_root)

        if os.path.exists(python_bin) and is_pytest_available(python_bin):
            pytest_cmd = [python_bin, "-m", "pytest"]
        else:
            print("Error: pytest not found in current environment or .venv.", file=sys.stderr)
            print("Please run the bootstrap script first to configure your local environment:", file=sys.stderr)
            print("    pnpm run bootstrap:python", file=sys.stderr)
            sys.exit(1)

    # Gather arguments: use any passed arguments, or default to checking 'cli/tests'
    args = sys.argv[1:]
    if not args:
        args = ["cli/tests"]

    cmd = pytest_cmd + args
    print(f"Executing: {' '.join(cmd)}", flush=True)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
