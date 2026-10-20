"""Retry engine with exponential backoff and jitter for CockroachDB serialization conflicts."""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING, TypeVar

from cockroachdb.exceptions import CockroachDBRetryExhausted, is_retryable_error
from cockroachdb.types import MetricsCollector, RetryPolicy, TransactionOutcome

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class RetryEngine:
    """Executes callables with automatic retry on serialization conflicts.

    Uses exponential backoff with jitter per CockroachDB's retry protocol.
    """

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._policy = policy or RetryPolicy()
        self._metrics = metrics

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    def _calc_delay(self, attempt: int) -> float:
        delay = min(
            self._policy.base_delay * (self._policy.multiplier**attempt),
            self._policy.max_delay,
        )
        jitter = delay * self._policy.jitter_factor * random.random()
        return delay + jitter

    def run(self, fn: Callable[[], T]) -> T:
        """Execute ``fn`` with retry on retryable errors.

        Each retry re-invokes ``fn`` from scratch, as CockroachDB requires
        the entire transaction to be replayed on serialization failure.
        """
        last_err: Exception | None = None
        start = time.monotonic()

        for attempt in range(self._policy.max_retries + 1):
            try:
                result = fn()
                duration_ms = (time.monotonic() - start) * 1000
                if self._metrics:
                    outcome = (
                        TransactionOutcome.RETRIED if attempt > 0 else TransactionOutcome.COMMITTED
                    )
                    self._metrics.record_transaction(outcome, duration_ms)
                return result
            except Exception as e:
                if not is_retryable_error(e):
                    duration_ms = (time.monotonic() - start) * 1000
                    if self._metrics:
                        self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
                    raise
                last_err = e
                if self._metrics:
                    self._metrics.record_retry(attempt + 1)
                if attempt < self._policy.max_retries:
                    time.sleep(self._calc_delay(attempt))

        duration_ms = (time.monotonic() - start) * 1000
        if self._metrics:
            self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
        raise CockroachDBRetryExhausted(self._policy.max_retries, last_err) from last_err

    async def run_async(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Async version of :meth:`run`."""
        last_err: Exception | None = None
        start = time.monotonic()

        for attempt in range(self._policy.max_retries + 1):
            try:
                result = await fn()
                duration_ms = (time.monotonic() - start) * 1000
                if self._metrics:
                    outcome = (
                        TransactionOutcome.RETRIED if attempt > 0 else TransactionOutcome.COMMITTED
                    )
                    self._metrics.record_transaction(outcome, duration_ms)
                return result
            except Exception as e:
                if not is_retryable_error(e):
                    duration_ms = (time.monotonic() - start) * 1000
                    if self._metrics:
                        self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
                    raise
                last_err = e
                if self._metrics:
                    self._metrics.record_retry(attempt + 1)
                if attempt < self._policy.max_retries:
                    await asyncio.sleep(self._calc_delay(attempt))

        duration_ms = (time.monotonic() - start) * 1000
        if self._metrics:
            self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
        raise CockroachDBRetryExhausted(self._policy.max_retries, last_err) from last_err
