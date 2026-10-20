"""Tests for cockroachdb.exceptions."""

from __future__ import annotations

from conftest import (
    FakeDeadlockError,
    FakeNonRetryableError,
    FakeRetryableError,
    FakeRetryableErrorPgcode,
    FakeWrappedRetryableError,
)

from cockroachdb.exceptions import (
    CircuitBreakerOpenError,
    CockroachDBError,
    CockroachDBRetryExhausted,
    RegionValidationError,
    is_retryable_error,
)


class TestIsRetryableError:
    """Tests for the is_retryable_error() function."""

    def test_retryable_with_sqlstate_40001(self, retryable_error: FakeRetryableError) -> None:
        assert is_retryable_error(retryable_error) is True

    def test_retryable_with_pgcode_40001(
        self, retryable_error_pgcode: FakeRetryableErrorPgcode
    ) -> None:
        assert is_retryable_error(retryable_error_pgcode) is True

    def test_retryable_with_deadlock_40P01(self, deadlock_error: FakeDeadlockError) -> None:
        assert is_retryable_error(deadlock_error) is True

    def test_not_retryable_for_generic_error(
        self, non_retryable_error: FakeNonRetryableError
    ) -> None:
        assert is_retryable_error(non_retryable_error) is False

    def test_retryable_with_nested_cause(
        self, wrapped_retryable_error: FakeWrappedRetryableError
    ) -> None:
        assert is_retryable_error(wrapped_retryable_error) is True

    def test_not_retryable_with_wrong_sqlstate(self) -> None:
        class WrongState(Exception):
            sqlstate = "23505"  # unique_violation

        assert is_retryable_error(WrongState()) is False

    def test_not_retryable_plain_exception(self) -> None:
        assert is_retryable_error(ValueError("nope")) is False


class TestCockroachDBRetryExhausted:
    """Tests for CockroachDBRetryExhausted exception."""

    def test_attributes(self) -> None:
        inner = FakeRetryableError()
        exc = CockroachDBRetryExhausted(max_retries=5, last_error=inner)
        assert exc.max_retries == 5
        assert exc.last_error is inner

    def test_message_format(self) -> None:
        exc = CockroachDBRetryExhausted(max_retries=3, last_error=None)
        assert "3 retries" in str(exc)

    def test_is_cockroachdb_error(self) -> None:
        assert issubclass(CockroachDBRetryExhausted, CockroachDBError)


class TestCircuitBreakerOpenError:
    """Tests for CircuitBreakerOpenError."""

    def test_recovery_seconds(self) -> None:
        exc = CircuitBreakerOpenError(recovery_seconds=15.0)
        assert exc.recovery_seconds == 15.0
        assert "15.0" in str(exc)


class TestRegionValidationError:
    """Tests for RegionValidationError."""

    def test_attributes(self) -> None:
        exc = RegionValidationError(region="BAD", reason="invalid format")
        assert exc.region == "BAD"
        assert exc.reason == "invalid format"
        assert "BAD" in str(exc)
