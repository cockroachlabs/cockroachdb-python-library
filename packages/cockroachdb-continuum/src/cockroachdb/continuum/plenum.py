"""Cockroach Plenum — storage insights over customer-safe SQL surfaces.

:func:`storage_summary` reports per-table row estimates and approximate on-disk
size using only customer-safe surfaces: ``SHOW TABLES`` (for
``estimated_row_count``) and ``SHOW RANGES FROM DATABASE ... WITH TABLES, DETAILS``
(for ``range_size``). It never touches ``crdb_internal`` (restricted in v26.2).

Every query is best-effort and version-tolerant: if a column or surface is
unavailable on the running cluster, the corresponding field degrades to ``None``
rather than raising, so a partial summary is always returned.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psycopg


@dataclass(frozen=True)
class TableStorage:
    """Approximate storage footprint of a single table.

    ``rows`` and ``bytes`` are best-effort estimates and are ``None`` when the
    running cluster does not expose them.
    """

    schema: str
    table: str
    rows: int | None
    bytes: int | None


def _safe_fetch(conn: psycopg.Connection, query: str) -> list[tuple[Any, ...]] | None:
    """Run ``query`` returning rows, or ``None`` if it is unavailable.

    On failure the connection is rolled back so the caller's connection stays
    usable for the remaining best-effort queries.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()
    except Exception:
        with contextlib.suppress(Exception):
            conn.rollback()
        return None


def _as_non_negative_int(value: Any) -> int | None:
    """Coerce a numeric cell to a non-negative int, or ``None`` when unusable."""
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _quote_ident(name: str) -> str:
    """Quote a SQL identifier, escaping embedded double-quotes."""
    return '"' + name.replace('"', '""') + '"'


def _current_database(conn: psycopg.Connection) -> str:
    rows = _safe_fetch(conn, "SELECT current_database()")
    if rows and rows[0] and rows[0][0]:
        return str(rows[0][0])
    return "defaultdb"


def _table_bytes(conn: psycopg.Connection, database: str) -> dict[tuple[str, str], int]:
    """Best-effort per-table byte sizes from ``SHOW RANGES``; empty on old clusters."""
    query = (
        "SELECT schema_name, table_name, sum(range_size)::INT8 AS bytes "
        f"FROM [SHOW RANGES FROM DATABASE {_quote_ident(database)} WITH TABLES, DETAILS] "
        "GROUP BY schema_name, table_name"
    )
    rows = _safe_fetch(conn, query)
    if rows is None:
        return {}
    sizes: dict[tuple[str, str], int] = {}
    for row in rows:
        size = _as_non_negative_int(row[2])
        if size is not None:
            sizes[(str(row[0]), str(row[1]))] = size
    return sizes


def storage_summary(conn: psycopg.Connection) -> list[TableStorage]:
    """Return the storage footprint of every table in the current database.

    Uses only customer-safe surfaces and never raises for missing columns: a
    table always appears, with ``rows``/``bytes`` set to ``None`` when the
    cluster does not expose the estimate.
    """
    database = _current_database(conn)
    byte_map = _table_bytes(conn, database)

    rich_query = (
        "SELECT schema_name, table_name, estimated_row_count "
        f"FROM [SHOW TABLES FROM {_quote_ident(database)}] WHERE type = 'table'"
    )
    rich = _safe_fetch(conn, rich_query)
    if rich is not None:
        return [
            TableStorage(
                schema=str(row[0]),
                table=str(row[1]),
                rows=_as_non_negative_int(row[2]),
                bytes=byte_map.get((str(row[0]), str(row[1]))),
            )
            for row in rich
        ]

    # Older cluster without estimated_row_count / type filter: table list only.
    basic_query = (
        f"SELECT schema_name, table_name FROM [SHOW TABLES FROM {_quote_ident(database)}]"
    )
    basic = _safe_fetch(conn, basic_query) or []
    return [
        TableStorage(
            schema=str(row[0]),
            table=str(row[1]),
            rows=None,
            bytes=byte_map.get((str(row[0]), str(row[1]))),
        )
        for row in basic
    ]
