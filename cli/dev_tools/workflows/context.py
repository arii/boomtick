# pylint: disable=missing-docstring,too-many-arguments,too-many-positional-arguments
import threading
from datetime import datetime
from types import MappingProxyType
from typing import Any, Dict, List, Optional

from dev_tools.services.context_builder import ContextBuilder


class WorkflowContext:
    """
    Manages the state and metrics of a workflow run.
    Provides thread-safe access to inputs, states, execution logs, and a shared scratchpad
    for a single agent to transition through different roles.
    """

    def __init__(
        self, initial_inputs: Optional[Dict[str, Any]] = None, builder: Optional[ContextBuilder] = None
    ) -> None:
        self._lock = threading.Lock()
        self._inputs: Dict[str, Any] = dict(initial_inputs) if initial_inputs else {}
        self._state: Dict[str, Any] = {}
        self._scratchpad: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        self.builder = builder if builder is not None else ContextBuilder()

    @property
    def inputs(self) -> MappingProxyType:
        """Read-only proxy view of the initial inputs to avoid redundant memory allocations."""
        with self._lock:
            return MappingProxyType(self._inputs)

    @property
    def state(self) -> MappingProxyType:
        """Read-only proxy view of internal state/outputs of the workflow to avoid redundant memory allocations."""
        with self._lock:
            return MappingProxyType(self._state)

    @property
    def scratchpad(self) -> MappingProxyType:
        """Shared agent scratchpad/blackboard for intermediate thoughts and findings."""
        with self._lock:
            return MappingProxyType(self._scratchpad)

    @property
    def history(self) -> List[Dict[str, Any]]:
        """History of node executions."""
        with self._lock:
            return list(self._history)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state. If not found, fall back to inputs."""
        with self._lock:
            if key in self._state:
                return self._state[key]
            return self._inputs.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the internal state."""
        with self._lock:
            self._state[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """Update multiple keys in the state."""
        with self._lock:
            self._state.update(data)

    def write_scratchpad(self, key: str, value: Any, role: str = "agent") -> None:
        """Write intermediate thoughts or notes to the scratchpad."""
        with self._lock:
            self._scratchpad[key] = value
            self.builder.add_scratch_note(role=role, note=f"{key}: {value}")

    def read_scratchpad(self, key: str, default: Any = None) -> Any:
        """Read intermediate thoughts or notes from the scratchpad."""
        with self._lock:
            return self._scratchpad.get(key, default)

    def record_node_execution(
        self,
        node_name: str,
        status: str,
        start_time: datetime,
        end_time: datetime,
        error: Optional[str] = None,
        retries: int = 0,
        role: Optional[str] = None,
    ) -> None:
        """Records metrics for a node execution."""
        duration = (end_time - start_time).total_seconds()
        record = {
            "node_name": node_name,
            "status": status,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_sec": duration,
            "error": error,
            "retries": retries,
            "role": role,
        }
        with self._lock:
            self._history.append(record)
