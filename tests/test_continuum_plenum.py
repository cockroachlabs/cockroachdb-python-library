"""Unit tests for Cockroach Plenum storage-summary version tolerance.

These use a fake connection so the version-tolerance logic can be exercised
without a live cluster (see the integration suite for the real query paths).
"""

from __future__ import annotations

from typing import Any

from cockroachdb.continuum import TableStorage, storage_summary


class _FakeCursor:
    def __init__(self, responder: Any) -> None:
        self._responder = responder
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: object) -> None:
        self._rows = self._responder(str(query))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeConn:
    def __init__(self, responder: Any) -> None:
        self._responder = responder
        self.rollbacks = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._responder)

    def rollback(self) -> None:
        self.rollbacks += 1


def _modern_responder(query: str) -> list[tuple[Any, ...]]:
    if "current_database" in query:
        return [("continuum_py",)]
    if "SHOW RANGES" in query:
        return [("public", "orders", 4096)]
    if "estimated_row_count" in query:
        return [("public", "orders", 12)]
    raise AssertionError(f"unexpected query: {query}")


def _legacy_responder(query: str) -> list[tuple[Any, ...]]:
    if "current_database" in query:
        return [("continuum_py",)]
    if "SHOW RANGES" in query:
        raise RuntimeError("SHOW RANGES ... WITH DETAILS unsupported")
    if "estimated_row_count" in query:
        raise RuntimeError("estimated_row_count column missing")
    if "SHOW TABLES" in query:  # basic fallback
        return [("public", "orders")]
    raise AssertionError(f"unexpected query: {query}")


def test_modern_cluster_reports_rows_and_bytes() -> None:
    conn = _FakeConn(_modern_responder)
    summary = storage_summary(conn)  # type: ignore[arg-type]
    assert summary == [TableStorage(schema="public", table="orders", rows=12, bytes=4096)]


def test_legacy_cluster_degrades_to_none_without_raising() -> None:
    conn = _FakeConn(_legacy_responder)
    summary = storage_summary(conn)  # type: ignore[arg-type]
    assert summary == [TableStorage(schema="public", table="orders", rows=None, bytes=None)]
    # Failed best-effort queries roll back to keep the connection usable.
    assert conn.rollbacks >= 1


def test_negative_row_counts_coerced_to_none() -> None:
    def responder(query: str) -> list[tuple[Any, ...]]:
        if "current_database" in query:
            return [("continuum_py",)]
        if "SHOW RANGES" in query:
            return []
        if "estimated_row_count" in query:
            return [("public", "t", -1)]
        raise AssertionError(query)

    summary = storage_summary(_FakeConn(responder))  # type: ignore[arg-type]
    assert summary[0].rows is None
    assert summary[0].bytes is None
