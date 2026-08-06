#!/usr/bin/env python3
"""
Centralized Toolchain Bootstrapping for Python Workspace Dependencies.
Sets up the Python virtual environment (.venv) and provisions all required dependencies.
"""
import os
import sys
import subprocess

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Verify that the script is being executed from the repository root
    package_json_path = os.path.join(repo_root, "package.json")
    if not os.path.exists(package_json_path):
        print("Error: bootstrap-python.py must be run from within the repository structure.", file=sys.stderr)
        sys.exit(1)

    venv_path = os.path.join(repo_root, ".venv")

    print("=== Centralized Python Toolchain Bootstrapping ===", flush=True)
    print(f"Workspace root: {repo_root}", flush=True)
    print(f"Virtual environment path: {venv_path}", flush=True)

    # 1. Create venv if it does not exist
    if not os.path.exists(venv_path):
        print("Creating virtual environment (.venv)...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
    else:
        print("Virtual environment already exists. Upgrading dependencies...", flush=True)

    # 2. Get platform-specific paths for python
    if sys.platform == "win32":
        python_bin = os.path.join(venv_path, "Scripts", "python.exe")
    else:
        python_bin = os.path.join(venv_path, "bin", "python")

    # 3. Upgrade pip, setuptools, wheel
    print("Upgrading pip, setuptools, and wheel...", flush=True)
    subprocess.run([python_bin, "-m", "pip", "install", "--upgrade", "pip", "setuptools<81.0.0", "wheel"], check=True)

    # 4. Perform editable install of the CLI package
    cli_dir = os.path.join(repo_root, "cli")
    print(f"Installing CLI package in editable mode from {cli_dir}...", flush=True)
    subprocess.run([python_bin, "-m", "pip", "install", "-e", cli_dir], check=True)

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

    if req_args:
        print("Installing dependencies in a single resolution pass...", flush=True)
        subprocess.run([python_bin, "-m", "pip", "install"] + req_args, check=True)

    # 6. Force/Pin opentelemetry dependencies to exactly version 1.37.0 to prevent semgrep and runtime compatibility issues
    print("Pinning opentelemetry packages to 1.37.0 to avoid conflicts...", flush=True)
    subprocess.run([
        python_bin, "-m", "pip", "install",
        "opentelemetry-api==1.37.0",
        "opentelemetry-sdk==1.37.0",
        "opentelemetry-proto==1.37.0",
        "opentelemetry-exporter-otlp-proto-common==1.37.0",
        "opentelemetry-exporter-otlp-proto-grpc==1.37.0",
        "opentelemetry-exporter-otlp-proto-http==1.37.0"
    ], check=True)

    print("✅ Python toolchain bootstrapping completed successfully!", flush=True)

if __name__ == "__main__":
    main()
