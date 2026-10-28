"""CockroachDB-aware SQLAlchemy session wrapper.

Provides :class:`CockroachDBSession` — a high-level facade over
SQLAlchemy's ``Session`` that integrates retry logic, follower reads,
and region-scoped operations out of the box.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy.orm import Session, sessionmaker

from cockroachdb.config import CockroachDBConfig
from cockroachdb.exceptions import CockroachDBRetryExhausted
from cockroachdb.sqla.events import FollowerReadContext, RegionContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

T = TypeVar("T")

# CockroachDB serialization error SQLSTATE
_SERIALIZATION_FAILURE = "40001"


def _is_serialization_error(exc: Exception) -> bool:
    """Return ``True`` if *exc* is a CockroachDB serialization conflict."""
    pgcode = getattr(exc, "pgcode", None) or getattr(getattr(exc, "orig", None), "pgcode", None)
    return pgcode == _SERIALIZATION_FAILURE


def _calc_delay(
    attempt: int,
    base: float,
    cap: float,
    mult: float,
    jitter: float,
) -> float:
    delay = min(base * (mult**attempt), cap)
    return delay + random.uniform(0, delay * jitter)


class RegionalSession:
    """Context-scoped helper that pins operations to a CockroachDB region.

    Intended for use via :meth:`CockroachDBSession.in_region`.

    Example::

        regional = crdb_session.in_region("us-east1")
        result = regional.execute(lambda s: s.execute(text("SELECT 1")))
    """

    def __init__(self, parent: CockroachDBSession, region: str) -> None:
        self._parent = parent
        self._region = region

    def execute(self, fn: Callable[[Session], T]) -> T:
        """Execute *fn* with the region context set.

        Args:
            fn: A callable receiving a SQLAlchemy ``Session``.

        Returns:
            The return value of *fn*.
        """
        token = RegionContext.set(self._region)
        try:
            return self._parent.execute_with_retry(fn)
        finally:
            RegionContext.reset(token)

    def __repr__(self) -> str:
        return f"RegionalSession(region={self._region!r})"


class CockroachDBSession:
    """High-level CockroachDB session with built-in retry and context support.

    Wraps SQLAlchemy's ``sessionmaker`` and provides convenience methods
    for retry-safe transactions, follower reads, and region pinning.

    Args:
        engine: A SQLAlchemy :class:`Engine` (ideally created via
            :func:`cockroachdb.sqla.engine.create_cockroachdb_engine`).
        config: Optional library configuration. Controls retry policy,
            follower-read staleness, and region settings.
    """

    def __init__(
        self,
        engine: Engine,
        config: CockroachDBConfig | None = None,
    ) -> None:
        self._engine = engine
        self._config = config or CockroachDBConfig()
        self._session_factory = sessionmaker(bind=engine)

    # ------------------------------------------------------------------
    # Retry-safe execution
    # ------------------------------------------------------------------

    def execute_with_retry(self, fn: Callable[[Session], T]) -> T:
        """Execute *fn* in a retry loop that handles serialization conflicts.

        Each attempt creates a **fresh** SQLAlchemy ``Session`` so that
        CockroachDB can restart the transaction cleanly.  The retry
        policy (max attempts, backoff, jitter) is read from
        :attr:`_config.retry`.

        Args:
            fn: A callable that receives a ``Session`` and returns a
                result.  The session is committed on success and rolled
                back on failure automatically.

        Returns:
            The return value of *fn* on the first successful attempt.

        Raises:
            CockroachDBRetryExhausted: If all retry attempts fail.
        """
        retry_cfg = self._config.retry
        last_error: Exception | None = None

        for attempt in range(retry_cfg.max_retries + 1):
            session = self._session_factory()
            try:
                result = fn(session)
                session.commit()
                return result
            except Exception as exc:
                session.rollback()
                if not _is_serialization_error(exc):
                    raise
                last_error = exc
                if attempt < retry_cfg.max_retries:
                    delay = _calc_delay(
                        attempt,
                        retry_cfg.base_delay,
                        retry_cfg.max_delay,
                        retry_cfg.multiplier,
                        retry_cfg.jitter_factor,
                    )
                    logger.warning(
                        "Serialization conflict (attempt %d/%d), retrying in %.3fs",
                        attempt + 1,
                        retry_cfg.max_retries,
                        delay,
                    )
                    time.sleep(delay)
            finally:
                session.close()

        raise CockroachDBRetryExhausted(retry_cfg.max_retries, last_error)

    # ------------------------------------------------------------------
    # Follower reads
    # ------------------------------------------------------------------

    def follower_read(
        self,
        fn: Callable[[Session], T],
        *,
        staleness: str = "follower_read_timestamp()",
        hours_ago: int = 0,
        minutes_ago: int = 0,
        seconds_ago: int = 0,
    ) -> T:
        """Execute *fn* as a CockroachDB follower read.

        Activates the :class:`FollowerReadContext` for the block so the
        event listener injects ``SET TRANSACTION AS OF SYSTEM TIME
        {staleness}`` before the query.

        Staleness is additive: ``hours_ago``/``minutes_ago``/``seconds_ago``
        add up and, when positive, compose to ``'-Ns'`` taking precedence
        over *staleness*. With no parts set, *staleness* is used.

        Args:
            fn: A callable that receives a ``Session`` and returns a
                result.  Should perform **read-only** operations.
            staleness: AS OF SYSTEM TIME expression used when no additive
                parts are set.
            hours_ago: Whole hours of staleness to add. Must be >= 0.
            minutes_ago: Whole minutes of staleness to add. Must be >= 0.
            seconds_ago: Whole seconds of staleness to add. Must be >= 0.

        Returns:
            The return value of *fn*.

        Raises:
            ValueError: if any additive part is negative (fail fast — raised
                before any session is opened).
        """
        with FollowerReadContext.scoped(
            staleness,
            hours_ago=hours_ago,
            minutes_ago=minutes_ago,
            seconds_ago=seconds_ago,
        ):
            session = self._session_factory()
            try:
                return fn(session)
            finally:
                session.close()

    # ------------------------------------------------------------------
    # Region-scoped operations
    # ------------------------------------------------------------------

    def in_region(self, region: str) -> RegionalSession:
        """Return a :class:`RegionalSession` pinned to *region*.

        All operations executed through the returned helper will have
        ``SET crdb_region = '<region>'`` injected automatically.

        Args:
            region: CockroachDB region identifier (e.g., ``'us-east1'``).

        Returns:
            A :class:`RegionalSession` bound to this session and region.
        """
        return RegionalSession(self, region)

    def __repr__(self) -> str:
        return f"CockroachDBSession(engine={self._engine.url!r})"
