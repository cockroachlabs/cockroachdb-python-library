"""Integration test — spins up a real CockroachDB via testcontainers.

3 threads x 20 upvotes = 60 total. A per-round barrier forces all three
threads to collide on the same row, so:
    - the plain path loses votes to 40001 (never reaches 60)
    - the @crdb_retry path lands every vote (exactly 60)

Skips cleanly when Docker / testcontainers is unavailable.
"""

from __future__ import annotations

import threading

import pytest

import repository
import service

THREADS = 3
PER_THREAD = 20
TOTAL = THREADS * PER_THREAD


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


def _seed(dsn: str) -> int:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        repository.create_schema(cur)
        return repository.seed(cur, "Concurrent upvote stress test")


def _votes(dsn: str, idea_id: int) -> int:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        return repository.current_votes(cur, idea_id)


def _run(dsn: str, idea_id: int, fn) -> None:
    """3 threads x 20 rounds; a barrier makes all 3 collide each round."""
    barrier = threading.Barrier(THREADS)

    def worker() -> None:
        for _ in range(PER_THREAD):
            barrier.wait()
            try:
                fn(dsn, idea_id)
            except Exception:  # noqa: BLE001 — plain path drops conflicts
                pass

    threads = [threading.Thread(target=worker) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# tag::concurrency-test[]
def test_retry_lands_every_vote(dsn: str) -> None:
    idea_id = _seed(dsn)

    _run(dsn, idea_id, service.upvote)
    assert _votes(dsn, idea_id) == TOTAL  # retry path: all 60 land

    plain_id = _seed(dsn)
    _run(dsn, plain_id, service.upvote_without_retry)
    assert _votes(dsn, plain_id) < TOTAL  # plain path: conflicts lose votes
# end::concurrency-test[]
