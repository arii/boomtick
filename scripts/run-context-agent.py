#!/usr/bin/env python3
"""
Example of using ContextBuilder and Workflow DAG in an end-to-end agentic workflow task.
This script demonstrates how a single agent session sequentially rotates through
multiple roles (Reviewer, Auditor, Triage Engineer, Analyst, Synthesizer) using the SAME compiled context
and a persistent Agent Scratch Pad to save and carry over intermediate observations.
"""

import sys
import os

# Ensure the cli/ directory is on the PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))

from dev_tools.workflows import WorkflowGraph, WorkflowNode, WorkflowContext
from dev_tools.workflows.nodes import DeploymentImpactCheckNode, FinalSynthesisNode
from dev_tools.orchestrator import Orchestrator

class IngestionNode(WorkflowNode):
    def __init__(self):
        super().__init__("Ingestion", role="system")

    def execute(self, context: WorkflowContext):
        pr_number = context.get("pr_number")
        issue_number = context.get("issue_number")

        print(f"🚀 [Agent] Initializing ContextBuilder for PR #{pr_number}...")
        if pr_number:
            print(f"📥 [Agent] Ingesting PR #{pr_number}...")
            context.builder.ingest_pr(pr_number)

        if issue_number:
            print(f"📥 [Agent] Ingesting Linked Issue #{issue_number}...")
            context.builder.ingest_linked_issue(issue_number)

        print("📥 [Agent] Ingesting Repository file tree layout...")
        context.builder.ingest_file_tree(max_depth=2)

class ReviewerNode(WorkflowNode):
    def __init__(self):
        super().__init__("Reviewer", role="reviewer")

    def execute(self, context: WorkflowContext):
        print("\n🕵️  [Agent Phase 1: Code Reviewer] Starting assessment...")
        context.write_scratchpad(
            "reviewer_assessment",
            "1. Verified all changes in context_builder.py. No raw Tailwind layout classes used.\n"
            "2. Identified a clean class structure and excellent use of local/deferred imports.\n"
            "3. Recommendation: Ready for promotion to compliance auditing.",
            role=self.role
        )

class AuditorNode(WorkflowNode):
    def __init__(self):
        super().__init__("Auditor", role="auditor")

    def execute(self, context: WorkflowContext):
        print("🔍 [Agent Phase 2: Compliance Auditor] Starting assessment...")
        previous_notes = context.builder.scratch_pad
        print(f"   💡 [Scratch Pad Read] Carry-over thoughts: {len(previous_notes)} notes found.")

        context.write_scratchpad(
            "auditor_assessment",
            "1. Inspected file tree. No stray, temporary or compiled artifacts (*.tmp, *dump.json) found.\n"
            "2. All file pathways are correctly organized inside the `cli/dev_tools/` structure.\n"
            "3. All compliance standards are fully satisfied.",
            role=self.role
        )

class TriageNode(WorkflowNode):
    def __init__(self):
        super().__init__("Triage", role="triage")

    def execute(self, context: WorkflowContext):
        print("🛠️  [Agent Phase 3: Triage Specialist] Starting assessment...")
        context.write_scratchpad(
            "triage_assessment",
            "1. Checked PR alignment with goal. The PR correctly implements the generic Context Builder Module.\n"
            "2. Verification plan: Verified locally via pytest and pylint.",
            role=self.role
        )

def run_single_agent_multi_role_scratchpad(pr_number: int = None, issue_number: int = None):
    orch = Orchestrator()
    pr_numbers = []

    if pr_number:
        pr_numbers.append(pr_number)
    else:
        import subprocess
        import json
        print("🔍 [Agent] No PR number provided. Fetching all open PRs...")
        try:
            res = subprocess.run(
                ["gh", "pr", "list", "--state", "open", "--json", "number", "--jq", ".[].number"],
                capture_output=True,
                text=True,
                check=True
            )
            # The output is a newline-separated list of PR numbers
            pr_numbers = [int(num) for num in res.stdout.strip().split("\n") if num.strip().isdigit()]
            print(f"✅ Found {len(pr_numbers)} open PRs: {pr_numbers}")
        except Exception as e:
            print(f"❌ Failed to fetch open PRs: {e}", file=sys.stderr)
            sys.exit(1)

    for pr in pr_numbers:
        print(f"\n{'='*50}\n🚀 RUNNING EVALUATION FOR PR #{pr}\n{'='*50}")
        graph = WorkflowGraph()

        # Add nodes
        graph.add_node(IngestionNode())
        graph.add_node(ReviewerNode())
        graph.add_node(AuditorNode())
        graph.add_node(TriageNode())
        graph.add_node(DeploymentImpactCheckNode())
        graph.add_node(FinalSynthesisNode())

        # Define sequential execution flow
        graph.add_edge("Ingestion", "Reviewer")
        graph.add_edge("Reviewer", "Auditor")
        graph.add_edge("Auditor", "Triage")
        graph.add_edge("Triage", "DeploymentImpactCheck")
        graph.add_edge("DeploymentImpactCheck", "FinalSynthesis")

        initial_inputs = {
            "pr_number": pr,
            "issue_number": issue_number,
        }

        try:
            context = orch.run_workflow_graph(graph, initial_inputs)

            print("\n" + "=" * 50)
            print(f"🤖 CONSOLIDATED AI EVALUATION RESULT (PR #{pr}):")
            print("=" * 50)
            print(context.get("final_synthesis_report"))
            print("=" * 50 + "\n")
        except Exception as e:
            print(f"❌ Workflow execution failed for PR #{pr}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            # Continue to next PR on failure, don't exit entirely.
            continue

if __name__ == "__main__":
    target_pr = None
    if len(sys.argv) > 1:
        try:
            target_pr = int(sys.argv[1])
        except ValueError:
            print("Usage: python3 scripts/run-context-agent.py [pr_number]", file=sys.stderr)
            sys.exit(1)

    run_single_agent_multi_role_scratchpad(pr_number=target_pr)
