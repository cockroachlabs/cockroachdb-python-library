"""Tests for cockroachdb.core.retry.RetryEngine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from conftest import FakeNonRetryableError, FakeRetryableError

from cockroachdb.core.retry import RetryEngine
from cockroachdb.exceptions import CockroachDBRetryExhausted
from cockroachdb.types import RetryPolicy, TransactionOutcome


class TestRetryEngineRun:
    """Tests for RetryEngine.run() (synchronous)."""

    def test_succeeds_first_try(self) -> None:
        engine = RetryEngine(policy=RetryPolicy(max_retries=3))
        result = engine.run(lambda: "ok")
        assert result == "ok"

    def test_retries_on_retryable_error(self) -> None:
        call_count = 0

        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FakeRetryableError()
            return "done"

        engine = RetryEngine(policy=RetryPolicy(max_retries=5, base_delay=0.0))
        result = engine.run(fn)
        assert result == "done"
        assert call_count == 3

    def test_raises_non_retryable_immediately(self) -> None:
        engine = RetryEngine(policy=RetryPolicy(max_retries=5, base_delay=0.0))

        with pytest.raises(FakeNonRetryableError):
            engine.run(lambda: (_ for _ in ()).throw(FakeNonRetryableError("fail")))

    def test_exhaustion_raises(self) -> None:
        def always_fail() -> str:
            raise FakeRetryableError()

        engine = RetryEngine(policy=RetryPolicy(max_retries=2, base_delay=0.0))

        with pytest.raises(CockroachDBRetryExhausted) as exc_info:
            engine.run(always_fail)
        assert exc_info.value.max_retries == 2

    def test_records_metrics_on_success(self) -> None:
        metrics = MagicMock()
        engine = RetryEngine(policy=RetryPolicy(max_retries=3), metrics=metrics)
        engine.run(lambda: "ok")

        metrics.record_transaction.assert_called_once()
        call_args = metrics.record_transaction.call_args
        assert call_args[0][0] == TransactionOutcome.COMMITTED

    def test_records_metrics_on_retry_then_success(self) -> None:
        metrics = MagicMock()
        call_count = 0

        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FakeRetryableError()
            return "ok"

        engine = RetryEngine(policy=RetryPolicy(max_retries=3, base_delay=0.0), metrics=metrics)
        engine.run(fn)

        metrics.record_retry.assert_called_once_with(1)
        tx_call = metrics.record_transaction.call_args
        assert tx_call[0][0] == TransactionOutcome.RETRIED


class TestRetryEngineRunAsync:
    """Tests for RetryEngine.run_async()."""

    @pytest.mark.asyncio
    async def test_async_succeeds_first_try(self) -> None:
        engine = RetryEngine(policy=RetryPolicy(max_retries=3))

        async def fn() -> str:
            return "async_ok"

        result = await engine.run_async(fn)
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_async_retries_on_retryable(self) -> None:
        call_count = 0

        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FakeRetryableError()
            return "done"

        engine = RetryEngine(policy=RetryPolicy(max_retries=3, base_delay=0.0))
        result = await engine.run_async(fn)
        assert result == "done"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_exhaustion(self) -> None:
        async def always_fail() -> str:
            raise FakeRetryableError()

        engine = RetryEngine(policy=RetryPolicy(max_retries=1, base_delay=0.0))

        with pytest.raises(CockroachDBRetryExhausted):
            await engine.run_async(always_fail)

    @pytest.mark.asyncio
    async def test_async_non_retryable_raises(self) -> None:
        async def fail() -> str:
            raise FakeNonRetryableError("boom")

        engine = RetryEngine(policy=RetryPolicy(max_retries=3))

        with pytest.raises(FakeNonRetryableError):
            await engine.run_async(fail)
