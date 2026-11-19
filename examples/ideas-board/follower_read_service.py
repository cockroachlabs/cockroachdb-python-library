"""Follower-read leaderboard: read the top ideas AS OF SYSTEM TIME so the query
is served by the nearest replica instead of the leaseholder.

The library's ``build_staleness()`` helper and the ``@follower_read`` decorator
supply the AS OF SYSTEM TIME expression; ``FollowerReadContext`` carries it across
a call. NOTE: the plain-psycopg ``CockroachDBTemplate`` does NOT auto-inject
AS OF SYSTEM TIME (only the SQLAlchemy layer does), so this service applies the
resolved staleness to the SELECT itself — the cooperative pattern for a
psycopg app, exactly how the Java demo threads its staleness through.
"""

from __future__ import annotations

import psycopg
from idea import Idea

# tag::follower-read[]
from cockroachdb import build_staleness, follower_read
from cockroachdb.core import FollowerReadContext


@follower_read("follower_read_timestamp()")
def top_ideas(dsn: str, limit: int = 10) -> list[Idea]:
    """Top ideas by votes, read from a follower snapshot.

    ``@follower_read`` stamps the resolved staleness on this function
    (``__crdb_follower_read__``); we read it back and apply it. The staleness is
    library-controlled (a builtin like ``follower_read_timestamp()`` or an
    interval like ``'-5s'``), never user input, so it is safe to interpolate.
    """
    staleness = getattr(top_ideas, "__crdb_follower_read__", build_staleness())
    sql = (
        "SELECT id, text, votes FROM ideas "
        f"AS OF SYSTEM TIME {staleness} "
        "ORDER BY votes DESC, text ASC LIMIT %s"
    )
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        return [Idea(id=r[0], text=r[1], votes=r[2]) for r in cur.fetchall()]


def top_ideas_scoped(dsn: str, limit: int, *, seconds_ago: int) -> list[Idea]:
    """Same read, but the staleness comes from a ``FollowerReadContext`` block —
    the signal a middleware or template layer would set for the whole request."""
    with FollowerReadContext.scoped(seconds_ago=seconds_ago) as staleness:
        sql = (
            "SELECT id, text, votes FROM ideas "
            f"AS OF SYSTEM TIME {staleness} "
            "ORDER BY votes DESC, text ASC LIMIT %s"
        )
        with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(sql, (limit,))
            return [Idea(id=r[0], text=r[1], votes=r[2]) for r in cur.fetchall()]


# end::follower-read[]
