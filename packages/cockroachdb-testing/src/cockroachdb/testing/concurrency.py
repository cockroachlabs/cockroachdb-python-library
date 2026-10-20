"""Concurrency runner for stress-testing CockroachDB operations.

Executes a callable across multiple threads or async tasks to verify
behaviour under contention — serialization conflicts, deadlock handling,
and throughput characteristics.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class ConcurrencyResult:
    """Aggregated outcome of a concurrent execution run.

    Attributes:
        success_count: Number of invocations that completed without error.
        failure_count: Number of invocations that raised an exception.
        total_duration: Wall-clock time for the entire run in seconds.
        errors: Exceptions collected from failed invocations.
    """

    success_count: int = 0
    failure_count: int = 0
    total_duration: float = 0.0
    errors: list[Exception] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total invocations (successes + failures)."""
        return self.success_count + self.failure_count

    @property
    def error_rate(self) -> float:
        """Fraction of invocations that failed (0.0-1.0)."""
        if self.total_count == 0:
            return 0.0
        return self.failure_count / self.total_count

    @property
    def throughput(self) -> float:
        """Successful invocations per second."""
        if self.total_duration == 0.0:
            return 0.0
        return self.success_count / self.total_duration


class ConcurrencyRunner:
    """Execute a callable concurrently and collect aggregate results.

    Args:
        threads: Number of worker threads (for ``run``).
        iterations: Total number of invocations to distribute across workers.

    Example::

        runner = ConcurrencyRunner(threads=10, iterations=100)

        def transfer():
            conn.execute("UPDATE accounts SET balance = balance - 1 WHERE id = 1")
            conn.execute("UPDATE accounts SET balance = balance + 1 WHERE id = 2")

        result = runner.run(transfer)
        assert result.failure_count == 0
    """

    def __init__(self, threads: int = 10, iterations: int = 100) -> None:
        self._threads = threads
        self._iterations = iterations

    def run(self, fn: Callable[[], Any]) -> ConcurrencyResult:
        """Execute *fn* across threads, collecting successes and errors.

        Args:
            fn: Zero-argument callable to invoke ``iterations`` times.

        Returns:
            A ``ConcurrencyResult`` summarising the run.
        """
        result = ConcurrencyResult()
        start = time.monotonic()

        with ThreadPoolExecutor(max_workers=self._threads) as pool:
            futures = [pool.submit(fn) for _ in range(self._iterations)]

            for future in as_completed(futures):
                try:
                    future.result()
                    result.success_count += 1
                except Exception as exc:
                    result.failure_count += 1
                    result.errors.append(exc)

        result.total_duration = time.monotonic() - start
        return result

    async def run_async(self, fn: Callable[[], Any]) -> ConcurrencyResult:
        """Execute *fn* as concurrent async tasks, collecting results.

        If *fn* is a coroutine function it is awaited directly; otherwise
        it is wrapped in ``asyncio.to_thread`` so blocking callables can
        still be exercised.

        Args:
            fn: Zero-argument callable (sync or async) to invoke ``iterations`` times.

        Returns:
            A ``ConcurrencyResult`` summarising the run.
        """
        result = ConcurrencyResult()
        start = time.monotonic()

        async def _invoke() -> None:
            try:
                if inspect.iscoroutinefunction(fn):
                    await fn()
                else:
                    await asyncio.to_thread(fn)
                result.success_count += 1
            except Exception as exc:
                result.failure_count += 1
                result.errors.append(exc)

        tasks = [asyncio.create_task(_invoke()) for _ in range(self._iterations)]
        await asyncio.gather(*tasks)

        result.total_duration = time.monotonic() - start
        return result
