#!/usr/bin/env python3
"""
td_cli.py - Project Developer CLI Shim

This script is a thin wrapper around the unified dev_tools CLI.
It maintains backward compatibility for existing scripts and CI workflows.
"""

from dev_tools.cli import main as cli_main

def main():
    """Entry point for the td-cli shim."""
    cli_main()

if __name__ == "__main__":
    main()
