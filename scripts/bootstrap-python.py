#!/usr/bin/env python3
"""
Centralized Toolchain Bootstrapping for Python Workspace Dependencies.
Sets up the Python virtual environment (.venv) and provisions all required dependencies.
"""
import os
import sys
import subprocess

# Ensure we can import from the local scripts package
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from lib.env_utils import get_venv_paths

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Verify that the script is being executed from the repository root
    package_json_path = os.path.join(repo_root, "package.json")
    if not os.path.exists(package_json_path):
        print("Error: bootstrap-python.py must be run from within the repository structure.", file=sys.stderr)
        sys.exit(1)

    venv_path, python_bin = get_venv_paths(repo_root)

    print("=== Centralized Python Toolchain Bootstrapping ===", flush=True)
    print(f"Workspace root: {repo_root}", flush=True)
    print(f"Virtual environment path: {venv_path}", flush=True)

    # 1. Create venv if it does not exist
    if not os.path.exists(venv_path):
        print("Creating virtual environment (.venv)...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
    else:
        print("Virtual environment already exists. Upgrading dependencies...", flush=True)

    # 2. Upgrade pip, setuptools, wheel, and install uv
    print("Upgrading pip and installing uv, setuptools, and wheel...", flush=True)
    subprocess.run([python_bin, "-m", "pip", "install", "--upgrade", "pip", "uv"], check=True)
    subprocess.run([python_bin, "-m", "uv", "pip", "install", "setuptools<81.0.0", "wheel"], check=True)

    # 4. Perform editable install of the CLI package
    cli_dir = os.path.join(repo_root, "cli")
    print(f"Installing CLI package in editable mode from {cli_dir}...", flush=True)
    subprocess.run([python_bin, "-m", "uv", "pip", "install", "-e", cli_dir], check=True)

    # 5. Gather requirements files that exist to install them in a single resolution pass
    req_args = []

    reqs_path = os.path.join(cli_dir, "requirements.txt")
    if os.path.exists(reqs_path):
        req_args.extend(["-r", reqs_path])

    dev_reqs_path = os.path.join(cli_dir, "requirements-dev.txt")
    if os.path.exists(dev_reqs_path):
        req_args.extend(["-r", dev_reqs_path])

    ai_reqs_path = os.path.join(cli_dir, "requirements-ai.txt")
    if os.path.exists(ai_reqs_path):
        req_args.extend(["-r", ai_reqs_path])

    pinned_reqs_path = os.path.join(cli_dir, "requirements-pinned.txt")
    if os.path.exists(pinned_reqs_path):
        req_args.extend(["-r", pinned_reqs_path])

    if req_args:
        print("Installing dependencies in a single resolution pass...", flush=True)
        subprocess.run([python_bin, "-m", "uv", "pip", "install"] + req_args, check=True)

    print("✅ Python toolchain bootstrapping completed successfully!", flush=True)

if __name__ == "__main__":
    main()
