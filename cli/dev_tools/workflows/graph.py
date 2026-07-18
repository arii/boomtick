# pylint: disable=missing-docstring
from typing import Dict, List, Set

from dev_tools.workflows.node import WorkflowNode


class WorkflowGraphError(Exception):
    """Base exception for workflow graph errors."""


class CycleDetectedError(WorkflowGraphError):
    """Raised when a cycle is detected in the workflow graph."""


class MissingDependencyError(WorkflowGraphError):
    """Raised when a dependency referenced in an edge is missing from the graph."""


class WorkflowGraph:
    """
    Represents a directed execution graph (DAG) of WorkflowNodes.
    Ensures cycle detection and dependency completeness validation.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: Dict[str, Set[str]] = {}  # from_node -> set of to_nodes
        self.dependencies: Dict[str, Set[str]] = {}  # to_node -> set of from_nodes

    def add_node(self, node: WorkflowNode) -> None:
        """Add a node to the graph."""
        if node.name in self.nodes:
            raise ValueError(f"Node with name '{node.name}' already exists in graph.")
        self.nodes[node.name] = node
        if node.name not in self.edges:
            self.edges[node.name] = set()
        if node.name not in self.dependencies:
            self.dependencies[node.name] = set()

    def add_edge(self, from_node: str, to_node: str) -> None:
        """
        Add a directed edge indicating that to_node depends on from_node.
        from_node executes BEFORE to_node.
        """
        if from_node not in self.edges:
            self.edges[from_node] = set()
        self.edges[from_node].add(to_node)

        if to_node not in self.dependencies:
            self.dependencies[to_node] = set()
        self.dependencies[to_node].add(from_node)

    def validate(self) -> None:
        """
        Validates the graph topology:
        1. Checks that all nodes referenced in edges actually exist.
        2. Detects any cycles.
        """
        # Validate existence of all nodes in edges
        for from_node, to_nodes in self.edges.items():
            if from_node not in self.nodes:
                raise MissingDependencyError(f"Edge references node '{from_node}' which is not in the graph.")
            for to_node in to_nodes:
                if to_node not in self.nodes:
                    raise MissingDependencyError(
                        f"Node '{from_node}' depends on/flows to '{to_node}' which is not in the graph."
                    )

        # Detect cycles using DFS coloring
        # 0 = unvisited, 1 = visiting, 2 = visited
        visited: Dict[str, int] = {name: 0 for name in self.nodes}
        path: List[str] = []

        def dfs(node_name: str) -> None:
            visited[node_name] = 1  # visiting
            path.append(node_name)

            for neighbor in self.edges.get(node_name, set()):
                if visited.get(neighbor, 0) == 1:
                    cycle_start_idx = path.index(neighbor)
                    cycle_path = path[cycle_start_idx:] + [neighbor]
                    cycle_str = " -> ".join(cycle_path)
                    raise CycleDetectedError(f"Cycle detected in workflow graph: {cycle_str}")
                if visited.get(neighbor, 0) == 0:
                    dfs(neighbor)

            path.pop()
            visited[node_name] = 2  # visited

        for node_name in self.nodes:
            if visited[node_name] == 0:
                dfs(node_name)

    def get_topological_sort(self) -> List[WorkflowNode]:
        """
        Returns the nodes in topological order.
        Validates the graph before sorting.
        """
        self.validate()

        # Kahn's algorithm or DFS post-order reversal
        visited: Set[str] = set()
        order: List[str] = []

        def visit(node_name: str) -> None:
            if node_name not in visited:
                visited.add(node_name)
                # Visit all nodes that this node depends on first
                for dep in self.dependencies.get(node_name, set()):
                    visit(dep)
                order.append(node_name)

        for name in self.nodes:
            visit(name)

        return [self.nodes[name] for name in order]
