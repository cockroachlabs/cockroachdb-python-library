"""Integration test for the multi-region schema check — gated on a real cluster.

The check reads ``SHOW REGIONS``, ``SHOW DATABASES``, ``SHOW TABLES`` and
``information_schema.columns`` against a live, multi-region CockroachDB database,
so it needs a database that already has regions added (``ALTER DATABASE ... ADD
REGION``). A single node does not. This test therefore SKIPS unless
``CRDB_MULTIREGION=true``; when enabled it reads the cluster from ``CRDB_URL``.

It is never a default-CI failure — it is skipped. Mirrors
``examples/ideas-board/test_regional_it.py``. Runs under the
``examples-it-multiregion`` style cluster or any manually supplied one.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from cockroachdb.core.multiregion import (
    Kind,
    MultiregionCheckError,
    MultiregionTable,
    evaluate,
    load_state,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("CRDB_MULTIREGION") != "true",
    reason="multi-region check IT needs a multi-region cluster; set CRDB_MULTIREGION=true and CRDB_URL",
)


def _query(cur):
    def run(sql: str, params=()):
        cur.execute(sql, params or None)
        return cur.fetchall()

    return run


def test_global_table_annotated_rbr_is_contradiction_live() -> None:
    url = os.environ["CRDB_URL"]
    table = f"mr_check_it_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        try:
            cur.execute(f"CREATE TABLE {table} (id INT PRIMARY KEY)")
            cur.execute(f"ALTER TABLE {table} SET LOCALITY GLOBAL")

            # Declare the entity as REGIONAL BY ROW while the table is GLOBAL:
            # the live schema and the declaration disagree -> contradiction.
            tables = [MultiregionTable(entity="it.Order", table=table, kind=Kind.REGIONAL_BY_ROW)]
            state = load_state(_query(cur), tables)
            assert state.primary_region is not None, "CRDB_URL database is not multi-region"
            report = evaluate(state, tables)
            assert report.has_contradictions(), report.format("warn")
            assert any("SET LOCALITY REGIONAL BY ROW" in s for s in report.statements)
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {table}")


def test_global_table_annotated_global_is_clean_live() -> None:
    url = os.environ["CRDB_URL"]
    table = f"mr_check_it_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        try:
            cur.execute(f"CREATE TABLE {table} (id INT PRIMARY KEY)")
            cur.execute(f"ALTER TABLE {table} SET LOCALITY GLOBAL")
            tables = [MultiregionTable(entity="it.Product", table=table, kind=Kind.GLOBAL)]
            report = evaluate(load_state(_query(cur), tables), tables)
            assert report.is_empty(), report.format("warn")
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {table}")


def test_sqla_verify_raises_on_contradiction_live() -> None:
    from sqlalchemy import Column, Integer
    from sqlalchemy.orm import DeclarativeBase

    from cockroachdb.sqla import create_cockroachdb_engine, verify_multiregion_schema
    from cockroachdb.sqla.mixins import RegionalByRowMixin

    url = os.environ["CRDB_URL"]
    table = f"mr_check_it_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id INT PRIMARY KEY)")
        cur.execute(f"ALTER TABLE {table} SET LOCALITY GLOBAL")

    sqla_url = url.replace("postgresql://", "cockroachdb://").replace(
        "postgres://", "cockroachdb://"
    )
    try:
        engine = create_cockroachdb_engine(sqla_url)

        class Base(DeclarativeBase):
            pass

        class Order(RegionalByRowMixin, Base):
            __tablename__ = table
            id = Column(Integer, primary_key=True)

        with pytest.raises(MultiregionCheckError):
            verify_multiregion_schema(engine, Base, mode="warn")
    finally:
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
