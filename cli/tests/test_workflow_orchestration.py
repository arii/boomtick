# pylint: disable=missing-docstring,unused-argument,too-few-public-methods,import-outside-toplevel
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.workflows import (
    CycleDetectedError,
    EnvironmentCheckNode,
    IssueValidationNode,
    MissingDependencyError,
    WorkflowContext,
    WorkflowGraph,
    WorkflowNode,
    WorkflowRunner,
)


class DummyNode(WorkflowNode):

    def __init__(self, name, execution_fn=None, **kwargs):
        super().__init__(name, **kwargs)
        self.execution_fn = execution_fn

    def execute(self, context: WorkflowContext):
        if self.execution_fn:
            return self.execution_fn(context)
        return f"Result from {self.name}"


def test_context_state_and_history():
    ctx = WorkflowContext(initial_inputs={"key1": "val1", "key2": "val2"})

    assert ctx.inputs == {"key1": "val1", "key2": "val2"}
    assert ctx.get("key1") == "val1"
    assert ctx.get("key3", "default") == "default"

    ctx.set("key1", "new_val")
    assert ctx.get("key1") == "new_val"
    assert ctx.inputs["key1"] == "val1"  # inputs should remain untouched

    ctx.update({"key3": "val3", "key4": "val4"})
    assert ctx.get("key3") == "val3"
    assert ctx.get("key4") == "val4"

    start = datetime.now(timezone.utc)
    end = datetime.now(timezone.utc)
    ctx.record_node_execution("NodeA", "COMPLETED", start, end, retries=1)

    assert len(ctx.history) == 1
    assert ctx.history[0]["node_name"] == "NodeA"
    assert ctx.history[0]["status"] == "COMPLETED"
    assert ctx.history[0]["retries"] == 1


def test_node_initialization():
    node = DummyNode("Test")
    assert node.name == "Test"
    assert node.retry_policy == {"max_retries": 0, "backoff_factor": 1.0}
    assert node.timeout is None

    node_custom = DummyNode(
        "Custom",
        retry_policy={"max_retries": 3, "backoff_factor": 2.0},
        timeout=5.0,
    )
    assert node_custom.retry_policy == {"max_retries": 3, "backoff_factor": 2.0}
    assert node_custom.timeout == 5.0


def test_graph_validation_success():
    graph = WorkflowGraph()
    node_a = DummyNode("A")
    node_b = DummyNode("B")
    node_c = DummyNode("C")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    graph.add_edge("A", "B")
    graph.add_edge("B", "C")

    # Should not raise any error
    graph.validate()

    sorted_nodes = graph.get_topological_sort()
    assert [n.name for n in sorted_nodes] == ["A", "B", "C"]


def test_graph_duplicate_node():
    graph = WorkflowGraph()
    node_a = DummyNode("A")
    graph.add_node(node_a)
    with pytest.raises(ValueError, match="already exists"):
        graph.add_node(node_a)


def test_graph_cycle_detection():
    graph = WorkflowGraph()
    node_a = DummyNode("A")
    node_b = DummyNode("B")
    node_c = DummyNode("C")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    graph.add_edge("A", "B")
    graph.add_edge("B", "C")
    graph.add_edge("C", "A")

    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        graph.validate()


def test_graph_missing_dependency():
    graph = WorkflowGraph()
    node_a = DummyNode("A")

    graph.add_node(node_a)
    graph.add_edge("A", "B")  # B is not added to the graph

    with pytest.raises(MissingDependencyError, match="not in the graph"):
        graph.validate()


def test_runner_successful_execution():
    graph = WorkflowGraph()

    def run_a(ctx):
        ctx.set("a_out", "hello")
        return "A done"

    def run_b(ctx):
        a_val = ctx.get("a_out")
        ctx.set("b_out", f"{a_val} world")
        return "B done"

    node_a = DummyNode("A", execution_fn=run_a)
    node_b = DummyNode("B", execution_fn=run_b)

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_edge("A", "B")

    runner = WorkflowRunner()
    context = runner.run(graph, initial_inputs={"init_key": "init_val"})

    assert context.get("a_out") == "hello"
    assert context.get("b_out") == "hello world"
    assert context.get("init_key") == "init_val"

    assert len(context.history) == 2
    assert context.history[0]["node_name"] == "A"
    assert context.history[0]["status"] == "COMPLETED"
    assert context.history[1]["node_name"] == "B"
    assert context.history[1]["status"] == "COMPLETED"


def test_runner_node_failure_halts():
    graph = WorkflowGraph()

    def failing_fn(ctx):
        raise ValueError("Something went wrong")

    node_a = DummyNode("A", execution_fn=failing_fn)
    node_b = DummyNode("B")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_edge("A", "B")

    runner = WorkflowRunner()
    with pytest.raises(ValueError, match="Something went wrong"):
        runner.run(graph)

    # Subsequent node B should not be executed


@patch("time.sleep", return_value=None)
def test_runner_retries_with_exponential_backoff(mock_sleep):
    graph = WorkflowGraph()
    attempts = 0

    def retry_fn(ctx):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError(f"Fail attempt {attempts}")
        ctx.set("success_on_attempt", attempts)
        return "Success"

    node = DummyNode("A", execution_fn=retry_fn, retry_policy={"max_retries": 3, "backoff_factor": 1.0})
    graph.add_node(node)

    runner = WorkflowRunner()
    context = runner.run(graph)

    assert context.get("success_on_attempt") == 3
    assert attempts == 3

    # Check history contains failed attempts followed by completed attempt
    assert len(context.history) == 3
    assert context.history[0]["status"] == "FAILED"
    assert context.history[0]["retries"] == 0
    assert context.history[1]["status"] == "FAILED"
    assert context.history[1]["retries"] == 1
    assert context.history[2]["status"] == "COMPLETED"
    assert context.history[2]["retries"] == 2

    # Check backoff sleep times
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0)  # 1.0 * (2 ** 0)
    mock_sleep.assert_any_call(2.0)  # 1.0 * (2 ** 1)


def test_runner_timeout_handling():
    graph = WorkflowGraph()

    def slow_fn(ctx):
        time.sleep(0.5)
        return "Too slow"

    node = DummyNode("A", execution_fn=slow_fn, timeout=0.1)
    graph.add_node(node)

    runner = WorkflowRunner()
    with pytest.raises(TimeoutError, match="timed out after 0.1 seconds"):
        runner.run(graph)


@patch("dev_tools.orchestrator.Orchestrator")
def test_concrete_nodes_execution(mock_orchestrator_class):
    mock_orchestrator = MagicMock()
    mock_orchestrator_class.return_value = mock_orchestrator
    mock_orchestrator.runtime_check.return_value = {"node": "24.16.0", "pnpm": "10.28.2"}
    mock_orchestrator.validate_issue.return_value = {"status": "success", "total_findings": 0}

    graph = WorkflowGraph()
    node_env = EnvironmentCheckNode()
    node_issue = IssueValidationNode()

    graph.add_node(node_env)
    graph.add_node(node_issue)
    graph.add_edge("EnvironmentCheck", "IssueValidation")

    runner = WorkflowRunner()
    context = runner.run(graph, initial_inputs={"issue_number": 42})

    # Verify calls on mocked orchestrator
    mock_orchestrator.runtime_check.assert_called_once()
    mock_orchestrator.validate_issue.assert_called_once_with(
        issueNumber=42, all_open=False, post_comments=False, dry_run=True
    )

    # Verify context outputs are set correctly
    assert context.get("runtime_info") == {"node": "24.16.0", "pnpm": "10.28.2"}
    assert context.get("issue_validation_results") == {"status": "success", "total_findings": 0}
