"""Integration test for follower reads — real CockroachDB via testcontainers.

Seeds three ideas, then reads the leaderboard AS OF SYSTEM TIME
``follower_read_timestamp()`` (~4.8s stale). Because the read is historical,
freshly-seeded rows are invisible until the staleness window advances, so the
test polls until the snapshot catches up (mirrors the Java follower-read IT).

Skips cleanly when Docker / testcontainers is unavailable.
"""

from __future__ import annotations

import time

import psycopg
import pytest
import repository
from follower_read_service import top_ideas


@pytest.fixture(scope="module")
def dsn() -> str:
    try:
        from crdb_container import insecure_crdb
    except Exception as exc:
        pytest.skip(f"testcontainers unavailable: {exc}")
    try:
        with insecure_crdb() as url:
            yield url
    except Exception as exc:
        pytest.skip(f"Docker/CockroachDB container unavailable: {exc}")


def _insert(dsn: str, text: str, votes: int) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO ideas (text, votes) VALUES (%s, %s)", (text, votes))


# tag::follower-read-it[]
def test_top_ideas_from_follower_snapshot(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        repository.create_schema(cur)
    _insert(dsn, "Dark mode", 5)
    _insert(dsn, "Full-text search", 12)
    _insert(dsn, "CSV export", 3)

    # follower_read_timestamp() is ~4.8s stale; poll until the snapshot advances
    # past the freshly-inserted rows.
    deadline = time.monotonic() + 30
    top: list = []
    while time.monotonic() < deadline:
        try:
            top = top_ideas(dsn, 10)
        except psycopg.Error:
            pass  # as-of-time read predates the schema; retry as the window advances
        if len(top) >= 3:
            break
        time.sleep(0.5)

    assert len(top) == 3
    assert top[0].text == "Full-text search"  # highest votes sorts first
    assert top[0].votes == 12
    assert [i.votes for i in top] == sorted((i.votes for i in top), reverse=True)


# end::follower-read-it[]
