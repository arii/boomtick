#!/usr/bin/env python3
"""
Robust Python linting runner that ensures dependencies are available
either in the active/current environment or via a local virtual environment (.venv).
Robust Python linting runner that assumes the environment is already pre-warmed,
failing fast if required developer tools are missing.
"""
import os
import sys
import subprocess

# Ensure we can import from the local scripts package
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from lib.env_utils import get_venv_paths

def is_pylint_available(python_exe):
    """Checks if pylint is installed/available via the given python executable."""
    try:
        res = subprocess.run([python_exe, "-m", "pylint", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return res.returncode == 0
    except Exception:
        return False

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Check if the current python running this script already has pylint
    if is_pylint_available(sys.executable):
        pylint_cmd = [sys.executable, "-m", "pylint"]
    else:
        # 2. Check if local .venv has pylint
        venv_path = os.path.join(repo_root, ".venv")
        if sys.platform == "win32":
            python_bin = os.path.join(venv_path, "Scripts", "python.exe")
            pip_bin = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            python_bin = os.path.join(venv_path, "bin", "python")
            pip_bin = os.path.join(venv_path, "bin", "pip")

        if not os.path.exists(python_bin) or not is_pylint_available(python_bin):
            print("pylint not found in current environment or .venv. Setting up virtual environment...", flush=True)
            # Create venv if not exists
            if not os.path.exists(venv_path):
                subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)

            # Install dev tools and requirements
            print("Installing python dependencies into virtual environment...", flush=True)
            subprocess.run([pip_bin, "install", "--upgrade", "pip", "setuptools<81.0.0", "wheel"], check=True)

            # Editable install of cli and requirements
            cli_dir = os.path.join(repo_root, "cli")
            subprocess.run([pip_bin, "install", "-e", cli_dir], check=True)
            if os.path.exists(os.path.join(cli_dir, "requirements-dev.txt")):
                subprocess.run([pip_bin, "install", "-r", os.path.join(cli_dir, "requirements-dev.txt")], check=True)

        pylint_cmd = [python_bin, "-m", "pylint"]
        venv_path, python_bin = get_venv_paths(repo_root)

        if os.path.exists(python_bin) and is_pylint_available(python_bin):
            pylint_cmd = [python_bin, "-m", "pylint"]
        else:
            print("Error: pylint not found in current environment or .venv.", file=sys.stderr)
            print("Please run the bootstrap script first to configure your local environment:", file=sys.stderr)
            print("    pnpm run bootstrap:python", file=sys.stderr)
            sys.exit(1)

    # Gather arguments: use any passed arguments, or default to linting 'cli'
    args = sys.argv[1:]
    if not args:
        args = ["cli", f"--rcfile={os.path.join(repo_root, '.pylintrc')}"]

    cmd = pylint_cmd + args
    print(f"Executing: {' '.join(cmd)}", flush=True)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
