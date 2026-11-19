"""Fast unit test for metered upvotes — no Docker, no database.

Simulates a serialization conflict (SQLSTATE 40001) so the REAL ``RetryEngine`` +
``InMemoryMetricsCollector`` count a retry and a RETRIED transaction. The library
classifies retryability off an exception's ``sqlstate``/``pgcode`` (walking the
cause chain), so a stand-in exception with ``sqlstate = "40001"`` exercises the
exact production path without psycopg or a cluster.
"""

from __future__ import annotations

from cockroachdb.core import RetryEngine
from cockroachdb.core.metrics import InMemoryMetricsCollector
from cockroachdb.types import RetryPolicy, TransactionOutcome


class _Fake40001(Exception):
    """Stand-in for psycopg's SerializationFailure (SQLSTATE 40001)."""

    sqlstate = "40001"


# tag::metrics-unit-test[]
def test_retry_engine_counts_retries_and_outcome() -> None:
    metrics = InMemoryMetricsCollector()
    engine = RetryEngine(RetryPolicy(max_retries=5, base_delay=0.0), metrics=metrics)

    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Fake40001("restart transaction")  # retryable
        return "ok"

    assert engine.run(flaky) == "ok"
    assert calls["n"] == 3
    assert metrics.total_retries == 2  # two 40001s absorbed
    assert metrics.transactions[TransactionOutcome.RETRIED]  # retried run recorded
    assert metrics.total_transactions == 1  # one logical transaction
# end::metrics-unit-test[]
