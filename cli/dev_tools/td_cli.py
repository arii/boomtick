# pylint: disable=import-outside-toplevel,missing-docstring
#!/usr/bin/env python3
"""
td_cli.py - Project Developer CLI Shim

This script is a thin wrapper around the unified dev_tools CLI.
It maintains backward compatibility for existing scripts and CI workflows.
"""

import sys


def main():
    """Entry point for the td-cli shim."""
    try:
        from dev_tools.cli import main as cli_main

        cli_main()
    except ImportError as e:
        # Handle missing dependencies gracefully (e.g. click, pydantic)
        print(f"❌ Error: {e}", file=sys.stderr)
        print("   The environment might not be fully bootstrapped.", file=sys.stderr)
        print("   Run `pip install -e boomtick-pkg/cli/` to install dependencies.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
