"""Runnable demo: concurrent upvotes on one hot row, plain vs. @crdb_retry.

Seeds a single idea, then fires N concurrent upvotes through the plain path
(votes get lost to 40001) and the retry path (every vote lands).

Connection:
    - Set CRDB_DSN to point at a running cluster, e.g.
      CRDB_DSN=postgresql://root@localhost:26257/defaultdb
    - Or leave it unset and the demo spins up a throwaway CockroachDB
      container via cockroachdb-testing (requires Docker).

Usage:
    python main.py
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Iterator

import repository
import service


@contextlib.contextmanager
def _dsn() -> Iterator[str]:
    """Yield a psycopg DSN — from CRDB_DSN, or a throwaway container."""
    env = os.environ.get("CRDB_DSN")
    if env:
        yield env
        return
    from crdb_container import insecure_crdb

    with insecure_crdb() as dsn:
        yield dsn


# tag::runner[]
def _hammer(dsn: str, idea_id: int, fn, votes: int) -> int:
    """Fire *votes* concurrent upvotes through *fn*; return the failure count.

    A barrier releases every thread at the same instant so the read-modify-write
    windows overlap and CockroachDB is forced to serialize them.
    """
    barrier = threading.Barrier(votes)
    failures: list[Exception] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            fn(dsn, idea_id)
        except Exception as exc:
            with lock:
                failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(votes)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(failures)


def main() -> None:
    votes = 25
    with _dsn() as dsn, __import__("psycopg").connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            repository.create_schema(cur)
            idea_id = repository.seed(cur, "Add dark mode to the dashboard")

        print(f"Seeded idea #{idea_id}; firing {votes} concurrent upvotes per path.\n")

        # Plain path — no retry. Conflicts raise 40001 and those votes are lost.
        failures = _hammer(dsn, idea_id, service.upvote_without_retry, votes)
        with conn.cursor() as cur:
            plain_total = repository.current_votes(cur, idea_id)
        print(
            f"PLAIN   @crdb_retry OFF : {plain_total}/{votes} votes landed "
            f"({failures} lost to 40001)"
        )

        # Reset, then the retry path — every vote eventually commits.
        with conn.cursor() as cur:
            repository.reset(cur, idea_id)
        failures = _hammer(dsn, idea_id, service.upvote, votes)
        with conn.cursor() as cur:
            retry_total = repository.current_votes(cur, idea_id)
        print(
            f"RETRY   @crdb_retry ON  : {retry_total}/{votes} votes landed ({failures} failures)"
        )


# end::runner[]


if __name__ == "__main__":
    main()
