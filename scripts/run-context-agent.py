#!/usr/bin/env python3
"""
Example of using ContextBuilder in an end-to-end agentic workflow task.
This script demonstrates how a single agent session sequentially rotates through
multiple roles (Reviewer, Auditor, Triage Engineer) using the SAME compiled context
and a persistent Agent Scratch Pad to save and carry over intermediate observations.
"""

import sys
import os

# Ensure the cli/ directory is on the PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))

from dev_tools.services.context_builder import ContextBuilder
from dev_tools.services.ai_service import AIClient


def run_single_agent_multi_role_scratchpad(pr_number: int, issue_number: int = None):
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

    # --- STEP 1: REVIEWER ROLE ---
    print("\n🕵️  [Agent Phase 1: Code Reviewer] Starting assessment...")
    # Add a mock reviewer thought/finding to the scratch pad
    builder.add_scratch_note(
        role="reviewer",
        note=(
            "1. Verified all changes in context_builder.py. No raw Tailwind layout classes used.\n"
            "2. Identified a clean class structure and excellent use of local/deferred imports.\n"
            "3. Recommendation: Ready for promotion to compliance auditing."
        )
    )

    # --- STEP 2: AUDITOR ROLE ---
    print("🔍 [Agent Phase 2: Compliance Auditor] Starting assessment...")
    # Read previous findings from the scratch pad to simulate sequential reasoning
    previous_notes = builder.scratch_pad
    print(f"   💡 [Scratch Pad Read] Carry-over thoughts: {len(previous_notes)} notes found.")

    # Auditor builds on Reviewer's work and adds compliance insights
    builder.add_scratch_note(
        role="auditor",
        note=(
            "1. Inspected file tree. No stray, temporary or compiled artifacts (*.tmp, *dump.json) found.\n"
            "2. All file pathways are correctly organized inside the `cli/dev_tools/` structure.\n"
            "3. All compliance standards are fully satisfied."
        )
    )

    # --- STEP 3: TRIAGE SPECIALIST ROLE ---
    print("🛠️  [Agent Phase 3: Triage Specialist] Starting assessment...")
    builder.add_scratch_note(
        role="triage",
        note=(
            "1. Checked PR alignment with goal. The PR correctly implements the generic Context Builder Module.\n"
            "2. Verification plan: Verified locally via pytest and pylint."
        )
    )

    # 5. Build the unified prompt context containing the persistent scratch pad state
    print("\n📝 [Agent] Compiling ultimate multi-role context with persistent Scratch Pad...")
    final_prompt_context = builder.build_markdown_context("generic")

    # Construct instructions requesting a consolidated response
    final_evaluation_prompt = (
        f"{final_prompt_context}\n\n"
        "### SINGLE-AGENT SEQUENTIAL ASSESSMENT TASK\n"
        "To prevent massive AI cost duplication, you are acting as a single agent representing multiple personas sequentially.\n"
        "Read the intermediate observations you recorded in the 'Agent Scratch Pad' section above.\n\n"
        "Provide a final, consolidated summary and approval verdict on the PR based on your own sequential thoughts across all roles."
    )

    # Print a preview of the compiled prompt
    print("\n" + "=" * 50)
    print("📊 COMPILED CONTEXT PREVIEW WITH SCRATCH PAD:")
    print("=" * 50)
    lines = final_evaluation_prompt.splitlines()
    for line in lines[:55]:
        print(line)
    if len(lines) > 55:
        print(f"... [Truncated {len(lines) - 55} lines] ...")
    print("=" * 50 + "\n")

    # 6. Execute task with AI
    print("🤖 [Agent] Calling AI Client to perform consolidated evaluation...")
    ai = AIClient()

    try:
        response = ai.generate(final_evaluation_prompt)
        print("\n" + "=" * 50)
        print("🤖 CONSOLIDATED SINGLE-AGENT AI EVALUATION RESULT:")
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

    run_single_agent_multi_role_scratchpad(pr_number=target_pr)
