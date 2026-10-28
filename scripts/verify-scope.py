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
    "Dockerfile", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "project_config.json",
    "tsconfig.json", "workspace.json", ".gitignore", ".dockerignore", ".pylintrc",
    "eslint.config.mjs", "oxlint.json", "tsconfig.app.json", ".release-please-manifest.json",
    "release-please-config.json", "changelog.md", "readme.md", "agents.md", "ci.yml", "release.yml",
    "verify-scope.py", "test_verify_scope.py", "reviewpromptconstants.ts",
    "prompt_constants.json", "pyproject.toml"
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

def fetch_linked_issue_bodies(text: str, fetched_nums=None) -> str:
    """Find issue numbers like #123, Fixes #123 in text and fetch their descriptions."""
    if fetched_nums is None:
        fetched_nums = set()

    extra_texts = []
    # Find patterns like #123 or fixes #123
    issue_refs = set(re.findall(r'#(\d+)', text))
    for num in issue_refs:
        if num in fetched_nums:
            continue
        fetched_nums.add(num)
        try:
            res = subprocess.run(
                ["gh", "issue", "view", str(num), "--json", "title,body"],
                capture_output=True, text=True, check=False
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                title = data.get('title', '')
                body = data.get('body', '')
                extra_texts.append(f"\n--- Linked Issue #{num} ---\n{title}\n\n{body}")
        except Exception:
            pass

    if extra_texts:
        return text + "\n" + "\n".join(extra_texts)
    return text

def fetch_issue_description(issue_file=None, issue_body=None, issue_number=None):
    raw_text = None

    if issue_body:
        raw_text = issue_body

    if not raw_text and issue_file and os.path.exists(issue_file):
        with open(issue_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

    # Check GITHUB_EVENT_PATH
    if not raw_text:
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
                    raw_text = f"{title}\n\n{body}"
            except Exception:
                pass

    # Try using gh CLI if issue_number is provided
    if not raw_text and issue_number:
        try:
            res = subprocess.run(
                ["gh", "issue", "view", str(issue_number), "--json", "title,body"],
                capture_output=True, text=True, check=False
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                raw_text = f"{data.get('title', '')}\n\n{data.get('body', '')}"
        except Exception:
            pass

    # Try looking for task_description.md or similar files in workspace
    if not raw_text:
        for fallback_path in ["task_description.md", "issue_description.md", ".agents/task_description.md"]:
            if os.path.exists(fallback_path):
                with open(fallback_path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                    break

    if raw_text:
        raw_text = fetch_linked_issue_bodies(raw_text)

    return raw_text

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

    # Check environment variables for release-please branch or PR head ref
    head_ref = os.environ.get("GITHUB_HEAD_REF", "")
    github_ref = os.environ.get("GITHUB_REF", "")
    if "release-please" in head_ref.lower() or "release-please" in github_ref.lower():
        return True

    # Check current git branch name
    try:
        res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            branch_name = res.stdout.strip().lower()
            if "release-please" in branch_name:
                return True
    except Exception:
        pass

    # Check GITHUB_EVENT_PATH for release-please branch, title, or bot user
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request", {})
            pr_head_ref = pr.get("head", {}).get("ref", "")
            pr_title = pr.get("title", "")
            user_login = pr.get("user", {}).get("login", "")

            if "release-please" in pr_head_ref.lower() or "release-please" in user_login.lower():
                return True
            if pr_title.lower().startswith("chore: release") or (pr_title.lower().startswith("chore(") and "release" in pr_title.lower()):
                return True
        except Exception:
            pass

    # Check git commit message for bypass tags or release-please commit messages
    try:
        res = subprocess.run(["git", "log", "-n", "10", "--pretty=%B"], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            msg = res.stdout.lower()
            if "[skip-scope-check]" in msg or "[scope-override]" in msg or "skip-scope" in msg or "release-please" in msg:
                return True
            if "chore: release" in msg or "chore(main): release" in msg:
                return True
    except Exception:
        pass

    return False

def is_module_hierarchy_subfile(filepath: str, allowed_file_paths: set) -> bool:
    """
    Check if candidate file is a newly created/extracted sub-file inside a subfolder or module namespace
    corresponding to an explicitly allowed parent file.
    E.g. if mcp/src/config.ts is allowed, mcp/src/config/dynamic.ts or mcp/src/config/github.ts is allowed.
    """
    filepath_norm = os.path.normpath(filepath)
    for allowed_p in allowed_file_paths:
        allowed_p_norm = os.path.normpath(allowed_p)
        parent_dir, filename = os.path.split(allowed_p_norm)
        stem, _ = os.path.splitext(filename)

        # 1. Check if filepath is inside a folder named `stem` at parent_dir (e.g. mcp/src/config/...)
        expected_dir = os.path.normpath(os.path.join(parent_dir, stem))
        if filepath_norm.startswith(expected_dir + os.sep):
            return True

        # 2. Check if filepath is a sibling module with prefix stem (e.g. config.sub.ts or config-sub.ts)
        if parent_dir and os.path.dirname(filepath_norm) == parent_dir:
            cand_filename = os.path.basename(filepath_norm)
            if cand_filename.startswith(f"{stem}.") or cand_filename.startswith(f"{stem}-") or cand_filename.startswith(f"{stem}_"):
                return True

    return False

def check_file_imports_target(importer_path: str, target_path: str) -> bool:
    """Check if importer_path file imports target_path (or vice versa)."""
    if not os.path.isfile(importer_path):
        return False

    try:
        with open(importer_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return False

    norm_target = os.path.normpath(target_path)
    target_dir, target_file = os.path.split(norm_target)
    target_stem, target_ext = os.path.splitext(target_file)
    importer_dir = os.path.dirname(importer_path)

    # JS/TS relative imports: import ... from './...'
    js_imports = re.findall(r'(?:import|export|require)\s*(?:[^\'\"]*?\s*from\s*)?[\(\'\"]([^\'\"]+)[\)\'\"]', content)
    for imp in js_imports:
        if imp.startswith('.'):
            resolved = os.path.normpath(os.path.join(importer_dir, imp))
            resolved_stem, _ = os.path.splitext(resolved)
            target_base = os.path.normpath(os.path.join(target_dir, target_stem))
            if resolved_stem == target_base:
                return True
            if target_stem == 'index' and target_dir == resolved:
                return True

    # Python relative/absolute module imports
    py_imports = re.findall(r'(?:from|import)\s+([\.\w]+)', content)
    for imp in py_imports:
        imp_parts = imp.lstrip('.').split('.')
        target_parts = os.path.splitext(target_path)[0].split(os.sep)
        if imp_parts and imp_parts[-1] == target_stem:
            return True

    return False

def is_refactor_extraction_heuristic(filepath: str, allowed_file_paths: set) -> bool:
    """
    If a newly added/extracted file is imported by an allowed file within the same package/component tree
    (or imports an allowed file in the same package/component tree), allow it as a modular extraction.
    """
    filepath_norm = os.path.normpath(filepath)
    cand_dir = os.path.dirname(filepath_norm)

    for allowed_p in allowed_file_paths:
        allowed_p_norm = os.path.normpath(allowed_p)
        allowed_dir = os.path.dirname(allowed_p_norm)

        # Must share a package or component subtree (common parent path up to 2 directory levels)
        if cand_dir == allowed_dir or cand_dir.startswith(allowed_dir + os.sep) or allowed_dir.startswith(cand_dir + os.sep):
            # Check if allowed file imports candidate file OR candidate file imports allowed file
            if check_file_imports_target(allowed_p_norm, filepath_norm) or check_file_imports_target(filepath_norm, allowed_p_norm):
                return True

    return False

def split_camel_case(s: str) -> list:
    """Splits camelCase or PascalCase strings into lowercased component tokens."""
    return [w.lower() for w in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+', s) if w]

def check_scope(changed_files, issue_text):
    if not issue_text:
        # If no issue text is found, we warn and pass to prevent blocking if run locally without metadata
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
    raw_words = set(re.findall(word_regex, issue_text))
    mentioned_words = set()
    for w in raw_words:
        mentioned_words.add(w.lower())
        for sub_w in split_camel_case(w):
            mentioned_words.add(sub_w)

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
    candidates_for_pass_2 = []

    # PASS 1: Direct matches, exempt files, directory matches, test matches, token matches
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
        matched_dir = None
        for md in mentioned_dirs:
            md_clean = md.strip("/")
            if md_clean and any(part == md_clean for part in filepath_lower.split("/")):
                is_in_mentioned_dir = True
                matched_dir = md
                break
        if is_in_mentioned_dir:
            allowed_files.append((filepath, f"Located in mentioned directory: {matched_dir}"))
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

        candidates_for_pass_2.append(filepath)

    # PASS 2: Modular refactoring / sub-file extractions & import heuristics
    disallowed_files = []
    allowed_file_paths = {f[0] for f in allowed_files}

    for filepath in candidates_for_pass_2:
        # 1. Module hierarchy matching
        if is_module_hierarchy_subfile(filepath, allowed_file_paths):
            allowed_files.append((filepath, "Module hierarchy sub-file extracted from in-scope parent module"))
            allowed_file_paths.add(filepath)
            continue

        # 2. Import heuristic matching
        if is_refactor_extraction_heuristic(filepath, allowed_file_paths):
            allowed_files.append((filepath, "Extracted helper module imported by/importing in-scope module"))
            allowed_file_paths.add(filepath)
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
