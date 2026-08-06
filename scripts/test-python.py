#!/usr/bin/env python3
"""
Robust Python test runner that ensures dependencies are available
either in the active/current environment or via a local virtual environment (.venv).
"""
import os
import sys
import subprocess

def is_env_ready(python_exe):
    """Checks if pytest and the dev_tools module are available via the given python executable."""
    try:
        # Check pytest
        res_pytest = subprocess.run([python_exe, "-c", "import pytest"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        # Check dev_tools
        res_dev_tools = subprocess.run([python_exe, "-c", "import dev_tools"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return res_pytest.returncode == 0 and res_dev_tools.returncode == 0
    except Exception:
        return False

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Check if the current python running this script already has both pytest and dev_tools
    if is_env_ready(sys.executable):
        pytest_cmd = [sys.executable, "-m", "pytest"]
    else:
        # 2. Check if local .venv has pytest and dev_tools
        venv_path = os.path.join(repo_root, ".venv")
        if sys.platform == "win32":
            python_bin = os.path.join(venv_path, "Scripts", "python.exe")
            pip_bin = os.path.join(venv_path, "Scripts", "pip.exe")
        else:
            python_bin = os.path.join(venv_path, "bin", "python")
            pip_bin = os.path.join(venv_path, "bin", "pip")

        if not os.path.exists(python_bin) or not is_env_ready(python_bin):
            print("Required environment (pytest and dev_tools) not found. Setting up virtual environment...", flush=True)
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

        pytest_cmd = [python_bin, "-m", "pytest"]

    # Gather arguments: use any passed arguments, or default to running 'cli/tests'
    args = sys.argv[1:]
    if not args:
        args = [os.path.join(repo_root, "cli", "tests")]

    cmd = pytest_cmd + args
    print(f"Executing: {' '.join(cmd)}", flush=True)

    result = subprocess.run(cmd)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
