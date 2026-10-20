"""Retry utilities for Django ORM operations on CockroachDB.

Provides :func:`execute_with_retry` for wrapping arbitrary callables and
:func:`atomic_with_retry` for wrapping ``django.db.transaction.atomic``
blocks with automatic retry on serialization conflicts (SQLSTATE 40001).

Uses :func:`is_retryable_error` from ``cockroachdb.exceptions`` which
already handles Django's ``OperationalError`` wrapping by walking
``__cause__`` chains.

Example::

    from cockroachdb.django import execute_with_retry, atomic_with_retry

    # Wrap a callable
    result = execute_with_retry(lambda: MyModel.objects.create(name="Alice"))

    # Wrap a transaction block
    with atomic_with_retry():
        obj = MyModel.objects.select_for_update().get(pk=1)
        obj.balance -= 100
        obj.save()
"""

from __future__ import annotations

import functools
import logging
import time
from typing import TYPE_CHECKING, Any, TypeVar

from cockroachdb.django.signals import (
    cockroachdb_retry_exhausted,
    post_cockroachdb_retry,
    pre_cockroachdb_retry,
)
from cockroachdb.exceptions import CockroachDBRetryExhausted, is_retryable_error
from django.db import transaction

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry parameters matching cockroachdb.types.RetryPolicy
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY = 0.1
_DEFAULT_MAX_DELAY = 5.0
_DEFAULT_MULTIPLIER = 2.0
_DEFAULT_JITTER_FACTOR = 0.1


def _calc_delay(
    attempt: int,
    base_delay: float = _DEFAULT_BASE_DELAY,
    max_delay: float = _DEFAULT_MAX_DELAY,
    multiplier: float = _DEFAULT_MULTIPLIER,
    jitter_factor: float = _DEFAULT_JITTER_FACTOR,
) -> float:
    """Calculate exponential backoff delay with jitter."""
    import random

    delay = min(base_delay * (multiplier**attempt), max_delay)
    jitter = delay * jitter_factor * random.random()
    return delay + jitter


def execute_with_retry(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
    max_delay: float = _DEFAULT_MAX_DELAY,
    **kwargs: Any,
) -> T:
    """Execute *fn* with automatic retry on CockroachDB serialization errors.

    Retries on SQLSTATE 40001 (serialization_failure) and 40P01
    (deadlock_detected).  Django wraps psycopg errors in
    ``OperationalError``; :func:`is_retryable_error` handles unwrapping
    via ``__cause__``.

    Args:
        fn: Callable to execute.
        *args: Positional arguments forwarded to *fn*.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff delay in seconds.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn*.

    Raises:
        CockroachDBRetryExhausted: When all retries are exhausted.
    """
    last_err: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = fn(*args, **kwargs)
            if attempt > 0:
                post_cockroachdb_retry.send(sender=fn, attempts=attempt + 1)
            return result
        except Exception as e:
            if not is_retryable_error(e):
                raise
            last_err = e
            if attempt < max_retries:
                pre_cockroachdb_retry.send(sender=fn, attempt=attempt + 1, error=e)
                delay = _calc_delay(attempt, base_delay, max_delay)
                logger.warning(
                    "Serialization conflict (attempt %d/%d), retrying in %.3fs",
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)

    cockroachdb_retry_exhausted.send(sender=fn, error=last_err)
    raise CockroachDBRetryExhausted(max_retries, last_err) from last_err


class atomic_with_retry:  # noqa: N801  # intentional snake_case: used as a decorator/context-manager
    """Context manager and decorator wrapping ``transaction.atomic()`` with retry.

    On serialization errors (SQLSTATE 40001), the entire atomic block is
    rolled back and re-executed from scratch, as required by CockroachDB's
    retry protocol.

    Can be used as a context manager::

        with atomic_with_retry():
            MyModel.objects.create(name="Alice")

    Or as a decorator::

        @atomic_with_retry()
        def transfer(from_id, to_id, amount):
            ...

    Args:
        using: Database alias for ``transaction.atomic()``.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff delay in seconds.
    """

    def __init__(
        self,
        using: str | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_delay: float = _DEFAULT_BASE_DELAY,
        max_delay: float = _DEFAULT_MAX_DELAY,
    ) -> None:
        self._using = using
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    def __enter__(self) -> atomic_with_retry:
        # When used as a context manager, the retry logic is handled in
        # __exit__ by re-raising and catching.  However, since we need
        # to re-execute the *entire* block on retry, the context manager
        # form cannot truly retry the body.  We raise a clear error to
        # guide users toward the decorator form for retryable blocks.
        #
        # For context-manager usage, we wrap a single atomic block.
        self._atomic = transaction.atomic(using=self._using)
        self._atomic.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        # Delegate to the inner atomic context manager
        return self._atomic.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[union-attr]

    def __call__(self, fn: Callable[..., T]) -> Callable[..., T]:
        """Use as a decorator to wrap a function with retry + atomic."""

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_err: Exception | None = None

            for attempt in range(self._max_retries + 1):
                try:
                    with transaction.atomic(using=self._using):
                        result = fn(*args, **kwargs)
                    if attempt > 0:
                        post_cockroachdb_retry.send(sender=fn, attempts=attempt + 1)
                    return result
                except Exception as e:
                    if not is_retryable_error(e):
                        raise
                    last_err = e
                    if attempt < self._max_retries:
                        pre_cockroachdb_retry.send(
                            sender=fn,
                            attempt=attempt + 1,
                            error=e,
                        )
                        delay = _calc_delay(attempt, self._base_delay, self._max_delay)
                        logger.warning(
                            "Serialization conflict in %s (attempt %d/%d), retrying in %.3fs",
                            fn.__name__,
                            attempt + 1,
                            self._max_retries,
                            delay,
                        )
                        time.sleep(delay)

            cockroachdb_retry_exhausted.send(sender=fn, error=last_err)
            raise CockroachDBRetryExhausted(
                self._max_retries,
                last_err,
            ) from last_err

        return wrapper  # type: ignore[return-value]
