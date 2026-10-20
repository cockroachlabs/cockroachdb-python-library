"""Tests for cockroachdb.django.retry — Django retry utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cockroachdb.django.retry import atomic_with_retry, execute_with_retry
from cockroachdb.django.signals import (
    cockroachdb_retry_exhausted,
    post_cockroachdb_retry,
    pre_cockroachdb_retry,
)
from cockroachdb.exceptions import CockroachDBRetryExhausted


class FakeSerializationError(Exception):
    """Simulates a Django OperationalError wrapping a psycopg serialization error."""

    sqlstate: str = "40001"


class FakeWrappedSerializationError(Exception):
    """Outer exception whose __cause__ has sqlstate 40001."""

    def __init__(self) -> None:
        inner = FakeSerializationError("inner conflict")
        super().__init__("wrapped error")
        self.__cause__ = inner


class TestExecuteWithRetry:
    """Tests for execute_with_retry."""

    def test_succeeds_on_first_attempt(self) -> None:
        """No retry needed when fn succeeds immediately."""
        result = execute_with_retry(lambda: "ok")
        assert result == "ok"

    @patch("cockroachdb.django.retry.time.sleep")
    def test_retries_on_serialization_error(self, mock_sleep: MagicMock) -> None:
        """Retries on SQLSTATE 40001 and eventually succeeds."""
        call_count = 0

        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FakeSerializationError("conflict")
            return "success"

        result = execute_with_retry(fn, max_retries=3)
        assert result == "success"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("cockroachdb.django.retry.time.sleep")
    def test_retries_on_wrapped_serialization_error(self, mock_sleep: MagicMock) -> None:
        """Retries when the serialization error is wrapped via __cause__."""
        call_count = 0

        def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FakeWrappedSerializationError()
            return "success"

        result = execute_with_retry(fn, max_retries=3)
        assert result == "success"
        assert call_count == 2

    def test_does_not_retry_on_non_retryable_error(self) -> None:
        """Non-retryable errors are raised immediately without retry."""
        call_count = 0

        def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("bad data")

        with pytest.raises(ValueError, match="bad data"):
            execute_with_retry(fn)

        assert call_count == 1

    @patch("cockroachdb.django.retry.time.sleep")
    def test_retry_exhausted_raises(self, mock_sleep: MagicMock) -> None:
        """CockroachDBRetryExhausted is raised when all retries are used."""

        def fn() -> str:
            raise FakeSerializationError("conflict")

        with pytest.raises(CockroachDBRetryExhausted) as exc_info:
            execute_with_retry(fn, max_retries=2)

        assert exc_info.value.max_retries == 2

    @patch("cockroachdb.django.retry.time.sleep")
    def test_passes_args_and_kwargs(self, mock_sleep: MagicMock) -> None:
        """Arguments are forwarded to the wrapped function."""

        def fn(a: int, b: int, c: int = 0) -> int:
            return a + b + c

        result = execute_with_retry(fn, 1, 2, c=3)
        assert result == 6

    @patch("cockroachdb.django.retry.time.sleep")
    def test_pre_retry_signal_sent(self, mock_sleep: MagicMock) -> None:
        """pre_cockroachdb_retry signal is sent before each retry."""
        received: list[dict] = []

        def handler(sender: object, attempt: int, error: Exception, **kwargs: object) -> None:
            received.append({"sender": sender, "attempt": attempt})

        pre_cockroachdb_retry.connect(handler)
        try:
            call_count = 0

            def fn() -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise FakeSerializationError("conflict")
                return "ok"

            execute_with_retry(fn, max_retries=3)

            assert len(received) == 2
            assert received[0]["attempt"] == 1
            assert received[1]["attempt"] == 2
        finally:
            pre_cockroachdb_retry.disconnect(handler)

    @patch("cockroachdb.django.retry.time.sleep")
    def test_post_retry_signal_sent(self, mock_sleep: MagicMock) -> None:
        """post_cockroachdb_retry signal is sent after successful retry."""
        received: list[dict] = []

        def handler(sender: object, attempts: int, **kwargs: object) -> None:
            received.append({"sender": sender, "attempts": attempts})

        post_cockroachdb_retry.connect(handler)
        try:
            call_count = 0

            def fn() -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise FakeSerializationError("conflict")
                return "ok"

            execute_with_retry(fn, max_retries=3)

            assert len(received) == 1
            assert received[0]["attempts"] == 2
        finally:
            post_cockroachdb_retry.disconnect(handler)

    @patch("cockroachdb.django.retry.time.sleep")
    def test_retry_exhausted_signal_sent(self, mock_sleep: MagicMock) -> None:
        """cockroachdb_retry_exhausted signal is sent when retries are used up."""
        received: list[dict] = []

        def handler(sender: object, error: Exception, **kwargs: object) -> None:
            received.append({"sender": sender, "error": error})

        cockroachdb_retry_exhausted.connect(handler)
        try:

            def fn() -> str:
                raise FakeSerializationError("conflict")

            with pytest.raises(CockroachDBRetryExhausted):
                execute_with_retry(fn, max_retries=1)

            assert len(received) == 1
            assert isinstance(received[0]["error"], FakeSerializationError)
        finally:
            cockroachdb_retry_exhausted.disconnect(handler)


class TestAtomicWithRetry:
    """Tests for atomic_with_retry."""

    @patch("cockroachdb.django.retry.transaction")
    @patch("cockroachdb.django.retry.time.sleep")
    def test_decorator_wraps_with_atomic(
        self,
        mock_sleep: MagicMock,
        mock_transaction: MagicMock,
    ) -> None:
        """Decorated function is wrapped in transaction.atomic()."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        @atomic_with_retry()
        def do_work() -> str:
            return "done"

        result = do_work()
        assert result == "done"
        mock_transaction.atomic.assert_called()

    @patch("cockroachdb.django.retry.transaction")
    @patch("cockroachdb.django.retry.time.sleep")
    def test_decorator_retries_on_serialization_error(
        self,
        mock_sleep: MagicMock,
        mock_transaction: MagicMock,
    ) -> None:
        """Decorator retries the entire atomic block on 40001."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        call_count = 0

        @atomic_with_retry(max_retries=3)
        def do_work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FakeSerializationError("conflict")
            return "success"

        result = do_work()
        assert result == "success"
        assert call_count == 3

    @patch("cockroachdb.django.retry.transaction")
    @patch("cockroachdb.django.retry.time.sleep")
    def test_decorator_raises_retry_exhausted(
        self,
        mock_sleep: MagicMock,
        mock_transaction: MagicMock,
    ) -> None:
        """Decorator raises CockroachDBRetryExhausted when retries are used up."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        @atomic_with_retry(max_retries=1)
        def do_work() -> str:
            raise FakeSerializationError("conflict")

        with pytest.raises(CockroachDBRetryExhausted):
            do_work()

    @patch("cockroachdb.django.retry.transaction")
    def test_decorator_does_not_retry_non_retryable(
        self,
        mock_transaction: MagicMock,
    ) -> None:
        """Non-retryable errors pass through without retry."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        @atomic_with_retry()
        def do_work() -> str:
            raise ValueError("bad")

        with pytest.raises(ValueError, match="bad"):
            do_work()

    @patch("cockroachdb.django.retry.transaction")
    @patch("cockroachdb.django.retry.time.sleep")
    def test_decorator_uses_custom_database(
        self,
        mock_sleep: MagicMock,
        mock_transaction: MagicMock,
    ) -> None:
        """The 'using' parameter is forwarded to transaction.atomic()."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        @atomic_with_retry(using="replica")
        def do_work() -> str:
            return "done"

        do_work()
        mock_transaction.atomic.assert_called_with(using="replica")

    @patch("cockroachdb.django.retry.transaction")
    @patch("cockroachdb.django.retry.time.sleep")
    def test_decorator_sends_signals_on_retry(
        self,
        mock_sleep: MagicMock,
        mock_transaction: MagicMock,
    ) -> None:
        """Retry signals are sent from the decorator form."""
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_transaction.atomic.return_value = mock_atomic

        pre_signals: list[int] = []
        post_signals: list[int] = []

        def pre_handler(sender: object, attempt: int, **kwargs: object) -> None:
            pre_signals.append(attempt)

        def post_handler(sender: object, attempts: int, **kwargs: object) -> None:
            post_signals.append(attempts)

        pre_cockroachdb_retry.connect(pre_handler)
        post_cockroachdb_retry.connect(post_handler)

        try:
            call_count = 0

            @atomic_with_retry(max_retries=3)
            def do_work() -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise FakeSerializationError("conflict")
                return "ok"

            do_work()

            assert pre_signals == [1]
            assert post_signals == [2]
        finally:
            pre_cockroachdb_retry.disconnect(pre_handler)
            post_cockroachdb_retry.disconnect(post_handler)
