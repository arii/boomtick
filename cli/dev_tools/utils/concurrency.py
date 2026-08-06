"""Concurrency utilities for parallel execution of tasks."""
import concurrent.futures
from typing import Callable, Iterable, List, Optional, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def run_concurrently(
    func: Callable[[T], R],
    items: Iterable[T],
    max_workers: int = 4,
    ignore_exceptions: bool = True,
    log_fn: Optional[Callable[[str], None]] = None,
) -> List[R]:
    """
    Executes `func` concurrently across `items` using a ThreadPoolExecutor.
    Handles exceptions by logging them and filtering out failed results if ignore_exceptions=True.
    If ignore_exceptions=False, raises the first encountered exception.
    Ensures order of results corresponds to the order of items (excluding failed ones if ignored).
    An optional log_fn callback can be passed to handle warnings/logging (defaults to project's log_warn).
    """
    if log_fn is None:
        from dev_tools.utils import log_warn  # pylint: disable=import-outside-toplevel
        log_fn = log_warn

    items_list = list(items)
    if not items_list:
        return []

    results_with_idx = []

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(max_workers, max(1, len(items_list)))
    ) as executor:
        future_to_idx = {
            executor.submit(func, item): idx for idx, item in enumerate(items_list)
        }

        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                res = future.result()
                results_with_idx.append((idx, res))
            except Exception as e:
                if not ignore_exceptions:
                    raise e
                func_name = getattr(func, "__name__", "func")
                log_fn(
                    f"Exception in concurrent execution of '{func_name}' for item '{items_list[idx]}': {e}"
                )

    # Sort by index to restore original order
    results_with_idx.sort(key=lambda x: x[0])
    return [res for _, res in results_with_idx]
