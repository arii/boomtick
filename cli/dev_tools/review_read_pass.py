#!/usr/bin/env python3
"""
review_read_pass.py – Diff parser and file-chunk splitter for the piecemeal
AI review pipeline.

Key exports
-----------
parse_diff_into_file_chunks(diff_text) -> list[dict]
    Groups a unified diff into one chunk per file (or multiple chunks for
    large files) and applies skip rules so non-code assets are never sent
    to the AI reviewer.

"""

import json
import re
import sys
from typing import Optional

# ── Skip rules ────────────────────────────────────────────────────────────────
# Files matching any of these patterns will be classified as skip=True.
_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".webp", ".woff", ".woff2", ".ttf", ".eot", ".otf",  # images / fonts
    ".mp4", ".mov", ".avi", ".webm",                       # video
    ".pdf", ".zip", ".tar", ".gz", ".br",                  # binary archives
    ".map",                                                 # source maps
}

_SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "Gemfile.lock", "poetry.lock",        # lock files
}

_SKIP_PATTERNS = [
    re.compile(r"\.min\.(js|css|mjs)$"),          # minified
    re.compile(r"\.snap$"),                         # Jest snapshots
    re.compile(r"^(dist|build|\.next|out|\.nuxt)/"),  # build artifacts
    re.compile(r"^__generated__/"),                 # GraphQL / codegen
]

# Maximum diff characters sent per AI call for a single hunk-group
MAX_CHUNK_CHARS = 8_000
# Maximum added lines before we split a file's diff into multiple chunks
HUNK_GROUP_SIZE = 50


def _should_skip(filepath: str) -> Optional[str]:
    """Return a human-readable skip reason, or None if the file should be reviewed."""
    import os
    basename = os.path.basename(filepath)
    ext = os.path.splitext(basename)[1].lower()

    if ext in _SKIP_EXTENSIONS:
        return f"binary/image ({ext})"
    if basename in _SKIP_FILENAMES:
        return "lock file"
    for pat in _SKIP_PATTERNS:
        if pat.search(filepath):
            return f"matches skip pattern ({pat.pattern})"
    return None


# ── Core diff parser ──────────────────────────────────────────────────────────

def _parse_raw_files(diff_text: str) -> list[dict]:
    """
    Split a unified diff into a list of per-file raw dicts:
      {file, hunks: [{header, lines, added_count}]}
    """
    files = []
    current_file: Optional[str] = None
    current_hunks: list = []
    current_hunk: Optional[dict] = None

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git"):
            if current_file is not None:
                if current_hunk:
                    current_hunks.append(current_hunk)
                files.append({"file": current_file, "hunks": current_hunks})
            current_file = None
            current_hunks = []
            current_hunk = None
        elif line.startswith("+++ b/"):
            current_file = line[6:].rstrip("\n")
        elif line.startswith("@@ "):
            if current_hunk:
                current_hunks.append(current_hunk)
            current_hunk = {"header": line, "lines": [], "added_count": 0}
        elif current_hunk is not None:
            current_hunk["lines"].append(line)
            if line.startswith("+") and not line.startswith("+++"):
                current_hunk["added_count"] += 1

    # flush last file
    if current_file is not None:
        if current_hunk:
            current_hunks.append(current_hunk)
        files.append({"file": current_file, "hunks": current_hunks})

    return files


def _hunk_to_text(hunk: dict) -> str:
    return hunk["header"] + "".join(hunk["lines"])


def parse_diff_into_file_chunks(diff_text: str) -> list[dict]:
    """
    Main entry point for the piecemeal review pipeline.

    Returns a list of chunk dicts:
    {
        "file": str,          # relative path
        "chunk_index": int,   # 0-based (most files have only one chunk)
        "total_chunks": int,
        "skip": bool,
        "reason": str | None, # populated when skip=True
        "diff_text": str,     # the raw diff text for this chunk
        "added_lines": int,
        "truncated": bool,    # True when diff_text was trimmed to MAX_CHUNK_CHARS
    }
    """
    raw_files = _parse_raw_files(diff_text)
    chunks = []

    for rf in raw_files:
        filepath = rf["file"]
        hunks = rf["hunks"]

        skip_reason = _should_skip(filepath)

        if skip_reason or not hunks:
            chunks.append({
                "file": filepath,
                "chunk_index": 0,
                "total_chunks": 1,
                "skip": True,
                "reason": skip_reason or "no hunks",
                "diff_text": "",
                "added_lines": 0,
                "truncated": False,
            })
            continue

        # Group hunks into batches of ≤ HUNK_GROUP_SIZE added lines each
        groups: list[list[dict]] = []
        current_group: list[dict] = []
        current_added = 0

        for hunk in hunks:
            if current_added + hunk["added_count"] > HUNK_GROUP_SIZE and current_group:
                groups.append(current_group)
                current_group = []
                current_added = 0
            current_group.append(hunk)
            current_added += hunk["added_count"]

        if current_group:
            groups.append(current_group)

        total_chunks = len(groups)

        for idx, group in enumerate(groups):
            text = f"--- a/{filepath}\n+++ b/{filepath}\n"
            text += "".join(_hunk_to_text(h) for h in group)
            added = sum(h["added_count"] for h in group)
            truncated = False

            if len(text) > MAX_CHUNK_CHARS:
                text = text[:MAX_CHUNK_CHARS] + f"\n... (diff truncated at {MAX_CHUNK_CHARS} chars)"
                truncated = True

            chunks.append({
                "file": filepath,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "skip": False,
                "reason": None,
                "diff_text": text,
                "added_lines": added,
                "truncated": truncated,
            })

    return chunks


if __name__ == "__main__":
    raw = sys.stdin.read()
    chunks = parse_diff_into_file_chunks(raw)
    reviewable = [c for c in chunks if not c["skip"]]
    skipped = [c for c in chunks if c["skip"]]
    print(json.dumps({
        "total_chunks": len(chunks),
        "reviewable": len(reviewable),
        "skipped": len(skipped),
        "chunks": chunks,
    }, indent=2))
