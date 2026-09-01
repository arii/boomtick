"""Tests for configurable sleep function strategy in AI service and Workflow runner."""

from unittest.mock import MagicMock
from dev_tools.services.ai_service import AIClient
from dev_tools.workflows.runner import WorkflowRunner
from dev_tools.workflows.graph import WorkflowGraph, WorkflowNode


def test_ai_client_custom_sleep_fn():
    """Verify AIClient uses provided sleep_fn during retries."""
    sleep_calls = []

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    client = AIClient(sleep_fn=mock_sleep)
    assert client.sleep_fn is mock_sleep


def test_workflow_runner_custom_sleep_fn():
    """Verify WorkflowRunner calls custom sleep_fn during retry backoff."""
    sleep_calls = []

    def mock_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    runner = WorkflowRunner(halt_on_failure=False, sleep_fn=mock_sleep)
    assert runner.sleep_fn is mock_sleep

    graph = WorkflowGraph()
    fail_node = MagicMock(spec=WorkflowNode)
    fail_node.name = "failing_node"
    fail_node.timeout = None
    fail_node.role = "tester"
    fail_node.retry_policy = {"max_retries": 2, "backoff_factor": 0.5}
    fail_node.execute.side_effect = ValueError("Simulated node error")

    graph.add_node(fail_node)
    runner.run(graph)

    # 2 retries -> 0.5 * (2**0) = 0.5 and 0.5 * (2**1) = 1.0
    assert sleep_calls == [0.5, 1.0]
    runner.shutdown()
