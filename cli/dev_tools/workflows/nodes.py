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

        issue_number = context.get("issue_number")
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
