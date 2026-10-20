"""Retry simulator for testing CockroachDB retry logic.

Provides a controllable error source that mimics CockroachDB serialization
failures (SQLSTATE 40001), allowing unit tests to verify retry behaviour
without a live database.
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class FakeSerializationError(Exception):
    """Simulated serialization failure with ``pgcode`` / ``sqlstate`` = ``40001``.

    Compatible with the detection logic used by ``cockroachdb.decorators.crdb_retry``
    and most PostgreSQL driver error classifiers.
    """

    pgcode: str = "40001"
    sqlstate: str = "40001"

    def __init__(self, message: str = "fake serialization error") -> None:
        super().__init__(message)


class RetrySimulator:
    """Deterministic failure source for retry-loop testing.

    The simulator raises ``FakeSerializationError`` for the first *fail_count*
    invocations, then delegates to the wrapped callable on subsequent calls.

    Args:
        fail_count: Number of failures to inject before allowing success.

    Example::

        sim = RetrySimulator(fail_count=3)

        @crdb_retry
        def do_work() -> str:
            return sim.execute(lambda: "ok")

        result = do_work()
        assert result == "ok"
        sim.assert_retried(expected_attempts=4)  # 3 failures + 1 success
    """

    def __init__(self, fail_count: int = 3) -> None:
        self._fail_count = fail_count
        self._call_count: int = 0
        self._retry_count: int = 0

    # -- Public API -------------------------------------------------------

    def execute(self, fn: Any) -> Any:
        """Call *fn*, raising ``FakeSerializationError`` for the first N calls.

        Args:
            fn: Zero-argument callable to invoke when failures are exhausted.

        Returns:
            The return value of *fn* once the failure budget is spent.

        Raises:
            FakeSerializationError: For the first ``fail_count`` invocations.
        """
        self._call_count += 1

        if self._call_count <= self._fail_count:
            self._retry_count += 1
            raise FakeSerializationError(
                f"simulated serialization failure (attempt {self._call_count})"
            )

        return fn()

    def assert_retried(self, expected_attempts: int) -> None:
        """Assert that the simulator was called exactly *expected_attempts* times.

        Args:
            expected_attempts: Total calls (failures + final success).

        Raises:
            AssertionError: If the actual call count does not match.
        """
        if self._call_count != expected_attempts:
            msg = (
                f"Expected {expected_attempts} attempts but got {self._call_count} "
                f"({self._retry_count} retries)"
            )
            raise AssertionError(msg)

    # -- Properties -------------------------------------------------------

    @property
    def call_count(self) -> int:
        """Total number of times ``execute`` has been called."""
        return self._call_count

    @property
    def retry_count(self) -> int:
        """Number of calls that resulted in a simulated failure."""
        return self._retry_count

    # -- Utilities --------------------------------------------------------

    def reset(self) -> None:
        """Reset all counters so the simulator can be reused."""
        self._call_count = 0
        self._retry_count = 0
