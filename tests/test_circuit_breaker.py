"""Tests for cockroachdb.core.circuit_breaker.CircuitBreaker."""

from __future__ import annotations

import time

import pytest

from cockroachdb.core.circuit_breaker import CircuitBreaker
from cockroachdb.exceptions import CircuitBreakerOpenError
from cockroachdb.types import CircuitBreakerPolicy, CircuitBreakerState


class TestCircuitBreakerClosed:
    """Tests for CLOSED state behavior."""

    def test_starts_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED

    def test_successful_calls_stay_closed(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=3))
        for _ in range(10):
            result = cb.call(lambda: "ok")
            assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED

    def test_failures_below_threshold_stay_closed(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=5))
        for _ in range(4):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 4


class TestCircuitBreakerOpen:
    """Tests for CLOSED -> OPEN transition and OPEN behavior."""

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=3))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

    def test_open_rejects_calls(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=1))
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not run")

    def test_failure_count_tracks(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=3))
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.failure_count == 3


class TestCircuitBreakerHalfOpen:
    """Tests for OPEN -> HALF_OPEN transition."""

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker(
            policy=CircuitBreakerPolicy(failure_threshold=1, recovery_timeout=0.01)
        )
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        cb = CircuitBreaker(
            policy=CircuitBreakerPolicy(failure_threshold=1, recovery_timeout=0.01)
        )
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.02)
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_failure_reopens(self) -> None:
        cb = CircuitBreaker(
            policy=CircuitBreakerPolicy(failure_threshold=1, recovery_timeout=0.01)
        )
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.02)
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail again")))
        assert cb.state == CircuitBreakerState.OPEN

    def test_half_open_limits_calls(self) -> None:
        cb = CircuitBreaker(
            policy=CircuitBreakerPolicy(
                failure_threshold=1, recovery_timeout=0.01, half_open_max_calls=1
            )
        )
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        time.sleep(0.02)
        # First call in half_open is allowed
        cb.call(lambda: "ok")
        # Circuit is now closed, so more calls should work
        assert cb.state == CircuitBreakerState.CLOSED


class TestCircuitBreakerReset:
    """Tests for manual reset."""

    def test_reset_from_open(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=1))
        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitBreakerState.OPEN

        cb.reset()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0


class TestCircuitBreakerAsync:
    """Tests for async call_async method."""

    @pytest.mark.asyncio
    async def test_async_success(self) -> None:
        cb = CircuitBreaker()

        async def fn() -> str:
            return "async_ok"

        result = await cb.call_async(fn)
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_async_opens_on_failures(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=2))

        async def fail() -> str:
            raise RuntimeError("boom")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call_async(fail)

        assert cb.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_async_rejects_when_open(self) -> None:
        cb = CircuitBreaker(policy=CircuitBreakerPolicy(failure_threshold=1))

        async def fail() -> str:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call_async(fail)

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_async(fail)
