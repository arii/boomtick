# pylint: disable=missing-docstring,too-few-public-methods,import-outside-toplevel
from typing import Any, Dict, Optional

from dev_tools.workflows.context import WorkflowContext
from dev_tools.workflows.node import WorkflowNode


class EnvironmentCheckNode(WorkflowNode):
    """
    WorkflowNode that verifies the runtime environment (Node, pnpm versions).
    """

    def __init__(
        self,
        name: str = "EnvironmentCheck",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> Dict[str, str]:
        from dev_tools.orchestrator import Orchestrator

        orchestrator = Orchestrator()
        res = orchestrator.runtime_check()
        context.set("runtime_info", res)
        return res


class IssueValidationNode(WorkflowNode):
    """
    WorkflowNode that validates specified open issues or all open issues.
    """

    def __init__(
        self,
        name: str = "IssueValidation",
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(name, description, retry_policy, timeout)

    def execute(self, context: WorkflowContext) -> Dict[str, Any]:
        from dev_tools.orchestrator import Orchestrator

        issue_number = context.get("issue_number")
        all_open = context.get("all_open", False)
        post_comments = context.get("post_comments", False)
        dry_run = context.get("dry_run", True)

        orchestrator = Orchestrator()
        res = orchestrator.validate_issue(
            issueNumber=issue_number,
            all_open=all_open,
            post_comments=post_comments,
            dry_run=dry_run,
        )
        context.set("issue_validation_results", res)
        return res
