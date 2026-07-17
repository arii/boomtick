#!/usr/bin/env python3
"""
Example of using ContextBuilder in an end-to-end agentic workflow task.
This script demonstrates how a single agent session sequentially rotates through
multiple roles (Reviewer, Auditor, Triage Engineer) using the SAME compiled context
to optimize overhead and prevent massive AI cost replication.
"""

import sys
import os

# Ensure the cli/ directory is on the PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))

from dev_tools.services.context_builder import ContextBuilder
from dev_tools.services.ai_service import AIClient


def run_sequential_multi_role_task(pr_number: int, issue_number: int = None):
    print(f"🚀 [Agent] Initializing ContextBuilder for PR #{pr_number}...")

    # 1. Initialize ContextBuilder
    builder = ContextBuilder()

    # 2. Ingest PR details and diff
    print(f"📥 [Agent] Ingesting PR #{pr_number}...")
    builder.ingest_pr(pr_number)

    # 3. Ingest linked issue if provided
    if issue_number:
        print(f"📥 [Agent] Ingesting Linked Issue #{issue_number}...")
        builder.ingest_linked_issue(issue_number)

    # 4. Ingest repository file tree
    print("📥 [Agent] Ingesting Repository file tree layout...")
    builder.ingest_file_tree(max_depth=2)

    # 5. Build a unified "Multi-Role" prompt context
    print("📝 [Agent] Generating standard generic prompt context...")
    markdown_context = builder.build_markdown_context("generic")

    # Construct the sequential multi-role evaluation instructions
    multi_role_prompt = (
        f"{markdown_context}\n\n"
        "### SEQUENTIAL MULTI-ROLE EVALUATION TASK\n"
        "To prevent massive AI cost duplication and avoid launching separate agent sessions, "
        "you are tasked with evaluating this compiled context by rotating sequentially through three distinct roles.\n\n"
        "Please provide your consolidated analysis divided into the following three sequential sections:\n\n"
        "#### ROLE 1: Code Reviewer (Focus: Modifications, Correctness, design tokens)\n"
        "- Analyze the PR diff for correctness, potential bugs, or performance issues.\n"
        "- Enforce design token compliance (flag any raw Tailwind layout flex/grid or inline styles in TSX files).\n\n"
        "#### ROLE 2: Compliance Auditor (Focus: File tree necessity, stray files, repository conventions)\n"
        "- Inspect the ingested file tree structure and list of changed files.\n"
        "- Assess file necessity. Flag any suspicious temporary artifacts (e.g. *.tmp, standalone root scripts).\n\n"
        "#### ROLE 3: Triage Engineer (Focus: PR description alignment, CI failure check)\n"
        "- Evaluate if the PR goals align with the linked issue description and context.\n"
        "- Provide clear remediation/stabilization steps for any identified regressions.\n"
    )

    # Print a preview of the compiled prompt
    print("\n" + "=" * 50)
    print("📊 COMPILED CONTEXT PREVIEW (Truncated for readability):")
    print("=" * 50)
    lines = multi_role_prompt.splitlines()
    for line in lines[:35]:
        print(line)
    if len(lines) > 35:
        print(f"... [Truncated {len(lines) - 35} lines] ...")
    print("=" * 50 + "\n")

    # 6. Execute task with AI
    print("🤖 [Agent] Calling AI Client to perform consolidated Multi-Role Evaluation...")
    ai = AIClient()

    try:
        response = ai.generate(multi_role_prompt)
        print("\n" + "=" * 50)
        print("🤖 CONSOLIDATED MULTI-ROLE AI EVALUATION RESULT:")
        print("=" * 50)
        print(response)
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"❌ AI call failed: {e}", file=sys.stderr)
        print("\n💡 [ContextBuilder Benefit] Even if the AI service is offline, the compiled prompt context above "
              "can be logged, queued, or fed directly into manual auditing tools, preventing lost state!", file=sys.stderr)


if __name__ == "__main__":
    # Default to PR #175 if not specified
    target_pr = 175
    if len(sys.argv) > 1:
        try:
            target_pr = int(sys.argv[1])
        except ValueError:
            print("Usage: python3 scripts/run-context-agent.py [pr_number]", file=sys.stderr)
            sys.exit(1)

    run_sequential_multi_role_task(pr_number=target_pr)
