import os
import sys
import re
import json
from typing import Dict, List, Optional, Tuple

from dev_tools.utils import (
    get_stack_versions,
    log_info,
    log_error,
    log_warn,
    fetch_latest_npm,
    fetch_latest_gh_action,
    compare_versions
)

def parse_diff(diff_text: str) -> List[Dict]:
    """Parses a git diff to find version changes."""
    changes = []
    current_file = None

    # Regex patterns
    ACTION_PATTERN = re.compile(r"uses:\s+([\w\-/]+)@([\w\.]+)")
    PKG_JSON_VERSION_PATTERN = re.compile(r'"(node|pnpm|[\w\-\./@]+)":\s*"([\d\.\^x~<>=\| v]+)"')
    PM_PATTERN = re.compile(r'"packageManager":\s*"pnpm@([\d\.]+)"')

    # Files we care about
    SENSITIVE_FILES = [".nvmrc", ".node-version", "package.json"]
    SENSITIVE_DIRS = [".github/workflows/"]

    hunks = re.split(r"^(?=--- )", diff_text, flags=re.MULTILINE)
    for hunk in hunks:
        if not hunk.strip(): continue

        lines = hunk.splitlines()
        current_file = None
        for line in lines:
            if line.startswith("--- a/"):
                current_file = line[6:]
                break
            elif line.startswith("+++ b/"):
                current_file = line[6:]
                break

        if not current_file:
            continue

        is_sensitive = (current_file in SENSITIVE_FILES or
                        any(current_file.startswith(sd) for sd in SENSITIVE_DIRS))
        if not is_sensitive:
            continue

        removals = {} # name -> version
        additions = {} # name -> version

        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@ "):
                continue

            if line.startswith("-"):
                content = line[1:].strip()
                # Check Actions
                m = ACTION_PATTERN.search(content)
                if m: removals[m.group(1)] = m.group(2)
                # Check Dependencies
                m = PKG_JSON_VERSION_PATTERN.search(content)
                if m: removals[m.group(1)] = m.group(2)
                # Check pnpm
                m = PM_PATTERN.search(content)
                if m: removals["pnpm"] = m.group(1)
                # Check node files
                if current_file in [".nvmrc", ".node-version"]:
                    removals["node"] = content.replace("v", "")

            elif line.startswith("+"):
                content = line[1:].strip()
                m = ACTION_PATTERN.search(content)
                if m: additions[m.group(1)] = m.group(2)
                m = PKG_JSON_VERSION_PATTERN.search(content)
                if m: additions[m.group(1)] = m.group(2)
                m = PM_PATTERN.search(content)
                if m: additions["pnpm"] = m.group(1)
                if current_file in [".nvmrc", ".node-version"]:
                    additions["node"] = content.replace("v", "")

        # Correlate changes
        for name, new_v in additions.items():
            old_v = removals.get(name, "unknown")
            type_val = "action" if "/" in name and "pnpm" not in name else "dependency"
            if name == "node" or current_file in [".nvmrc", ".node-version"]: type_val = "runtime"

            changes.append({
                "file": current_file,
                "type": type_val,
                "name": name,
                "old": old_v,
                "new": new_v
            })

    return changes

def verify_changes(changes: List[Dict]) -> List[Dict]:
    """Verifies changes against HEAD and registries."""
    findings = []
    stack = get_stack_versions()

    for c in changes:
        # 1. Compare against HEAD (Downgrade detection)
        head_v = stack.get(c["name"])
        if not head_v and c["name"] == "node": head_v = stack.get("node")
        if not head_v and c["name"] == "pnpm": head_v = stack.get("pnpm")

        if head_v:
            if compare_versions(c["new"], head_v) < 0:
                findings.append({
                    "severity": "error",
                    "file": c["file"],
                    "message": f"Version downgrade detected for {c['name']}: {head_v} -> {c['new']}",
                    "type": "downgrade"
                })

        # 2. Compare against Latest (Outdated detection - optional warning)
        from dev_tools.utils import fetch_latest_node # Import node fetcher
        latest = None
        if c["name"] == "node":
            latest = fetch_latest_node()
        elif c["type"] == "action":
            latest = fetch_latest_gh_action(c["name"])
        elif c["name"] in ["pnpm"] or c["type"] == "dependency":
             latest = fetch_latest_npm(c["name"])

        if latest:
            if compare_versions(c["new"], latest) < 0:
                findings.append({
                    "severity": "warn",
                    "file": c["file"],
                    "message": f"Proposed version for {c['name']} ({c['new']}) is outdated. Latest is {latest}.",
                    "type": "outdated"
                })

        # 3. Node.js Hard Block
        if c["name"] == "node":
             # Only trigger hard block if the version is ACTUALLY changing from HEAD
             if head_v and compare_versions(c["new"], head_v) != 0:
                 if os.environ.get("ALLOW_NODE_VERSION_CHANGE") != "true":
                     findings.append({
                        "severity": "error",
                        "file": c["file"],
                        "message": f"Hard block: Node.js version modification detected ({head_v} -> {c['new']}). Modification is forbidden unless ALLOW_NODE_VERSION_CHANGE=true.",
                        "type": "hard_block"
                    })

    return findings

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_versions.py <diff_file_or_text>")
        sys.exit(1)

    input_val = sys.argv[1]
    if os.path.exists(input_val):
        with open(input_val, "r") as f:
            diff_text = f.read()
    else:
        diff_text = input_val

    changes = parse_diff(diff_text)
    findings = verify_changes(changes)

    if findings:
        print(json.dumps(findings, indent=2))
        # Exit with error code if any 'error' severity exists
        if any(f["severity"] == "error" for f in findings):
            sys.exit(1)
    else:
        print(json.dumps([], indent=2))

    sys.exit(0)

if __name__ == "__main__":
    main()
