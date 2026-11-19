#!/usr/bin/env python3
"""
Lightweight Scope Verification Tool
Parses the initial issue description and compares it against the git diff --name-only output.
Strictly prevents modifications to files outside the direct scope of the reported issue.

The scope-matching rules are implemented once in
cli/dev_tools/services/scope_gate.py and re-exported below, so CI
and td enforce identical verdicts.
"""

import os
import sys
import argparse
import re
import subprocess
import json

# Single source of truth for the scope-matching rules lives in
# cli/dev_tools/services/scope_gate.py (importable by the td package
# and its test suite). This script re-exports that implementation so
# CI and td enforce identical verdicts.
from dev_tools.services import scope_gate as _scope_gate

EXEMPT_FILES = _scope_gate.EXEMPT_FILES
EXEMPT_FILES_LOWER = _scope_gate.EXEMPT_FILES_LOWER
STOP_WORDS = _scope_gate.STOP_WORDS
KNOWN_FILE_EXTENSIONS = _scope_gate.KNOWN_FILE_EXTENSIONS
normalize_name = _scope_gate.normalize_name
is_test_file_for_in_scope = _scope_gate.is_test_file_for_in_scope
is_module_hierarchy_subfile = _scope_gate.is_module_hierarchy_subfile
check_file_imports_target = _scope_gate.check_file_imports_target
is_refactor_extraction_heuristic = _scope_gate.is_refactor_extraction_heuristic
split_camel_case = _scope_gate.split_camel_case
_is_phantom_file_match = _scope_gate._is_phantom_file_match
_is_phantom_dir_match = _scope_gate._is_phantom_dir_match
extract_mentions = _scope_gate.extract_mentions
check_scope = _scope_gate.check_scope


def get_changed_files(base_branch=None):
    files = set()

    if not base_branch:
        base_ref = os.environ.get("GITHUB_BASE_REF")
        if base_ref:
            base_branch = f"origin/{base_ref}"
        else:
            base_branch = "origin/main"

    # Try diffing directly against base branch (compares base branch commit to the working directory)
    res = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base_branch],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
    else:
        # Fallback to main
        res = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "main"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
        else:
            # Fallback to HEAD~1 to catch local changes if base branches are not available
            res = subprocess.run(
                ["git", "diff", "--name-only", "--no-renames", "HEAD~1"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                files.update(f.strip() for f in res.stdout.splitlines() if f.strip())
            else:
                res = subprocess.run(
                    ["git", "diff", "--name-only", "--no-renames"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    files.update(
                        f.strip() for f in res.stdout.splitlines() if f.strip()
                    )

    # Also include untracked files to be extremely thorough and developer-friendly!
    res = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            if line.startswith("?? "):
                files.add(line[3:].strip())

    return sorted(list(files))


def fetch_linked_issue_bodies(
    text: str, fetched_nums=None, *, resolved_issues=None, issue_numbers=()
) -> str:
    """Find issue numbers like #123, Fixes #123 in text and fetch their descriptions."""
    if fetched_nums is None:
        fetched_nums = set()

    extra_texts = []
    # Find patterns like #123 or fixes #123
    issue_refs = set(re.findall(r"#(\d+)", text)) | {str(n) for n in issue_numbers}
    for num in issue_refs:
        if num in fetched_nums:
            continue
        fetched_nums.add(num)
        try:
            res = subprocess.run(
                ["gh", "issue", "view", str(num), "--json", "title,body"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                title = data.get("title", "")
                body = data.get("body", "")
                extra_texts.append(f"\n--- Linked Issue #{num} ---\n{title}\n\n{body}")
                if resolved_issues is not None:
                    resolved_issues.add(int(num))
        except Exception as e:
            print(f"verify-scope: linked issue #{num} unreadable: {e}", file=sys.stderr)

    if extra_texts:
        return text + "\n" + "\n".join(extra_texts)
    return text


def pr_linked_issue_numbers(pr_number, repository):
    numbers = set()
    repo = repository.get("full_name")
    if not pr_number or not repo:
        return numbers
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "closingIssuesReferences",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            for linked in json.loads(result.stdout).get("closingIssuesReferences", []):
                number = linked.get("number")
                repo_url = repository.get("html_url", f"https://github.com/{repo}")
                if (
                    isinstance(number, int)
                    and not isinstance(number, bool)
                    and number > 0
                    and linked.get("url") == f"{repo_url}/issues/{number}"
                ):
                    numbers.add(number)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"verify-scope: PR issue links unreadable: {exc}", file=sys.stderr)
    return numbers


def closing_issue_numbers(text):
    return {
        int(number)
        for number in re.findall(
            r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)(?:\s*:\s*|\s+)#([1-9][0-9]*)\b",
            text,
            re.IGNORECASE,
        )
    }


def event_scope_context(event):
    pr = event.get("pull_request", {})
    issue = event.get("issue", {})
    body = pr.get("body") or issue.get("body") or ""
    title = pr.get("title") or issue.get("title") or ""
    text = f"{title}\n\n{body}" if title or body else ""
    numbers = closing_issue_numbers(text) if pr else set()
    numbers.update(
        pr_linked_issue_numbers(pr.get("number"), event.get("repository", {}))
    )
    if pr and not numbers:
        head = os.environ.get("GITHUB_HEAD_REF") or pr.get("head", {}).get("ref", "")
        match = re.fullmatch(r"agent/issue-([1-9][0-9]*)", head)
        if match:
            numbers.add(int(match[1]))
    return text, numbers, issue.get("number") if not pr and text else None


def fetch_issue_description(
    issue_file=None, issue_body=None, issue_number=None, *, resolved_issues=None
):
    raw_text = None
    linked_numbers = set()
    candidates = set()
    fetched_issues = set()
    resolved_issues = resolved_issues if resolved_issues is not None else set()

    if issue_body:
        raw_text = issue_body

    if not raw_text and issue_file and os.path.exists(issue_file):
        with open(issue_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

    if raw_text:
        candidates.update(closing_issue_numbers(raw_text))

    # Check GITHUB_EVENT_PATH
    if not raw_text:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path, "r", encoding="utf-8") as f:
                    event = json.load(f)
                raw_text, linked_numbers, event_issue = event_scope_context(event)
                candidates.update(linked_numbers)
                if event_issue:
                    candidates.add(event_issue)
                    fetched_issues.add(event_issue)
            except Exception as e:
                print(f"verify-scope: event payload unreadable: {e}", file=sys.stderr)

    # Try using gh CLI if issue_number is provided
    if not raw_text and not linked_numbers and issue_number:
        try:
            res = subprocess.run(
                ["gh", "issue", "view", str(issue_number), "--json", "title,body"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                raw_text = f"{data.get('title', '')}\n\n{data.get('body', '')}"
                candidates.add(issue_number)
                fetched_issues.add(issue_number)
        except Exception as e:
            print(
                f"verify-scope: issue #{issue_number} unreadable: {e}", file=sys.stderr
            )

    # Try looking for task_description.md or similar files in workspace
    if not raw_text and not linked_numbers:
        for fallback_path in [
            "task_description.md",
            "issue_description.md",
            ".agents/task_description.md",
        ]:
            if os.path.exists(fallback_path):
                with open(fallback_path, "r", encoding="utf-8") as f:
                    raw_text = f.read()
                    candidates.update(closing_issue_numbers(raw_text))
                    break

    if raw_text or linked_numbers:
        raw_text = fetch_linked_issue_bodies(
            raw_text or "",
            resolved_issues=fetched_issues,
            issue_numbers=linked_numbers,
        )

    if len(candidates) == 1:
        resolved_issues.update(candidates & fetched_issues)

    return raw_text


def check_override():
    if os.environ.get("SCOPE_OVERRIDE") == "true":
        return True

    # Check environment variables for release-please branch or PR head ref
    head_ref = os.environ.get("GITHUB_HEAD_REF", "").lower()
    github_ref = os.environ.get("GITHUB_REF", "").lower()
    release_branch_keywords = ["release-please", "autorelease", "release/", "release-"]
    if any(k in head_ref or k in github_ref for k in release_branch_keywords):
        return True

    # Check current git branch name
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            branch_name = res.stdout.strip().lower()
            if any(k in branch_name for k in release_branch_keywords):
                return True
    except Exception as e:
        print(f"verify-scope: branch probe failed: {e}", file=sys.stderr)

    # Check GITHUB_EVENT_PATH for release-please branch, title, or bot user
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event = json.load(f)
            pr = event.get("pull_request", {})
            pr_head_ref = pr.get("head", {}).get("ref", "").lower()
            pr_title = pr.get("title", "").strip().lower()
            user_login = pr.get("user", {}).get("login", "").lower()

            if any(k in pr_head_ref for k in release_branch_keywords):
                return True
            if any(
                k in user_login
                for k in ["release-please", "boomtick", "github-actions"]
            ) or user_login.endswith("[bot]"):
                return True
            if (
                pr_title.startswith("chore: release")
                or pr_title.startswith("release:")
                or pr_title.startswith("chore(release)")
                or (pr_title.startswith("chore(") and "release" in pr_title)
                or "chore: release main" in pr_title
                or "chore(deps" in pr_title
            ):
                return True
        except Exception as e:
            print(f"verify-scope: event file unreadable: {e}", file=sys.stderr)

    # The PR's own commits, one range, no retry: a failed probe denies bypass.
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    rev_args = [f"origin/{base_ref}..HEAD"] if base_ref else ["-n", "1", "HEAD"]
    try:
        res = subprocess.run(
            ["git", "log", *rev_args, "--pretty=%B"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            msg = res.stdout.lower()
            if any(
                tag in msg
                for tag in [
                    "[skip-scope-check]",
                    "[scope-override]",
                    "skip-scope",
                    "release-please",
                ]
            ):
                return True
            if any(
                tag in msg
                for tag in [
                    "chore: release",
                    "chore(main): release",
                    "chore: release main",
                ]
            ):
                return True
    except Exception as e:
        print(f"verify-scope: commit log probe failed: {e}", file=sys.stderr)

    return False


def submitted_issue_number(resolved_issues):
    return next(iter(resolved_issues)) if len(resolved_issues) == 1 else None


def main():
    parser = argparse.ArgumentParser(
        description="Verify that modified files are within the direct scope of the reported issue."
    )
    parser.add_argument(
        "--issue-file", help="Path to a file containing the issue description/body"
    )
    parser.add_argument(
        "--issue-body", help="Direct text of the issue description/body"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        help="GitHub issue/PR number to fetch description for",
    )
    parser.add_argument(
        "--base-branch", help="Git base branch to compare against (e.g. origin/main)"
    )
    parser.add_argument(
        "--strict-scope",
        action="store_true",
        help="Fail with exit code 1 if out-of-scope files are found",
    )

    args = parser.parse_args()

    # Check bypass / override
    if check_override():
        print("⚠️ Scope verification bypassed via explicit override.")
        sys.exit(0)

    resolved_issues = set()
    issue_text = fetch_issue_description(
        args.issue_file,
        args.issue_body,
        args.issue_number,
        resolved_issues=resolved_issues,
    )
    changed_files = get_changed_files(args.base_branch)

    if not issue_text:
        if args.strict_scope:
            print(
                "❌ Error: Initial issue description could not be fetched/auto-detected. Failing closed under --strict-scope."
            )
            sys.exit(1)
        print(
            "⚠️ Warning: Initial issue description could not be fetched/auto-detected. Skipping strict scope check."
        )
        sys.exit(0)

    success, allowed, disallowed = check_scope(
        changed_files, issue_text, issue=submitted_issue_number(resolved_issues)
    )

    print("\n--- Scope Verification Report ---")
    print(f"Total files checked: {len(changed_files)}")
    print(f"Allowed files: {len(allowed)}")
    for f, reason in allowed:
        print(f"  ✅ {f} ({reason})")

    if disallowed:
        print(f"\n❌ Out-of-Scope files detected: {len(disallowed)}")
        for f in disallowed:
            print(f"  🚨 {f}")

        print(
            "\nError: Modifications to files outside the direct scope of the reported issue violate the 'minimize scope creep' directive."
        )
        print("To resolve this, please either:")
        print("  1. Revert modifications to the out-of-scope files.")
        print(
            "  2. If the modifications are necessary, mention them in the PR body or issue description so they are parsed."
        )
        print(
            "  3. Bypass this check by setting the SCOPE_OVERRIDE=true environment variable or adding '[skip-scope-check]' to your last commit message."
        )

        if args.strict_scope:
            sys.exit(1)
        else:
            print(
                "\n⚠️ Running in warning-only mode. Strict mode (--strict-scope) was not enabled."
            )

    else:
        print("\n🎉 Success: All modified files are within the permitted issue scope!")

    sys.exit(0)


if __name__ == "__main__":
    main()
