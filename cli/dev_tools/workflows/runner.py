# pylint: disable=missing-docstring,too-few-public-methods,too-many-locals
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dev_tools.workflows.context import WorkflowContext
from dev_tools.workflows.graph import WorkflowGraph


class WorkflowRunner:
    """
    Executes a WorkflowGraph in topological order.
    Manages retries with exponential backoff, timeouts, and execution logs.
    """

    def __init__(self, halt_on_failure: bool = True) -> None:
        self.halt_on_failure = halt_on_failure

    def _execute_with_timeout(self, node: Any, context: WorkflowContext) -> Any:
        timeout = node.timeout
        if timeout is None or timeout <= 0:
            return node.execute(context)

        res_queue: queue.Queue = queue.Queue()

        def worker() -> None:
            try:
                result = node.execute(context)
                res_queue.put((True, result))
            except Exception as e:
                res_queue.put((False, e))

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

        try:
            success, val = res_queue.get(timeout=timeout)
            if not success:
                raise val
            return val
        except queue.Empty as exc:
            raise TimeoutError(f"Node '{node.name}' timed out after {timeout} seconds.") from exc

    def run(self, graph: WorkflowGraph, initial_inputs: Optional[Dict[str, Any]] = None) -> WorkflowContext:
        """
        Runs the workflow graph.
        """
        # Validate and obtain nodes in topological order
        sorted_nodes = graph.get_topological_sort()
        context = WorkflowContext(initial_inputs)

        for node in sorted_nodes:
            retry_policy = node.retry_policy or {}
            max_retries = retry_policy.get("max_retries", 0)
            backoff_factor = retry_policy.get("backoff_factor", 1.0)

            retries_attempted = 0
            success = False
            last_error = None

            while retries_attempted <= max_retries:
                start_time = datetime.now(timezone.utc)
                try:
                    self._execute_with_timeout(node, context)
                    end_time = datetime.now(timezone.utc)
                    context.record_node_execution(
                        node_name=node.name,
                        status="COMPLETED",
                        start_time=start_time,
                        end_time=end_time,
                        retries=retries_attempted,
                    )
                    success = True
                    break
                except Exception as e:
                    end_time = datetime.now(timezone.utc)
                    last_error = e
                    context.record_node_execution(
                        node_name=node.name,
                        status="FAILED",
                        start_time=start_time,
                        end_time=end_time,
                        error=str(e),
                        retries=retries_attempted,
                    )

                    retries_attempted += 1
                    if retries_attempted <= max_retries:
                        sleep_time = backoff_factor * (2 ** (retries_attempted - 1))
                        time.sleep(sleep_time)

            if not success:
                if self.halt_on_failure:
                    if last_error:
                        raise last_error
                    raise RuntimeError(f"Node '{node.name}' failed to execute.")

        return context
