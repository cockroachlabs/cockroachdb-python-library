"""CockroachDB template pattern for transaction execution with retry and region support."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

import psycopg
from psycopg import sql

from cockroachdb.config import CockroachDBConfig
from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.metrics import NoopMetricsCollector
from cockroachdb.core.region import RegionContext
from cockroachdb.core.retry import RetryEngine
from cockroachdb.core.vcluster import VClusterContext
from cockroachdb.types import (
    IsolationLevel,
    MetricsCollector,
    RetryPolicy,
    TransactionOutcome,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

T = TypeVar("T")

# Fixed, safe SQL templates: only the *value* is parameterized (via sql.Literal),
# the GUC names are constant LiteralStrings.
_SET_APP_NAME = sql.SQL("SET LOCAL application_name = {}")
_SET_QOS = sql.SQL("SET LOCAL default_transaction_quality_of_service = {}")


def _isolation_option(level: IsolationLevel) -> str:
    """libpq ``options`` fragment that sets the transaction isolation.

    The value is backslash-escaped rather than quoted: libpq passes single
    quotes through literally (the server would reject ``'serializable'``) but
    honors a backslash-escaped space, which ``read committed`` requires.
    """
    escaped = level.value.replace(" ", "\\ ")
    return f"-c default_transaction_isolation={escaped}"


def _apply_vcluster(conn: psycopg.Connection) -> None:
    """Apply the active vCluster's session settings to ``conn``'s transaction.

    Issues ``SET LOCAL`` for the application name and quality-of-service so the
    settings are scoped to the current transaction. No-op when no vCluster is
    active, mirroring how follower reads leave untagged transactions untouched.
    """
    settings = VClusterContext.current()
    if settings is None:
        return
    with conn.cursor() as cur:
        cur.execute(_SET_APP_NAME.format(sql.Literal(settings.application_name)))
        cur.execute(_SET_QOS.format(sql.Literal(settings.quality_of_service)))


async def _apply_vcluster_async(conn: psycopg.AsyncConnection) -> None:
    """Async counterpart of :func:`_apply_vcluster`."""
    settings = VClusterContext.current()
    if settings is None:
        return
    async with conn.cursor() as cur:
        await cur.execute(_SET_APP_NAME.format(sql.Literal(settings.application_name)))
        await cur.execute(_SET_QOS.format(sql.Literal(settings.quality_of_service)))


class RegionalTemplate:
    """Region-scoped wrapper around CockroachDBTemplate.

    Sets the region context for all operations executed through this instance.
    """

    def __init__(self, template: CockroachDBTemplate, region: str) -> None:
        self._template = template
        self._region = region

    def execute(self, fn: Callable[[psycopg.Connection], T]) -> T:
        with RegionContext.scoped(self._region):
            return self._template.execute(fn)

    def execute_read_committed(self, fn: Callable[[psycopg.Connection], T]) -> T:
        with RegionContext.scoped(self._region):
            return self._template.execute_read_committed(fn)


class CockroachDBTemplate:
    """Primary entry point for executing CockroachDB transactions.

    Wraps psycopg connections with SERIALIZABLE retry logic, region
    context, follower reads, and metrics collection.
    """

    def __init__(
        self,
        conninfo: str,
        config: CockroachDBConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._conninfo = conninfo
        self._config = config or CockroachDBConfig()
        self._metrics: MetricsCollector = metrics or NoopMetricsCollector()
        self._retry_engine = RetryEngine(
            policy=RetryPolicy(
                max_retries=self._config.retry.max_retries,
                base_delay=self._config.retry.base_delay,
                max_delay=self._config.retry.max_delay,
                multiplier=self._config.retry.multiplier,
                jitter_factor=self._config.retry.jitter_factor,
            ),
            metrics=self._metrics,
        )

    def execute(self, fn: Callable[[psycopg.Connection], T]) -> T:
        """Execute ``fn`` in a SERIALIZABLE transaction with automatic retry."""

        def _attempt() -> T:
            with psycopg.connect(
                self._conninfo,
                autocommit=False,
                options=_isolation_option(IsolationLevel.SERIALIZABLE),
            ) as conn:
                _apply_vcluster(conn)
                result = fn(conn)
                conn.commit()
                return result

        return self._retry_engine.run(_attempt)

    def execute_read_committed(self, fn: Callable[[psycopg.Connection], T]) -> T:
        """Execute ``fn`` in a READ COMMITTED transaction without retry."""
        start = time.monotonic()
        try:
            with psycopg.connect(
                self._conninfo,
                autocommit=False,
                options=_isolation_option(IsolationLevel.READ_COMMITTED),
            ) as conn:
                _apply_vcluster(conn)
                result = fn(conn)
                conn.commit()
                duration_ms = (time.monotonic() - start) * 1000
                self._metrics.record_transaction(TransactionOutcome.COMMITTED, duration_ms)
                return result
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
            raise

    def in_region(self, region: str) -> RegionalTemplate:
        """Return a region-scoped wrapper for this template."""
        return RegionalTemplate(self, region)

    @contextmanager
    def follower_read(
        self,
        staleness: str = "follower_read_timestamp()",
        *,
        hours_ago: int = 0,
        minutes_ago: int = 0,
        seconds_ago: int = 0,
    ) -> Iterator[CockroachDBTemplate]:
        """Context manager that activates follower reads.

        Staleness is additive; see :meth:`FollowerReadContext.scoped`. A
        negative additive part raises ``ValueError``.
        """
        with FollowerReadContext.scoped(
            staleness,
            hours_ago=hours_ago,
            minutes_ago=minutes_ago,
            seconds_ago=seconds_ago,
        ):
            yield self


class AsyncRegionalTemplate:
    """Async region-scoped wrapper around AsyncCockroachDBTemplate."""

    def __init__(self, template: AsyncCockroachDBTemplate, region: str) -> None:
        self._template = template
        self._region = region

    async def execute(self, fn: Callable[[psycopg.AsyncConnection], Awaitable[T]]) -> T:
        with RegionContext.scoped(self._region):
            return await self._template.execute(fn)

    async def execute_read_committed(
        self, fn: Callable[[psycopg.AsyncConnection], Awaitable[T]]
    ) -> T:
        with RegionContext.scoped(self._region):
            return await self._template.execute_read_committed(fn)


class AsyncCockroachDBTemplate:
    """Async equivalent of CockroachDBTemplate using psycopg's AsyncConnection."""

    def __init__(
        self,
        conninfo: str,
        config: CockroachDBConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._conninfo = conninfo
        self._config = config or CockroachDBConfig()
        self._metrics: MetricsCollector = metrics or NoopMetricsCollector()
        self._retry_engine = RetryEngine(
            policy=RetryPolicy(
                max_retries=self._config.retry.max_retries,
                base_delay=self._config.retry.base_delay,
                max_delay=self._config.retry.max_delay,
                multiplier=self._config.retry.multiplier,
                jitter_factor=self._config.retry.jitter_factor,
            ),
            metrics=self._metrics,
        )

    async def execute(self, fn: Callable[[psycopg.AsyncConnection], Awaitable[T]]) -> T:
        """Execute ``fn`` in a SERIALIZABLE async transaction with automatic retry."""

        async def _attempt() -> T:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo,
                autocommit=False,
                options=_isolation_option(IsolationLevel.SERIALIZABLE),
            ) as conn:
                await _apply_vcluster_async(conn)
                result = await fn(conn)
                await conn.commit()
                return result

        return await self._retry_engine.run_async(_attempt)

    async def execute_read_committed(
        self, fn: Callable[[psycopg.AsyncConnection], Awaitable[T]]
    ) -> T:
        """Execute ``fn`` in a READ COMMITTED async transaction without retry."""
        start = time.monotonic()
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo,
                autocommit=False,
                options=_isolation_option(IsolationLevel.READ_COMMITTED),
            ) as conn:
                await _apply_vcluster_async(conn)
                result = await fn(conn)
                await conn.commit()
                duration_ms = (time.monotonic() - start) * 1000
                self._metrics.record_transaction(TransactionOutcome.COMMITTED, duration_ms)
                return result
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            self._metrics.record_transaction(TransactionOutcome.FAILED, duration_ms)
            raise

    def in_region(self, region: str) -> AsyncRegionalTemplate:
        """Return an async region-scoped wrapper for this template."""
        return AsyncRegionalTemplate(self, region)

    @contextmanager
    def follower_read(
        self,
        staleness: str = "follower_read_timestamp()",
        *,
        hours_ago: int = 0,
        minutes_ago: int = 0,
        seconds_ago: int = 0,
    ) -> Iterator[AsyncCockroachDBTemplate]:
        """Context manager that activates follower reads.

        Staleness is additive; see :meth:`FollowerReadContext.scoped`. A
        negative additive part raises ``ValueError``.
        """
        with FollowerReadContext.scoped(
            staleness,
            hours_ago=hours_ago,
            minutes_ago=minutes_ago,
            seconds_ago=seconds_ago,
        ):
            yield self
