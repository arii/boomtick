#!/usr/bin/env python3
"""
Lightweight Scope Verification Tool
Parses the initial issue description and compares it against the git diff --name-only output.
Strictly prevents modifications to files outside the direct scope of the reported issue.
"""
import os
import sys
import argparse
import re
import subprocess
import json

EXEMPT_FILES = {
    "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "project_config.json",
    "tsconfig.json", "workspace.json", ".gitignore", ".dockerignore", ".pylintrc",
    "eslint.config.mjs", "oxlint.json", "tsconfig.app.json", ".release-please-manifest.json",
    "release-please-config.json", "changelog.md", "readme.md", "agents.md", "ci.yml",
    "verify-scope.py", "test_verify_scope.py", "reviewpromptconstants.ts", "prompt_constants.json",
    "__init__.py", "verdict.ts", "impact-ai-code-review.ts", "requirements-dev.txt", ".gitkeep"
}

def get_changed_files(base_branch=None):
    files = set()

    if not base_branch:
        base_ref = os.environ.get("GITHUB_BASE_REF")
        if base_ref:
            base_branch = f"origin/{base_ref}"
        else:
            base_branch = "origin/main"

    # Try diffing directly against base branch (compares base branch commit to the working directory)
    res = subprocess.run(["git", "diff", "--name-only", base_branch], capture_output=True, text=True, check=False)
    if res.returncode == 0:
        files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
    else:
        # Fallback to main
        res = subprocess.run(["git", "diff", "--name-only", "main"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
        else:
            # Fallback to HEAD~1 to catch local changes if base branches are not available
            res = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True, check=False)
            if res.returncode == 0:
                files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
            else:
                res = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, check=False)
                if res.returncode == 0:
                    files.update(f.strip() for f in res.stdout.splitlines() if f.strip())

    # Also include untracked files to be extremely thorough and developer-friendly!
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=False)
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            if line.startswith("?? "):
                files.add(line[3:].strip())

    return sorted(list(files))

def fetch_issue_description(issue_file=None, issue_body=None, issue_number=None):
    if issue_body:
        return issue_body

    if issue_file and os.path.exists(issue_file):
        with open(issue_file, "r", encoding="utf-8") as f:
            return f.read()

    # Check GITHUB_EVENT_PATH
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request", {})
            body = pr.get("body") or ""
            title = pr.get("title") or ""

            issue = event.get("issue", {})
            body = body or issue.get("body") or ""
            title = title or issue.get("title") or ""

            if body or title:
                return f"{title}\n\n{body}"
        except Exception:
            pass

    # Try using gh CLI if issue_number is provided
    if issue_number:
        try:
            res = subprocess.run(["gh", "issue", "view", str(issue_number), "--json", "title,body"], capture_output=True, text=True, check=False)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return f"{data.get('title', '')}\n\n{data.get('body', '')}"
        except Exception:
            pass

    # Try looking for task_description.md or similar files in workspace
    for fallback_path in ["task_description.md", "issue_description.md", ".agents/task_description.md"]:
        if os.path.exists(fallback_path):
            with open(fallback_path, "r", encoding="utf-8") as f:
                return f.read()

    return None

def normalize_name(name: str) -> str:
    return name.replace("_", "-").lower()

def is_test_file_for_in_scope(filepath: str, allowed_base_names: set) -> bool:
    lower_path = filepath.lower()
    if "test" not in lower_path and "spec" not in lower_path:
        return False

    filename = os.path.basename(filepath).lower()
    base = filename
    for pattern in ["test_", "_test", ".test", ".spec"]:
        base = base.replace(pattern, "")

    base_no_ext = os.path.splitext(base)[0]
    norm_base_no_ext = normalize_name(base_no_ext)

    for allowed in allowed_base_names:
        norm_allowed = normalize_name(allowed)
        if norm_base_no_ext in norm_allowed or norm_allowed in norm_base_no_ext:
            return True

    return False

def check_override():
    if os.environ.get("SCOPE_OVERRIDE") == "true":
        return True

    # Check git commit message for bypass tags
    try:
        res = subprocess.run(["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            msg = res.stdout.lower()
            if "[skip-scope-check]" in msg or "[scope-override]" in msg or "skip-scope" in msg:
                return True
    except Exception:
        pass

    return False

def check_scope(changed_files, issue_text):
    if not issue_text:
        # If no issue text is found, we warning and pass to prevent blocking if run locally without metadata
        return True, [], []

    issue_text_lower = issue_text.lower()

    # Extract everything that looks like a file name, file path, or directory path
    path_regex = r'[a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+'
    mentioned_files = set(re.findall(path_regex, issue_text_lower))

    # Extract directories
    dir_regex = r'[a-zA-Z0-9_\-\./]+/'
    mentioned_dirs = set(re.findall(dir_regex, issue_text_lower))

    # Extract single words/tokens
    word_regex = r'[a-zA-Z0-9_\-]+'
    mentioned_words = set(re.findall(word_regex, issue_text_lower))
    stop_words = {
        "with", "this", "that", "from", "your", "have", "will", "mode", "flag", "test", "file", "spec",
        "tool", "mode", "strict", "scope", "hook", "hooks", "commit", "issue", "branch", "main", "origin",
        "unrequested", "modification", "modifications", "unrelated", "runner", "release", "publish",
        "build", "docker", "setup", "buildx", "workflow", "workflows", "verification", "mechanism"
    }
    mentioned_words = {w for w in mentioned_words if len(w) > 3 and w not in stop_words}

    allowed_base_names = set()
    for f in mentioned_files:
        filename = os.path.basename(f)
        base = os.path.splitext(filename)[0]
        allowed_base_names.add(base.lower())

    allowed_files = []
    disallowed_files = []

    for filepath in changed_files:
        filepath_lower = filepath.lower()
        filename_lower = os.path.basename(filepath).lower()
        base_lower = os.path.splitext(filename_lower)[0]

        # 1. Exempt files
        if filename_lower in EXEMPT_FILES:
            allowed_files.append((filepath, "Exempt configuration/readme/tooling file"))
            continue

        # 2. Exact match in mentioned files
        if any(mf in filepath_lower or filepath_lower in mf for mf in mentioned_files):
            allowed_files.append((filepath, "Exact path/pattern mentioned in issue"))
            continue

        if any(mf in filename_lower or filename_lower in mf for mf in mentioned_files):
            allowed_files.append((filepath, "Filename mentioned in issue"))
            continue

        # 3. Directory match
        is_in_mentioned_dir = False
        for md in mentioned_dirs:
            md_clean = md.strip("/")
            if md_clean and any(part == md_clean for part in filepath_lower.split("/")):
                is_in_mentioned_dir = True
                break
        if is_in_mentioned_dir:
            allowed_files.append((filepath, f"Located in mentioned directory: {md}"))
            continue

        # 4. Test file for an allowed file
        if is_test_file_for_in_scope(filepath, allowed_base_names):
            allowed_files.append((filepath, "Test file for an in-scope source file"))
            continue

        # 5. Base name match
        norm_base_lower = normalize_name(base_lower)
        is_base_matched = False
        for ab in allowed_base_names:
            if norm_base_lower == normalize_name(ab):
                is_base_matched = True
                break
        if not is_base_matched:
            for w in mentioned_words:
                if norm_base_lower == normalize_name(w):
                    is_base_matched = True
                    break

        if is_base_matched:
            allowed_files.append((filepath, "Base name/key token matched in issue"))
            continue

        disallowed_files.append(filepath)

    return len(disallowed_files) == 0, allowed_files, disallowed_files

def main():
    parser = argparse.ArgumentParser(description="Verify that modified files are within the direct scope of the reported issue.")
    parser.add_argument("--issue-file", help="Path to a file containing the issue description/body")
    parser.add_argument("--issue-body", help="Direct text of the issue description/body")
    parser.add_argument("--issue-number", type=int, help="GitHub issue/PR number to fetch description for")
    parser.add_argument("--base-branch", help="Git base branch to compare against (e.g. origin/main)")
    parser.add_argument("--strict-scope", action="store_true", help="Fail with exit code 1 if out-of-scope files are found")

    args = parser.parse_args()

    # Check bypass / override
    if check_override():
        print("⚠️ Scope verification bypassed via explicit override.")
        sys.exit(0)

    issue_text = fetch_issue_description(args.issue_file, args.issue_body, args.issue_number)
    changed_files = get_changed_files(args.base_branch)

    if not issue_text:
        print("⚠️ Warning: Initial issue description could not be fetched/auto-detected. Skipping strict scope check.")
        sys.exit(0)

    success, allowed, disallowed = check_scope(changed_files, issue_text)

    print("\n--- Scope Verification Report ---")
    print(f"Total files checked: {len(changed_files)}")
    print(f"Allowed files: {len(allowed)}")
    for f, reason in allowed:
        print(f"  ✅ {f} ({reason})")

    if disallowed:
        print(f"\n❌ Out-of-Scope files detected: {len(disallowed)}")
        for f in disallowed:
            print(f"  🚨 {f}")

        print("\nError: Modifications to files outside the direct scope of the reported issue violate the 'minimize scope creep' directive.")
        print("To resolve this, please either:")
        print("  1. Revert modifications to the out-of-scope files.")
        print("  2. If the modifications are necessary, mention them in the PR body or issue description so they are parsed.")
        print("  3. Bypass this check by setting the SCOPE_OVERRIDE=true environment variable or adding '[skip-scope-check]' to your last commit message.")

        if args.strict_scope:
            sys.exit(1)
        else:
            print("\n⚠️ Running in warning-only mode. Strict mode (--strict-scope) was not enabled.")

    else:
        print("\n🎉 Success: All modified files are within the permitted issue scope!")

    sys.exit(0)

if __name__ == "__main__":
    main()
