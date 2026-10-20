"""Testing utilities example.

Demonstrates the ``cockroachdb-testing`` package for testing
CockroachDB-aware applications without a live database:
    - ``RetrySimulator`` for deterministic retry testing
    - ``FakeSerializationError`` for simulating SQLSTATE 40001
    - ``ChangefeedEventFactory`` for building CDC test data
    - ``VectorSearchResultFactory`` for building search results
    - ``ConcurrencyRunner`` for concurrent operation testing

Prerequisites:
    pip install cockroachdb cockroachdb-testing

Usage:
    python examples/testing_demo.py
"""

from __future__ import annotations

import asyncio

from cockroachdb import DistanceMetric, crdb_retry
from cockroachdb.testing import (
    ChangefeedEventFactory,
    ConcurrencyResult,
    ConcurrencyRunner,
    FakeSerializationError,
    RetrySimulator,
    VectorSearchResultFactory,
)
from cockroachdb.types import CDCOperation

# ---------------------------------------------------------------------------
# 1. RetrySimulator — test retry logic deterministically
# ---------------------------------------------------------------------------


def demonstrate_retry_simulator() -> None:
    """Test that @crdb_retry handles transient failures correctly.

    ``RetrySimulator`` raises ``FakeSerializationError`` (which has
    pgcode='40001') for the first N invocations, then delegates to
    the real callable. This lets you verify retry behavior without
    a database.
    """
    print("--- RetrySimulator ---")

    # Simulate 3 failures before success
    sim = RetrySimulator(fail_count=3)

    @crdb_retry(max_retries=5)
    def do_work() -> str:
        return sim.execute(lambda: "operation complete")

    result = do_work()
    print(f"  Result: {result}")

    # Verify retry behavior
    sim.assert_retried(expected_attempts=4)  # 3 failures + 1 success
    print(f"  Call count: {sim.call_count}")
    print("  All calls succeeded after retries: True")
    print()


# ---------------------------------------------------------------------------
# 2. FakeSerializationError — standalone use
# ---------------------------------------------------------------------------


def demonstrate_fake_error() -> None:
    """Use FakeSerializationError directly for fine-grained testing.

    The error has ``pgcode`` and ``sqlstate`` attributes set to '40001',
    making it compatible with the retry decorator's error detection.
    """
    print("--- FakeSerializationError ---")

    err = FakeSerializationError("simulated conflict")
    print(f"  Message: {err}")
    print(f"  pgcode: {err.pgcode}")
    print(f"  sqlstate: {err.sqlstate}")

    # Verify it triggers retry detection
    from cockroachdb.exceptions import is_retryable_error

    print(f"  is_retryable_error(): {is_retryable_error(err)}")
    print()


# ---------------------------------------------------------------------------
# 3. ChangefeedEventFactory — build CDC test data
# ---------------------------------------------------------------------------


def demonstrate_changefeed_factory() -> None:
    """Build realistic CDC events for testing handlers.

    ``ChangefeedEventFactory.build()`` creates events with sensible
    defaults. Override any field to test specific scenarios.
    """
    print("--- ChangefeedEventFactory ---")

    # Default event (INSERT on test_table)
    event = ChangefeedEventFactory.build()
    print(f"  Default event: table={event.table}, op={event.operation}")

    # Custom INSERT event
    insert_event = ChangefeedEventFactory.build(
        table="orders",
        operation=CDCOperation.INSERT,
        after={"id": 42, "customer": "Alice", "total": 99.99},
    )
    print(f"  Insert event: table={insert_event.table}, after={insert_event.after}")

    # UPDATE event with before/after
    update_event = ChangefeedEventFactory.build(
        table="orders",
        operation=CDCOperation.UPDATE,
        before={"id": 42, "status": "pending"},
        after={"id": 42, "status": "shipped"},
    )
    print(
        f"  Update event: before_status={update_event.before['status']}, "
        f"after_status={update_event.after['status']}"
    )

    # DELETE event
    delete_event = ChangefeedEventFactory.build(
        table="orders",
        operation=CDCOperation.DELETE,
        before={"id": 42, "customer": "Alice"},
    )
    print(f"  Delete event: before={delete_event.before}")

    # Build with custom metadata
    event_with_meta = ChangefeedEventFactory.build(
        table="audit_log",
        metadata={"source": "cdc", "partition": 3},
    )
    print(f"  With metadata: {event_with_meta.metadata}")
    print()


# ---------------------------------------------------------------------------
# 4. VectorSearchResultFactory — build search results for testing
# ---------------------------------------------------------------------------


def demonstrate_vector_factory() -> None:
    """Build vector search results for testing search logic.

    ``VectorSearchResultFactory.build()`` creates result objects with
    realistic distance/similarity values. Pass a ``metric`` to compute
    similarity correctly for your distance metric.
    """
    print("--- VectorSearchResultFactory ---")

    # Default result (cosine, distance=0.25)
    result = VectorSearchResultFactory.build()
    print(
        f"  Default: id={result.id}, distance={result.distance}, "
        f"similarity={result.similarity:.4f}"
    )

    # Custom cosine result
    cosine_result = VectorSearchResultFactory.build(
        distance=0.15,
        document={"text": "CockroachDB is a distributed SQL database"},
        metric=DistanceMetric.COSINE,
    )
    print(
        f"  Cosine: distance={cosine_result.distance}, similarity={cosine_result.similarity:.4f}"
    )

    # L2 distance result
    l2_result = VectorSearchResultFactory.build(
        distance=1.5,
        metric=DistanceMetric.EUCLIDEAN,
    )
    print(f"  L2: distance={l2_result.distance}, similarity={l2_result.similarity:.4f}")

    # Inner product result
    ip_result = VectorSearchResultFactory.build(
        distance=-0.85,
        metric=DistanceMetric.INNER_PRODUCT,
    )
    print(f"  Inner product: distance={ip_result.distance}, similarity={ip_result.similarity:.4f}")

    # Build a batch for testing ranked results
    results = [
        VectorSearchResultFactory.build(distance=d, metric=DistanceMetric.COSINE)
        for d in [0.05, 0.12, 0.25, 0.40, 0.65]
    ]
    print(f"  Batch of {len(results)} results:")
    for r in results:
        print(f"    distance={r.distance:.2f}, similarity={r.similarity:.4f}")
    print()


# ---------------------------------------------------------------------------
# 5. ConcurrencyRunner — test concurrent operations
# ---------------------------------------------------------------------------


def demonstrate_concurrency_runner() -> None:
    """Test that operations handle concurrent access correctly.

    ``ConcurrencyRunner`` executes a callable across multiple threads
    and collects aggregate results — success count, failure count,
    error list, duration, and throughput.
    """
    print("--- ConcurrencyRunner (sync) ---")

    counter = {"value": 0}

    def increment():
        counter["value"] += 1

    runner = ConcurrencyRunner(threads=4, iterations=100)
    result: ConcurrencyResult = runner.run(increment)

    print(f"  Total iterations: {result.total_count}")
    print(f"  Successes: {result.success_count}")
    print(f"  Failures: {result.failure_count}")
    print(f"  Failure rate: {result.failure_rate:.2%}")
    print(f"  Duration: {result.total_duration:.3f}s")
    print(f"  Throughput: {result.throughput:.0f} ops/sec")
    print(f"  Final counter: {counter['value']}")
    print()


async def demonstrate_async_concurrency() -> None:
    """Test async operations with ConcurrencyRunner.

    ``run_async`` creates async tasks for concurrent execution,
    suitable for testing async database operations.
    """
    print("--- ConcurrencyRunner (async) ---")

    counter = {"value": 0}

    async def async_increment():
        counter["value"] += 1

    runner = ConcurrencyRunner(threads=1, iterations=50)
    result: ConcurrencyResult = await runner.run_async(async_increment)

    print(f"  Total iterations: {result.total_count}")
    print(f"  Successes: {result.success_count}")
    print(f"  Failures: {result.failure_count}")
    print(f"  Duration: {result.total_duration:.3f}s")
    print(f"  Throughput: {result.throughput:.0f} ops/sec")
    print()


# ---------------------------------------------------------------------------
# 6. Combining tools: retry under concurrency
# ---------------------------------------------------------------------------


def demonstrate_retry_under_concurrency() -> None:
    """Test retry behavior under concurrent load.

    Combine RetrySimulator with ConcurrencyRunner to verify that
    retries work correctly when multiple threads hit serialization
    conflicts simultaneously.
    """
    print("--- Retry under concurrency ---")

    # Each thread gets its own simulator
    import threading

    local = threading.local()

    def get_simulator() -> RetrySimulator:
        if not hasattr(local, "sim"):
            local.sim = RetrySimulator(fail_count=2)
        return local.sim

    @crdb_retry(max_retries=5)
    def concurrent_operation() -> str:
        sim = get_simulator()
        return sim.execute(lambda: "ok")

    runner = ConcurrencyRunner(threads=4, iterations=20)
    result = runner.run(concurrent_operation)

    print(
        f"  Concurrent retries — successes: {result.success_count}, "
        f"failures: {result.failure_count}"
    )
    print(f"  Throughput: {result.throughput:.0f} ops/sec")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB Testing Utilities Examples ===\n")

    demonstrate_retry_simulator()
    demonstrate_fake_error()
    demonstrate_changefeed_factory()
    demonstrate_vector_factory()
    demonstrate_concurrency_runner()
    asyncio.run(demonstrate_async_concurrency())
    demonstrate_retry_under_concurrency()

    print("Done.")
