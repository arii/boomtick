# pylint: disable=missing-docstring,too-many-arguments,too-many-positional-arguments
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional


class WorkflowContext:
    """
    Manages the state and metrics of a workflow run.
    Provides thread-safe access to inputs, states, and execution logs.
    """

    def __init__(self, initial_inputs: Optional[Dict[str, Any]] = None) -> None:
        self._lock = threading.Lock()
        self._inputs: Dict[str, Any] = dict(initial_inputs) if initial_inputs else {}
        self._state: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []

    @property
    def inputs(self) -> Dict[str, Any]:
        """Read-only view of the initial inputs."""
        with self._lock:
            return dict(self._inputs)

    @property
    def state(self) -> Dict[str, Any]:
        """Current internal state/outputs of the workflow."""
        with self._lock:
            return dict(self._state)

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

    def record_node_execution(
        self,
        node_name: str,
        status: str,
        start_time: datetime,
        end_time: datetime,
        error: Optional[str] = None,
        retries: int = 0,
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
        }
        with self._lock:
            self._history.append(record)
