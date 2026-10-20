"""Tests for cockroachdb.testing.concurrency."""

from __future__ import annotations

import pytest

from cockroachdb.testing.concurrency import ConcurrencyResult, ConcurrencyRunner


class TestConcurrencyResult:
    """Tests for ConcurrencyResult dataclass."""

    def test_total_count(self) -> None:
        r = ConcurrencyResult(success_count=7, failure_count=3)
        assert r.total_count == 10

    def test_error_rate(self) -> None:
        r = ConcurrencyResult(success_count=8, failure_count=2)
        assert r.error_rate == pytest.approx(0.2)

    def test_error_rate_zero_total(self) -> None:
        r = ConcurrencyResult()
        assert r.error_rate == 0.0

    def test_throughput(self) -> None:
        r = ConcurrencyResult(success_count=100, total_duration=2.0)
        assert r.throughput == pytest.approx(50.0)

    def test_throughput_zero_duration(self) -> None:
        r = ConcurrencyResult(success_count=5, total_duration=0.0)
        assert r.throughput == 0.0


class TestConcurrencyRunnerSync:
    """Tests for ConcurrencyRunner.run() (thread-based)."""

    def test_all_succeed(self) -> None:
        runner = ConcurrencyRunner(threads=4, iterations=20)
        result = runner.run(lambda: None)
        assert result.success_count == 20
        assert result.failure_count == 0
        assert result.total_duration > 0

    def test_collects_failures(self) -> None:
        call_count = 0

        def sometimes_fail() -> None:
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise ValueError("fail")

        runner = ConcurrencyRunner(threads=1, iterations=6)
        result = runner.run(sometimes_fail)
        assert result.failure_count > 0
        assert result.success_count + result.failure_count == 6
        assert len(result.errors) == result.failure_count

    def test_returns_concurrency_result(self) -> None:
        runner = ConcurrencyRunner(threads=2, iterations=5)
        result = runner.run(lambda: None)
        assert isinstance(result, ConcurrencyResult)


class TestConcurrencyRunnerAsync:
    """Tests for ConcurrencyRunner.run_async()."""

    @pytest.mark.asyncio
    async def test_async_all_succeed(self) -> None:
        runner = ConcurrencyRunner(threads=4, iterations=10)

        async def async_task() -> None:
            pass

        result = await runner.run_async(async_task)
        assert result.success_count == 10
        assert result.failure_count == 0

    @pytest.mark.asyncio
    async def test_async_collects_failures(self) -> None:
        call_count = 0

        async def sometimes_fail() -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise RuntimeError("async fail")

        runner = ConcurrencyRunner(threads=1, iterations=6)
        result = await runner.run_async(sometimes_fail)
        assert result.failure_count == 3
        assert result.success_count == 3

    @pytest.mark.asyncio
    async def test_async_with_sync_function(self) -> None:
        runner = ConcurrencyRunner(threads=2, iterations=5)
        # Sync function should be wrapped in asyncio.to_thread
        result = await runner.run_async(lambda: None)
        assert result.success_count == 5
        assert result.failure_count == 0

    @pytest.mark.asyncio
    async def test_async_duration_tracked(self) -> None:
        runner = ConcurrencyRunner(threads=2, iterations=3)

        async def task() -> None:
            pass

        result = await runner.run_async(task)
        assert result.total_duration >= 0
