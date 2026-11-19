"""Integration test for metrics — spins up a real CockroachDB via testcontainers.

4 workers x 10 upvotes = 40 total on one hot row. A per-round barrier forces
collisions, so the metered path records exactly 40 transactions and a non-zero
retry count (real 40001s absorbed by the engine).

Skips cleanly when Docker / testcontainers is unavailable.
"""

from __future__ import annotations

import threading

import psycopg
import pytest

import repository
from metrics_service import MeteredIdeaService

WORKERS = 4
ITERATIONS = 10
EXPECTED = WORKERS * ITERATIONS


@pytest.fixture(scope="module")
def dsn() -> str:
    try:
        from crdb_container import insecure_crdb
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"testcontainers unavailable: {exc}")
    try:
        with insecure_crdb() as url:
            yield url
    except Exception as exc:  # noqa: BLE001 — Docker not running / image pull failed
        pytest.skip(f"Docker/CockroachDB container unavailable: {exc}")


# tag::metrics-it[]
def test_metrics_count_transactions_and_retries(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        repository.create_schema(cur)
        idea_id = repository.seed(cur, "Instrument the ideas board")

    service = MeteredIdeaService(dsn)
    barrier = threading.Barrier(WORKERS)

    def worker() -> None:
        for _ in range(ITERATIONS):
            barrier.wait()
            service.upvote(idea_id)

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        assert repository.current_votes(cur, idea_id) == EXPECTED  # retry absorbs conflicts

    assert service.metrics.total_transactions == EXPECTED  # one per metered upvote
    assert service.metrics.total_retries > 0  # contention forces 40001 retries
# end::metrics-it[]
