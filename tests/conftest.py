"""Shared fixtures for CockroachDB Python Library tests."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Django setup — must happen before any Django module is imported.
# Only runs if Django is installed; harmless to skip otherwise.
# ---------------------------------------------------------------------------
try:
    from conftest_django import configure_django_settings

    configure_django_settings()
except ImportError:
    pass


class FakeRetryableError(Exception):
    """Exception with sqlstate=40001 to simulate CockroachDB serialization failures."""

    sqlstate: str = "40001"

    def __init__(self, message: str = "serialization failure") -> None:
        super().__init__(message)


class FakeRetryableErrorPgcode(Exception):
    """Exception using pgcode attribute instead of sqlstate."""

    pgcode: str = "40001"

    def __init__(self, message: str = "serialization failure via pgcode") -> None:
        super().__init__(message)


class FakeDeadlockError(Exception):
    """Exception simulating a deadlock (SQLSTATE 40P01)."""

    sqlstate: str = "40P01"

    def __init__(self, message: str = "deadlock detected") -> None:
        super().__init__(message)


class FakeNonRetryableError(Exception):
    """A generic non-retryable error with no sqlstate/pgcode."""


class FakeWrappedRetryableError(Exception):
    """An outer exception whose __cause__ is a retryable error."""

    def __init__(self) -> None:
        inner = FakeRetryableError("inner serialization failure")
        super().__init__("wrapper error")
        self.__cause__ = inner


@pytest.fixture
def retryable_error() -> FakeRetryableError:
    return FakeRetryableError()


@pytest.fixture
def retryable_error_pgcode() -> FakeRetryableErrorPgcode:
    return FakeRetryableErrorPgcode()


@pytest.fixture
def deadlock_error() -> FakeDeadlockError:
    return FakeDeadlockError()


@pytest.fixture
def non_retryable_error() -> FakeNonRetryableError:
    return FakeNonRetryableError("some other error")


@pytest.fixture
def wrapped_retryable_error() -> FakeWrappedRetryableError:
    return FakeWrappedRetryableError()
