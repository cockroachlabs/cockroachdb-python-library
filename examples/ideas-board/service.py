"""Upvote service: the plain path loses votes, the @crdb_retry path lands them all.

Both functions perform the SAME read-modify-write against a single hot row
under SERIALIZABLE isolation, so CockroachDB raises a serialization conflict
(SQLSTATE 40001) when concurrent upvotes collide. The only difference is the
decorator.
"""

from __future__ import annotations

import time

import psycopg

import repository

# tag::retry[]
from cockroachdb import IsolationLevel, crdb_retry

# end::retry[]

# Pause between the read and the write to widen the conflict window so
# concurrent upvotes reliably collide. ponytail: fixed delay, tune per cluster.
CONTENTION_DELAY = 0.05


def _apply_upvote(dsn: str, idea_id: int) -> None:
    """Read current votes, add one, write it back — in one SERIALIZABLE tx.

    Opens its OWN connection every call. @crdb_retry re-executes the whole
    decorated function on a 40001, and CockroachDB's retry protocol requires
    a brand-new transaction each attempt, so the connection must be created
    inside the retried unit — not passed in.
    """
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE"
        )
        with conn.transaction(), conn.cursor() as cur:
            votes = repository.current_votes(cur, idea_id)
            time.sleep(CONTENTION_DELAY)
            repository.update_votes(cur, idea_id, votes + 1)


# tag::plain[]
def upvote_without_retry(dsn: str, idea_id: int) -> None:
    """Upvote with NO retry — a 40001 propagates and that vote is lost."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE"
        )
        with conn.transaction(), conn.cursor() as cur:
            votes = repository.current_votes(cur, idea_id)  # <1>
            new_votes = votes + 1  # <2>
            repository.update_votes(cur, idea_id, new_votes)  # <3>
# end::plain[]


# tag::retry[]
@crdb_retry(max_retries=25, base_delay=0.02, isolation=IsolationLevel.SERIALIZABLE)  # <1>
def upvote(dsn: str, idea_id: int) -> None:
    """Upvote WITH automatic retry — every vote eventually lands."""
    _apply_upvote(dsn, idea_id)
# end::retry[]
