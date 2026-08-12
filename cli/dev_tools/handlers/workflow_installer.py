"""Workflow installer template engine."""

from pathlib import Path

WORKFLOW_TEMPLATES = {
    "impact-analysis.yml": """name: Impact Analysis

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  impact-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version-file: '.node-version'
      - name: Install BoomTick CLI
        run: pip install boomtick-cli
      - name: Run Impact Review
        run: td-cli ai review ${{ github.event.pull_request.number }}
""",
    "agent-audit.yml": """name: Agent Audit

on:
  issue_comment:
    types: [created]

jobs:
  agent-audit:
    runs-on: ubuntu-latest
    if: contains(github.event.comment.body, '/audit')
    steps:
      - uses: actions/checkout@v4
      - name: Install BoomTick CLI
        run: pip install boomtick-cli
      - name: Execute Audit Gate
        run: td-cli gh audit-gate
"""
}

def install_workflows(target_dir: str, dry_run: bool = False, force: bool = False) -> bool:
    """Installs standardized workflow templates into the specified target directory."""
    github_dir = Path(target_dir) / ".github" / "workflows"
    if not dry_run:
        github_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in WORKFLOW_TEMPLATES.items():
        file_path = github_dir / filename
        if not dry_run and file_path.exists() and not force:
            print(f"[SKIP] {file_path} already exists. Use --force to overwrite.")
            continue
        print(f"[{'DRY-RUN' if dry_run else 'INSTALL'}] Writing {file_path}")
        if not dry_run:
            file_path.write_text(content.strip() + "\n", encoding="utf-8")
    return True
