#!/usr/bin/env python3
"""
Example of using ContextBuilder in an end-to-end agentic workflow task.
This script compiles context for a PR (and any linked issues) and runs an AI evaluation.
"""

import sys
import os

# Ensure the cli/ directory is on the PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))

from dev_tools.services.context_builder import ContextBuilder
from dev_tools.services.ai_service import AIClient


def run_agentic_task(pr_number: int, issue_number: int = None, step: str = "review"):
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

    # 5. Build clean prompt context formatted in Markdown
    print(f"📝 [Agent] Generating step-specific prompt context for step '{step}'...")
    markdown_context = builder.build_markdown_context(step)

    # Print a preview of the compiled prompt context
    print("\n" + "=" * 50)
    print("📊 COMPILED CONTEXT PREVIEW (Truncated for readability):")
    print("=" * 50)
    lines = markdown_context.splitlines()
    for line in lines[:30]:
        print(line)
    if len(lines) > 30:
        print(f"... [Truncated {len(lines) - 30} lines] ...")
    print("=" * 50 + "\n")

    # 6. Execute task with AI using the compiled prompt context
    print("🤖 [Agent] Calling AI Client to perform evaluation...")
    ai = AIClient()

    prompt = (
        f"{markdown_context}\n\n"
        "### TASK\n"
        "Analyze the compiled context above and provide a high-level summary and "
        "relevance assessment of the PR changes against the linked issue (if any) "
        "and overall repository structure. Highlight any potential compliance issues "
        "with our design tokens (e.g. raw Tailwind utility classes)."
    )

    try:
        response = ai.generate(prompt)
        print("\n" + "=" * 50)
        print("🤖 AI EVALUATION RESULT:")
        print("=" * 50)
        print(response)
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"❌ AI call failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    # Default to PR #175 if not specified
    target_pr = 175
    if len(sys.argv) > 1:
        try:
            target_pr = int(sys.argv[1])
        except ValueError:
            print("Usage: python3 scripts/run-context-agent.py [pr_number]", file=sys.stderr)
            sys.exit(1)

    run_agentic_task(pr_number=target_pr, step="review")
