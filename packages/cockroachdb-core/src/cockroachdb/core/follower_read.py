"""Follower read context for CockroachDB bounded-staleness reads."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_follower_read_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cockroachdb_follower_read", default=None
)


class FollowerReadContext:
    """Thread-safe follower read context backed by contextvars.

    When active, the template layer prepends ``AS OF SYSTEM TIME``
    to read queries using the configured staleness expression.
    """

    @classmethod
    def is_active(cls) -> bool:
        return _follower_read_var.get() is not None

    @classmethod
    def current_staleness(cls) -> str | None:
        return _follower_read_var.get()

    @classmethod
    @contextmanager
    def scoped(cls, staleness: str = "follower_read_timestamp()") -> Iterator[str]:
        """Context manager that activates follower reads for the block duration."""
        token = _follower_read_var.set(staleness)
        try:
            yield staleness
        finally:
            _follower_read_var.reset(token)
