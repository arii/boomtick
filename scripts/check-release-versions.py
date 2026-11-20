"""Reject changed release versions that collide with any immutable git tag."""

import argparse
import json
import re
import subprocess
import sys

MANIFEST = ".release-please-manifest.json"
COMPONENTS = ("cli", "mcp")


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def stable_version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value
    ):
        raise ValueError(f"Expected stable major.minor.patch version, got {value!r}")
    return tuple(int(part) for part in value.split("."))


def validate(base, head, tags):
    """Return errors only for components whose manifest version changed."""
    errors = []
    for component in COMPONENTS:
        old, new = base[component], head[component]
        if old == new:
            continue
        version = stable_version(new)
        previous = stable_version(old)
        prefix = f"{component}-v"
        published = []
        for tag in tags:
            if tag.startswith(prefix):
                candidate = tag[len(prefix) :]
                if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", candidate):
                    published.append(stable_version(candidate))
        if prefix + new in tags:
            errors.append(
                f"{component}: {prefix}{new} already exists; never reuse tags"
            )
        if version <= max([previous, *published]):
            errors.append(
                f"{component}: {new} must exceed the base version and every existing "
                f"stable {prefix} tag, independent of publication date"
            )
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    if not all(re.fullmatch(r"[a-fA-F0-9]{40}", sha) for sha in (args.base, args.head)):
        raise ValueError("Expected full base and head commit SHAs")
    base = json.loads(git("show", f"{args.base}:{MANIFEST}"))
    head = json.loads(git("show", f"{args.head}:{MANIFEST}"))
    tags = git("tag", "--list").splitlines()
    errors = validate(base, head, tags)
    for error in errors:
        print(f"Release version safety: {error}", file=sys.stderr)
    if errors:
        print(
            "Prepare reviewed unused versions. Do not move/delete published tags.",
            file=sys.stderr,
        )
        return 1
    print("Release version safety passed (unchanged versions need no new release).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
