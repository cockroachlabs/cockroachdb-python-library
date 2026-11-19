"""Fast unit test — no Docker, no database.

Mocks psycopg so the whole read-modify-write runs in memory, proving
`upvote_without_retry` reads the current vote count and writes count + 1.
"""

from __future__ import annotations

import contextlib

import pytest
import service


class _FakeCursor:
    def __init__(self, store: dict) -> None:
        self._store = store

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self._store.setdefault("executed", []).append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            # params = (new_votes, idea_id)
            self._store["written"] = params[0]

    def fetchone(self) -> tuple:
        return (self._store["votes"],)


class _FakeConnection:
    def __init__(self, store: dict) -> None:
        self._store = store

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        pass  # SET SESSION CHARACTERISTICS — nothing to simulate

    @contextlib.contextmanager
    def transaction(self):
        yield self

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store)


# tag::unit-test[]
def test_upvote_without_retry_reads_then_writes_plus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    store = {"votes": 41}

    def fake_connect(dsn: str, autocommit: bool = False) -> _FakeConnection:
        return _FakeConnection(store)

    monkeypatch.setattr(service.psycopg, "connect", fake_connect)

    service.upvote_without_retry("postgresql://ignored", idea_id=7)

    assert store["written"] == 42  # read 41, wrote 41 + 1


# end::unit-test[]
