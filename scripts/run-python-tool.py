#!/usr/bin/env python3
"""
Robust Python tool runner that assumes the environment is already pre-warmed,
failing fast if the required developer tool is missing.
"""
import os
import sys
import subprocess

# Ensure we can import from the local scripts package
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from lib.env_utils import get_venv_paths

def is_tool_available(python_exe, tool_module):
    """Checks if a tool is installed/available via the given python executable."""
    try:
        res = subprocess.run([python_exe, "-m", tool_module, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return res.returncode == 0
    except Exception:
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: run-python-tool.py <tool_module> [args...]", file=sys.stderr)
        sys.exit(1)

    tool_module = sys.argv[1]
    args = sys.argv[2:]

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Check if the current python running this script already has the tool
    if is_tool_available(sys.executable, tool_module):
        tool_cmd = [sys.executable, "-m", tool_module]
    else:
        # 2. Check if local .venv has the tool
        venv_path, python_bin = get_venv_paths(repo_root)

        if os.path.exists(python_bin) and is_tool_available(python_bin, tool_module):
            tool_cmd = [python_bin, "-m", tool_module]
        else:
            print(f"Error: {tool_module} not found in current environment or .venv.", file=sys.stderr)
            print("Please run the bootstrap script first to configure your local environment:", file=sys.stderr)
            print("    pnpm run bootstrap:python", file=sys.stderr)
            sys.exit(1)

    # Some defaults for tools if args are not passed
    if tool_module == "pylint" and not args:
        args = ["cli", f"--rcfile={os.path.join(repo_root, '.pylintrc')}"]
    elif tool_module == "pytest" and not args:
        args = ["cli/tests"]
    elif tool_module == "mypy" and not args:
        args = ["cli", "--ignore-missing-imports"]

    cmd = tool_cmd + args
    print(f"Executing: {' '.join(cmd)}", flush=True)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
