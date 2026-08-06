# pylint: disable=missing-docstring,redefined-outer-name
import time
from unittest.mock import patch

import pytest
from dev_tools.utils.concurrency import run_concurrently


def test_run_concurrently_basic():
    def double(x: int) -> int:
        return x * 2

    items = [1, 2, 3, 4, 5]
    results = run_concurrently(double, items)
    assert results == [2, 4, 6, 8, 10]


def test_run_concurrently_empty():
    results = run_concurrently(lambda x: x, [])
    assert results == []


def test_run_concurrently_ordering():
    def delay_func(x: int) -> int:
        # Sleep proportional to index but reversed so they complete out of order
        time.sleep(0.01 * (5 - x))
        return x

    items = [1, 2, 3, 4, 5]
    results = run_concurrently(delay_func, items)
    # Ordering must be preserved in the final results list
    assert results == [1, 2, 3, 4, 5]


def test_run_concurrently_ignore_exceptions():
    def divide_one(x: int) -> float:
        if x == 0:
            raise ValueError("Cannot divide by zero")
        return 1.0 / x

    items = [1, 0, 2, 0, 4]
    with patch("dev_tools.utils.log_warn") as mock_log_warn:
        results = run_concurrently(divide_one, items, ignore_exceptions=True)
        assert results == [1.0, 0.5, 0.25]
        # Two warnings should have been logged for the two divisions by zero
        assert mock_log_warn.call_count == 2
        logged_messages = "".join(call[0][0] for call in mock_log_warn.call_args_list)
        assert "Cannot divide by zero" in logged_messages


def test_run_concurrently_raise_on_exception():
    def divide_one(x: int) -> float:
        if x == 0:
            raise ValueError("Cannot divide by zero")
        return 1.0 / x

    items = [1, 0, 2]
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        run_concurrently(divide_one, items, ignore_exceptions=False)
