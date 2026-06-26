#!/usr/bin/env python3
"""
ai_reviewer.py - Standalone AI Code Reviewer CLI
"""

import os
import sys
import argparse
from utils import call_ai
from dev_tools_sdk.config import load_project_config

PROJECT_CONFIG = load_project_config()
MODEL = PROJECT_CONFIG.ai_review_model
MAX_FILE_SIZE_KB = 50

def is_binary(file_path):
    """Simple check to detect binary files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.read(1024)
            return False
    except (UnicodeDecodeError, PermissionError):
        return True

def review_file(file_path, silent=False):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)

    # 1. File Size Check
    file_size_kb = os.path.getsize(file_path) / 1024
    if file_size_kb > MAX_FILE_SIZE_KB:
        print(f"Error: File '{file_path}' is too large ({file_size_kb:.1f}KB). Maximum size is {MAX_FILE_SIZE_KB}KB.", file=sys.stderr)
        sys.exit(1)

    # 2. Binary Check
    if is_binary(file_path):
        print(f"Error: File '{file_path}' appears to be binary or cannot be read as UTF-8.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(file_path, "r", encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    prompt = f"Please review the following code:\n\n```\n{content}\n```"

    if not silent:
        print(f"--- Reviewing {file_path} using AI service ---")

    review = call_ai(prompt, model=MODEL)
    if review:
        print(review)
    else:
        print(f"Error: Failed to get review for {file_path}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Standalone AI Code Reviewer CLI")
    parser.add_argument("file", help="Path to the file to review")
    parser.add_argument("--silent", action="store_true", help="Suppress non-review output")
    args = parser.parse_args()

    review_file(args.file, silent=args.silent)

if __name__ == "__main__":
    main()
