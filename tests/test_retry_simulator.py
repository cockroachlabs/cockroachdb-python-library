"""Tests for cockroachdb.testing.retry_simulator."""

from __future__ import annotations

import contextlib

import pytest

from cockroachdb.exceptions import is_retryable_error
from cockroachdb.testing.retry_simulator import FakeSerializationError, RetrySimulator


class TestFakeSerializationError:
    """Tests for FakeSerializationError."""

    def test_has_sqlstate_40001(self) -> None:
        err = FakeSerializationError()
        assert err.sqlstate == "40001"

    def test_has_pgcode_40001(self) -> None:
        err = FakeSerializationError()
        assert err.pgcode == "40001"

    def test_is_retryable(self) -> None:
        err = FakeSerializationError()
        assert is_retryable_error(err) is True

    def test_custom_message(self) -> None:
        err = FakeSerializationError("custom msg")
        assert str(err) == "custom msg"


class TestRetrySimulator:
    """Tests for RetrySimulator."""

    def test_fails_then_succeeds(self) -> None:
        sim = RetrySimulator(fail_count=2)
        with pytest.raises(FakeSerializationError):
            sim.execute(lambda: "ok")
        with pytest.raises(FakeSerializationError):
            sim.execute(lambda: "ok")
        result = sim.execute(lambda: "ok")
        assert result == "ok"

    def test_zero_failures_succeeds_immediately(self) -> None:
        sim = RetrySimulator(fail_count=0)
        result = sim.execute(lambda: "immediate")
        assert result == "immediate"

    def test_assert_retried_passes(self) -> None:
        sim = RetrySimulator(fail_count=3)
        for _ in range(3):
            with contextlib.suppress(FakeSerializationError):
                sim.execute(lambda: "ok")
        sim.execute(lambda: "ok")
        sim.assert_retried(expected_attempts=4)

    def test_assert_retried_fails(self) -> None:
        sim = RetrySimulator(fail_count=1)
        with contextlib.suppress(FakeSerializationError):
            sim.execute(lambda: "ok")
        sim.execute(lambda: "ok")
        with pytest.raises(AssertionError):
            sim.assert_retried(expected_attempts=5)

    def test_call_count_property(self) -> None:
        sim = RetrySimulator(fail_count=2)
        with contextlib.suppress(FakeSerializationError):
            sim.execute(lambda: "ok")
        assert sim.call_count == 1

    def test_retry_count_property(self) -> None:
        sim = RetrySimulator(fail_count=3)
        for _ in range(3):
            with contextlib.suppress(FakeSerializationError):
                sim.execute(lambda: "ok")
        assert sim.retry_count == 3

    def test_executes_fn_after_failures(self) -> None:
        sim = RetrySimulator(fail_count=1)
        with contextlib.suppress(FakeSerializationError):
            sim.execute(lambda: "ok")
        # The lambda is called when failures are exhausted
        result = sim.execute(lambda: 42)
        assert result == 42
