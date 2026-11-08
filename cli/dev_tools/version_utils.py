# pylint: disable=import-outside-toplevel,missing-docstring,too-many-branches,too-many-locals,too-many-return-statements,cyclic-import
import json
import os
import re
import sys
from typing import Dict, Optional

import requests
from packaging import version


def log_warn(msg: str):
    print(f"⚠️  Warning: {msg}", file=sys.stderr)


def log_error(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)


# Registry Cache
_NPM_CACHE: Dict[str, str] = {}
_GITHUB_CACHE: Dict[str, str] = {}


def fetch_latest_npm(package_name: str) -> Optional[str]:
    if package_name in _NPM_CACHE:
        return _NPM_CACHE[package_name]
    try:
        url = f"https://registry.npmjs.org/{package_name}/latest"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            ver = res.json().get("version")
            _NPM_CACHE[package_name] = ver
            return ver
    except Exception as e:
        log_warn(f"Failed to fetch latest NPM version for {package_name}: {e}")
    return None


def fetch_latest_node() -> Optional[str]:
    if "node" in _NPM_CACHE:
        return _NPM_CACHE["node"]
    try:
        url = "https://nodejs.org/dist/index.json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            # Latest is the first one
            ver = res.json()[0].get("version").lstrip("v")
            _NPM_CACHE["node"] = ver
            return ver
    except Exception as e:
        log_warn(f"Failed to fetch latest Node.js version: {e}")
    return None


def fetch_latest_gh_action(action_path: str) -> Optional[str]:
    if action_path in _GITHUB_CACHE:
        return _GITHUB_CACHE[action_path]
    try:
        url = f"https://api.github.com/repos/{action_path}/releases/latest"
        headers = {}
        # Try to use token if available
        from dev_tools.utils import get_github_token

        token = get_github_token()
        if token:
            headers["Authorization"] = f"token {token}"

        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            tag = res.json().get("tag_name")
            _GITHUB_CACHE[action_path] = tag
            return tag
    except Exception as e:
        log_warn(f"Failed to fetch latest GitHub Action version for {action_path}: {e}")
    return None


def compare_versions(v1: str, v2: str) -> int:
    """Returns 1 if v1 > v2, -1 if v1 < v2, 0 if v1 == v2."""
    if v1 == v2:
        return 0
    try:
        v1_clean = v1.lstrip("v")
        v2_clean = v2.lstrip("v")

        if ".x" in v1_clean:
            v1_clean = v1_clean.replace(".x", ".0")
        if ".x" in v2_clean:
            v2_clean = v2_clean.replace(".x", ".0")

        pv1 = version.parse(v1_clean)
        pv2 = version.parse(v2_clean)
        if pv1 > pv2:
            return 1
        if pv1 < pv2:
            return -1
        return 0
    except Exception:
        if v1 > v2:
            return 1
        if v1 < v2:
            return -1
        return 0


# NOTE (config-hygiene #1172): .node-version is the single source of truth
# for the required Node version. There is no hardcoded fallback: a missing
# file fails instead of silently pinning a stale version.
def read_node_version() -> str:
    """Reads the required Node version from .node-version. Fails if absent."""
    with open(".node-version", "r", encoding="utf-8") as f:
        v = f.read().strip().lstrip("v")
    if not v:
        raise ValueError(".node-version is empty; it must contain the required Node version.")
    return v


# NOTE (config-hygiene #1172): package.json (packageManager, then
# engines.pnpm) is the single source of truth for the required pnpm
# version. There is no hardcoded fallback: a missing declaration fails.
def read_pnpm_version() -> str:
    """Reads the required pnpm version from package.json. Fails if absent."""
    with open("package.json", "r", encoding="utf-8") as f:
        pkg = json.load(f)
    if "packageManager" in pkg:
        return pkg["packageManager"].replace("pnpm@", "")
    if "engines" in pkg and "pnpm" in pkg["engines"]:
        return pkg["engines"]["pnpm"]
    raise ValueError("package.json must declare the pnpm version via packageManager or engines.pnpm.")


def get_stack_versions(fetch_latest: bool = False) -> Dict[str, str]:
    """Extracts core versions (Node, pnpm, GHA) from the repository."""
    # NOTE (config-hygiene #1172): canonical reads happen up front so a
    # missing contract file fails instead of falling back to hardcoded versions.
    versions = {
        "node": read_node_version(),
        "pnpm": read_pnpm_version(),
        "actions/checkout": "v4",
        "actions/setup-node": "v4",
        "actions/upload-artifact": "v4",
    }

    try:
        workflow_dir = ".github/workflows"
        if os.path.exists(workflow_dir):
            for filename in os.listdir(workflow_dir):
                if not (filename.endswith(".yml") or filename.endswith(".yaml")):
                    continue
                try:
                    with open(os.path.join(workflow_dir, filename), "r", encoding="utf-8") as f:
                        content = f.read()
                        matches = re.findall(r"uses:\s+([\w\-/]+)@([\w\.]+)", content)
                        for action, v_str in matches:
                            if not action.startswith("actions/"):
                                continue
                            current_v = versions.get(action)
                            if not current_v or compare_versions(v_str, current_v) > 0:
                                versions[action] = v_str
                except Exception as e:
                    log_warn(f"Failed to read workflow {filename}: {e}")

        if fetch_latest:
            latest_node = fetch_latest_node()
            if latest_node:
                versions["latest_node"] = latest_node

            latest_pnpm = fetch_latest_npm("pnpm")
            if latest_pnpm:
                versions["latest_pnpm"] = latest_pnpm

            for action in ["actions/checkout", "actions/setup-node"]:
                latest_a = fetch_latest_gh_action(action)
                if latest_a:
                    versions[f"latest_{action}"] = latest_a

    except Exception as e:
        log_error(f"Unexpected error in get_stack_versions: {e}")

    return versions
