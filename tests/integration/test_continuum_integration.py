"""Integration tests for CockroachDB Continuum against a live node.

Isolated on the shared node via a dedicated ``continuum_py`` database so these
never collide with other suites on :26257.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import psycopg
import pytest

from cockroachdb.continuum import Priority, storage_summary, vcluster
from cockroachdb.core import CockroachDBTemplate

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

_ADMIN_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
_CONTINUUM_DB = "continuum_py"
_CONTINUUM_DSN = f"postgresql://root@localhost:26257/{_CONTINUUM_DB}?sslmode=disable"


@pytest.fixture(scope="module")
def continuum_dsn() -> Iterator[str]:
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {_CONTINUUM_DB}")
    yield _CONTINUUM_DSN
    with psycopg.connect(_ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {_CONTINUUM_DB} CASCADE")


def test_vcluster_applies_app_name_and_qos(continuum_dsn: str) -> None:
    template = CockroachDBTemplate(continuum_dsn)

    def _read(conn: psycopg.Connection) -> tuple[str, str]:
        with conn.cursor() as cur:
            cur.execute("SHOW application_name")
            app_row = cur.fetchone()
            cur.execute("SHOW default_transaction_quality_of_service")
            qos_row = cur.fetchone()
        assert app_row is not None and qos_row is not None
        return str(app_row[0]), str(qos_row[0])

    with vcluster("analytics-batch", Priority.LOW):
        app, qos = template.execute(_read)
    assert app == "analytics-batch"
    assert qos == "background"

    # Outside a vCluster, transactions are untagged and use the default QoS.
    app_default, qos_default = template.execute(_read)
    assert app_default != "analytics-batch"
    assert qos_default == "regular"


def test_storage_summary_includes_created_table(continuum_dsn: str) -> None:
    table = f"orders_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(continuum_dsn, autocommit=True) as conn:
        conn.execute(f"CREATE TABLE {table} (id INT PRIMARY KEY, val STRING)")
        conn.execute(f"INSERT INTO {table} (id, val) VALUES (1, 'a'), (2, 'b')")

    try:
        with psycopg.connect(continuum_dsn) as conn:
            summary = storage_summary(conn)
    finally:
        with psycopg.connect(continuum_dsn, autocommit=True) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table}")

    entries = {t.table: t for t in summary}
    assert table in entries
    entry = entries[table]
    assert entry.schema  # e.g. "public"
    # rows/bytes are best-effort: present ⇒ non-negative, otherwise None.
    if entry.rows is not None:
        assert entry.rows >= 0
    if entry.bytes is not None:
        assert entry.bytes >= 0
