"""Classify prose-only changes for the CI job gate."""

import os
import re
import subprocess
from pathlib import Path


def docs_only(paths: list[bytes]) -> bool:
    """Skip heavy checks only for Markdown files under docs/."""
    return bool(paths) and all(
        path.startswith(b"docs/") and path.endswith(b".md") for path in paths
    )


def changed_paths(base: str, head: str) -> list[bytes]:
    """Read both sides of renames and preserve unusual filename bytes."""
    if not all(re.fullmatch(r"[0-9a-fA-F]{40}", sha) for sha in (base, head)):
        raise ValueError("Expected full commit SHAs for the PR diff")
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--name-only",
            "-z",
            f"{base}...{head}",
            "--",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [path for path in result.stdout.split(b"\0") if path]


def main() -> None:
    is_docs_only = False
    if os.environ["EVENT_NAME"] == "pull_request":
        is_docs_only = docs_only(
            changed_paths(os.environ["BASE_SHA"], os.environ["HEAD_SHA"])
        )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"docs_only={str(is_docs_only).lower()}\n")


if __name__ == "__main__":
    main()
