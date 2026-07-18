# pylint: disable=missing-docstring,too-few-public-methods,import-outside-toplevel
from typing import Any, Dict, Optional

from dev_tools.workflows.context import WorkflowContext
from dev_tools.workflows.node import WorkflowNode


class EnvironmentCheckNode(WorkflowNode):
    """
    WorkflowNode that verifies the runtime environment (Node, pnpm versions).
    Assumes the role 'verifier'.
    """

    def __init__(
        self,
        name: str = "EnvironmentCheck",
        role: str = "verifier",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, role, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> Dict[str, str]:
        from dev_tools.orchestrator import Orchestrator

        # Ingest file tree if not already ingested to improve context efficiency
        if not context.builder.file_tree:
            context.builder.ingest_file_tree(max_depth=1)

        orchestrator = Orchestrator()
        res = orchestrator.runtime_check()
        context.set("runtime_info", res)

        # Write to the shared single-agent scratchpad
        context.write_scratchpad("verified_node_version", res.get("node"))
        context.write_scratchpad("verified_pnpm_version", res.get("pnpm"))
        return res


class IssueValidationNode(WorkflowNode):
    """
    WorkflowNode that validates specified open issues or all open issues.
    Assumes the role 'validator'.
    """

    def __init__(
        self,
        name: str = "IssueValidation",
        role: str = "validator",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, role, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        from dev_tools.orchestrator import Orchestrator

        # Ingest file tree if not already ingested to improve context efficiency
        if not context.builder.file_tree:
            context.builder.ingest_file_tree(max_depth=1)

        # Only ingest issue if provided and not already present
        issue_number = context.get("issue_number")
        if issue_number and not context.builder.linked_issues:
            context.builder.ingest_linked_issue(issue_number)

        all_open = context.get("all_open", False)
        post_comments = context.get("post_comments", False)
        dry_run = context.get("dry_run", True)

        # Read from the shared single-agent scratchpad to adjust logic
        node_version = context.read_scratchpad("verified_node_version")
        context.write_scratchpad("validation_focus", f"Validating under Node {node_version}")

        orchestrator = Orchestrator()
        res = orchestrator.validate_issue(
            issue_number=issue_number,
            all_open=all_open,
            post_comments=post_comments,
            dry_run=dry_run,
        )
        context.set("issue_validation_results", res)
        return res

class DeploymentImpactCheckNode(WorkflowNode):
    """
    WorkflowNode that checks for affected files and writes a status note.
    Assumes the role 'analyst'.
    """

    def __init__(
        self,
        name: str = "DeploymentImpactCheck",
        role: str = "analyst",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, role, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        pr_number = context.get("pr_number")
        if pr_number and not context.builder.pr_details:
            context.builder.ingest_pr(pr_number)

        affected = []
        if context.builder.pr_diff:
            from dev_tools.services.dependency_graph import DependencyGraph
            from dev_tools.utils import log_warn
            try:
                # Get changed files from PR
                from dev_tools.orchestrator import Orchestrator
                orch = Orchestrator()
                changed_files = [f.get("filename") for f in orch.github.fetch_pr_files(pr_number) if f.get("filename")]
                if changed_files:
                    graph = DependencyGraph()
                    affected = list(graph.find_affected_files(changed_files))
                    if affected:
                        context.builder.add_extra_context("Affected Files (Impact Analysis)", sorted(affected))
            except Exception as e:
                log_warn(f"Could not calculate affected files: {e}")

        # Write risk assessment to scratchpad
        risk_level = "HIGH" if len(affected) > 5 else ("MEDIUM" if len(affected) > 0 else "LOW")
        note = f"Deployment risk assessment: {risk_level} risk. {len(affected)} files affected."
        context.write_scratchpad("deployment_risk", note, role=self.role)

        return {"affected_files": affected, "risk_level": risk_level}


class FinalSynthesisNode(WorkflowNode):
    """
    Mandatory terminal node that builds the final markdown context and generates the AI synthesis.
    Assumes the role 'synthesizer'.
    """

    def __init__(
        self,
        name: str = "FinalSynthesis",
        role: str = "synthesizer",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, role, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> str:
        from dev_tools.services.ai_service import AIClient

        # Build the unified markdown string. This is the ONLY input to the AI.
        markdown_context = context.builder.build_markdown_context("generic")

        # We don't call anything that spawns sub-agents or threads.
        ai_client = AIClient()
        try:
            response = ai_client.generate(markdown_context)
        except Exception as e:
            response = f"AI Mock Response (Service Unavailable): {e}"

        context.set("final_synthesis_report", response)
        context.write_scratchpad("synthesis_complete", "Final report generated successfully.", role=self.role)

        return response
