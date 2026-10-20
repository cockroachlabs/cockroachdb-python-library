"""Circuit breaker for CockroachDB connection fault tolerance."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, TypeVar

from cockroachdb.exceptions import CircuitBreakerOpenError
from cockroachdb.types import CircuitBreakerPolicy, CircuitBreakerState

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class CircuitBreaker:
    """Thread-safe circuit breaker that trips after repeated failures.

    Transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED (on success) or OPEN (on failure).
    """

    def __init__(self, policy: CircuitBreakerPolicy | None = None) -> None:
        self._policy = policy or CircuitBreakerPolicy()
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self._state == CircuitBreakerState.OPEN
            and self._last_failure_time is not None
            and time.monotonic() - self._last_failure_time >= self._policy.recovery_timeout
        ):
            self._state = CircuitBreakerState.HALF_OPEN
            self._half_open_calls = 0

    def _check_state(self) -> None:
        self._maybe_transition_to_half_open()

        if self._state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - (self._last_failure_time or 0)
            remaining = max(0.0, self._policy.recovery_timeout - elapsed)
            raise CircuitBreakerOpenError(remaining)

        if (
            self._state == CircuitBreakerState.HALF_OPEN
            and self._half_open_calls >= self._policy.half_open_max_calls
        ):
            raise CircuitBreakerOpenError(self._policy.recovery_timeout)

    def _record_success(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if (
            self._state == CircuitBreakerState.HALF_OPEN
            or self._failure_count >= self._policy.failure_threshold
        ):
            self._state = CircuitBreakerState.OPEN

    def call(self, fn: Callable[[], T]) -> T:
        """Execute ``fn`` through the circuit breaker."""
        with self._lock:
            self._check_state()
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = fn()
        except Exception:
            with self._lock:
                self._record_failure()
            raise
        else:
            with self._lock:
                self._record_success()
            return result

    async def call_async(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Async version of :meth:`call`."""
        with self._lock:
            self._check_state()
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = await fn()
        except Exception:
            with self._lock:
                self._record_failure()
            raise
        else:
            with self._lock:
                self._record_success()
            return result

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
