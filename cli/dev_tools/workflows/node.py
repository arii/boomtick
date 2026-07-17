# pylint: disable=missing-docstring,too-few-public-methods
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from dev_tools.workflows.context import WorkflowContext


class WorkflowNode(ABC):
    """
    Abstract base class representing a discrete unit of execution within a workflow DAG.
    """

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.name = name
        self.description = description or self.__doc__ or ""
        self.retry_policy = retry_policy or {"max_retries": 0, "backoff_factor": 1.0}
        self.timeout = timeout

    @abstractmethod
    def execute(self, context: WorkflowContext) -> Any:
        """
        Execute the business logic of this node.
        Should read from and write to the context as needed.
        """
        raise NotImplementedError("Subclasses must implement execute")
