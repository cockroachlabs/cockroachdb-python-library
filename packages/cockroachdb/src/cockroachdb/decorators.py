"""Decorators for CockroachDB operations.

These decorators provide the primary developer-facing API, mapping to
Java's @CockroachDB/@FollowerRead annotations and .NET's [CockroachDB]
/[FollowerRead] attributes.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
import time
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from cockroachdb.exceptions import CockroachDBRetryExhausted, is_retryable_error
from cockroachdb.staleness import build_staleness
from cockroachdb.types import IsolationLevel

if TYPE_CHECKING:
    from collections.abc import Callable

P = ParamSpec("P")
T = TypeVar("T")


def crdb_retry(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 5.0,
    multiplier: float = 2.0,
    jitter_factor: float = 0.1,
    isolation: IsolationLevel = IsolationLevel.SERIALIZABLE,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry on CockroachDB serialization errors (SQLSTATE 40001).

    Supports both sync and async functions. Each retry executes the
    entire decorated function, creating a fresh transaction as required
    by CockroachDB's retry protocol.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds before first retry.
        max_delay: Maximum delay cap in seconds.
        multiplier: Exponential backoff multiplier.
        jitter_factor: Random jitter as fraction of delay (0.0 to 1.0).
        isolation: Transaction isolation level.
        on_retry: Optional callback invoked on each retry with (attempt, error).
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                last_err: Exception | None = None
                for attempt in range(max_retries + 1):
                    try:
                        return await fn(*args, **kwargs)  # type: ignore[no-any-return]
                    except Exception as e:
                        if not is_retryable_error(e):
                            raise
                        last_err = e
                        if attempt < max_retries:
                            if on_retry:
                                on_retry(attempt + 1, e)
                            delay = _calc_delay(
                                attempt, base_delay, max_delay, multiplier, jitter_factor
                            )
                            await asyncio.sleep(delay)
                raise CockroachDBRetryExhausted(max_retries, last_err) from last_err

            async_wrapper.__crdb_retry__ = True  # type: ignore[attr-defined]
            async_wrapper.__crdb_isolation__ = isolation  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_err: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if not is_retryable_error(e):
                        raise
                    last_err = e
                    if attempt < max_retries:
                        if on_retry:
                            on_retry(attempt + 1, e)
                        delay = _calc_delay(
                            attempt, base_delay, max_delay, multiplier, jitter_factor
                        )
                        time.sleep(delay)
            raise CockroachDBRetryExhausted(max_retries, last_err) from last_err

        sync_wrapper.__crdb_retry__ = True  # type: ignore[attr-defined]
        sync_wrapper.__crdb_isolation__ = isolation  # type: ignore[attr-defined]
        return sync_wrapper

    return decorator


def follower_read(
    staleness: str = "follower_read_timestamp()",
    *,
    hours_ago: int = 0,
    minutes_ago: int = 0,
    seconds_ago: int = 0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Execute read queries AS OF SYSTEM TIME for low-latency replica reads.

    Always performs a follower read — there is no fallback to a current read.

    Staleness is additive: ``hours_ago``/``minutes_ago``/``seconds_ago`` add up
    and, when their total is positive, compose to ``'-Ns'`` which takes
    precedence over *staleness*. With no parts set, *staleness* is used (a
    built-in like ``follower_read_timestamp()`` or an interval like ``'-5s'``).

    Args:
        staleness: AS OF SYSTEM TIME expression used when no additive parts set.
        hours_ago: Whole hours of staleness to add. Must be >= 0.
        minutes_ago: Whole minutes of staleness to add. Must be >= 0.
        seconds_ago: Whole seconds of staleness to add. Must be >= 0.

    Raises:
        ValueError: if any additive part is negative (raised at decoration
            time — fail fast rather than silently read current data).
    """
    resolved = build_staleness(
        staleness,
        hours_ago=hours_ago,
        minutes_ago=minutes_ago,
        seconds_ago=seconds_ago,
    )

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        fn.__crdb_follower_read__ = resolved  # type: ignore[attr-defined]
        return fn

    return decorator


def crdb_region(region: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Pin execution to a specific CockroachDB region.

    The region is set via SET crdb_region before the operation executes,
    and propagated through contextvars.

    Args:
        region: CockroachDB region identifier (e.g., 'us-east1').
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        fn.__crdb_region__ = region  # type: ignore[attr-defined]
        return fn

    return decorator


def regional_by_row(
    default_region: str | None = None,
) -> Callable[[type[T]], type[T]]:
    """Mark an entity class as REGIONAL BY ROW.

    Equivalent to Java's @RegionalByRow and .NET's [RegionalByRow].

    Args:
        default_region: Default region for new rows.
    """

    def decorator(cls: type[T]) -> type[T]:
        cls.__crdb_regional_by_row__ = True  # type: ignore[attr-defined]
        cls.__crdb_default_region__ = default_region  # type: ignore[attr-defined]
        return cls

    return decorator


def global_table(cls: type[T]) -> type[T]:
    """Mark an entity class as a GLOBAL table (replicated across all regions).

    Equivalent to Java's @GlobalTable and .NET's [GlobalTable].
    """
    cls.__crdb_global_table__ = True  # type: ignore[attr-defined]
    return cls


def changefeed_handler(
    table: str,
    operations: list[str] | None = None,
    endpoint: str | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Register a function as a CDC changefeed webhook handler.

    Args:
        table: The CockroachDB table to watch.
        operations: List of operations to handle ('insert', 'update', 'delete').
        endpoint: Custom webhook endpoint path.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        fn.__crdb_changefeed__ = {  # type: ignore[attr-defined]
            "table": table,
            "operations": operations or ["insert", "update", "delete"],
            "endpoint": endpoint or f"/webhooks/{table}",
        }
        return fn

    return decorator


def vector_search(
    table: str,
    vector_column: str,
    metric: str = "cosine",
    limit: int = 10,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function as a vector similarity search operation.

    The decorated function's first positional argument (after self) should be
    the query vector (list[float]).

    Args:
        table: Table containing vector data.
        vector_column: Column storing vector embeddings.
        metric: Distance metric ('cosine', 'l2', 'inner_product').
        limit: Maximum number of results.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        fn.__crdb_vector_search__ = {  # type: ignore[attr-defined]
            "table": table,
            "vector_column": vector_column,
            "metric": metric,
            "limit": limit,
        }
        return fn

    return decorator


def semantic_search(
    table: str,
    vector_column: str,
    text_column: str,
    metric: str = "cosine",
    limit: int = 10,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Mark a function as a hybrid semantic search (vector + text filter).

    Args:
        table: Table containing vector and text data.
        vector_column: Column storing vector embeddings.
        text_column: Column containing searchable text.
        metric: Distance metric.
        limit: Maximum number of results.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        fn.__crdb_semantic_search__ = {  # type: ignore[attr-defined]
            "table": table,
            "vector_column": vector_column,
            "text_column": text_column,
            "metric": metric,
            "limit": limit,
        }
        return fn

    return decorator


def _calc_delay(
    attempt: int,
    base: float,
    cap: float,
    mult: float,
    jitter: float,
) -> float:
    delay = min(base * (mult**attempt), cap)
    return delay + random.uniform(0, delay * jitter)
