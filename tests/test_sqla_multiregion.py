"""Tests for cockroachdb.sqla.multiregion — verify_multiregion_schema."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer
from sqlalchemy.orm import DeclarativeBase

from cockroachdb.core.multiregion import Kind, MultiregionCheckError
from cockroachdb.sqla.mixins import GlobalTableMixin, RegionalByRowMixin
from cockroachdb.sqla.multiregion import _tables_from_base, verify_multiregion_schema


def _make_base():
    class Base(DeclarativeBase):
        pass

    class Order(RegionalByRowMixin, Base):
        __tablename__ = "orders"
        id = Column(Integer, primary_key=True)

    class Product(GlobalTableMixin, Base):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True)

    class Plain(Base):
        __tablename__ = "plain"
        id = Column(Integer, primary_key=True)

    return Base, Order, Product, Plain


class _FakeConn:
    def __init__(self, routes):
        self._routes = routes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exec_driver_sql(self, sql, params=None):
        for needle, rows in self._routes:
            if needle in sql:
                return list(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def __init__(self, routes):
        self._routes = routes

    def connect(self):
        return _FakeConn(self._routes)


def _routes(*, orders_locality, primary="us-east1"):
    return [
        ("version()", [("CockroachDB CCL v25.1",)]),
        ("current_database()", [("defaultdb", "public")]),
        ("SHOW DATABASES", [(primary,)] if primary else []),
        ("SHOW REGIONS FROM CLUSTER", [("us-east1",), ("us-west1",)]),
        ("pg_get_keywords", []),
        (
            "SHOW TABLES",
            [
                ("public", "orders", orders_locality),
                ("public", "products", "GLOBAL"),
                ("public", "plain", "REGIONAL BY TABLE IN PRIMARY REGION"),
            ],
        ),
        ("information_schema.columns", [("crdb_region", "crdb_internal_region")]),
    ]


class TestEnumeration:
    def test_tables_from_base_reads_mixin_locality(self):
        base, *_ = _make_base()
        by_table = {t.table: t for t in _tables_from_base(base)}
        assert by_table["orders"].kind is Kind.REGIONAL_BY_ROW
        assert by_table["orders"].region_column == "crdb_region"
        assert by_table["products"].kind is Kind.GLOBAL
        assert by_table["plain"].kind is Kind.NONE


class TestVerify:
    def test_none_mode_does_not_touch_engine(self):
        base, *_ = _make_base()

        class Boom:
            def connect(self):  # pragma: no cover - must not be called
                raise AssertionError("engine used in none mode")

        verify_multiregion_schema(Boom(), base, mode="none")

    def test_contradiction_raises_even_in_warn(self):
        # orders is annotated REGIONAL BY ROW but the table is GLOBAL -> contradiction.
        base, *_ = _make_base()
        engine = _FakeEngine(_routes(orders_locality="GLOBAL"))
        with pytest.raises(MultiregionCheckError) as exc:
            verify_multiregion_schema(engine, base, mode="warn")
        assert "Contradiction" in str(exc.value)

    def test_clean_schema_does_not_raise(self):
        base, *_ = _make_base()
        engine = _FakeEngine(_routes(orders_locality="REGIONAL BY ROW"))
        # products GLOBAL matches, orders RBR matches, plain unannotated+non-MR-locality is fine.
        verify_multiregion_schema(engine, base, mode="warn")

    def test_validate_raises_on_plain_problem(self, caplog):
        # Make products mismatch (GLOBAL entity, table reports RBR) -> plain problem,
        # which must raise only in validate mode.
        base, *_ = _make_base()
        routes = _routes(orders_locality="REGIONAL BY ROW")
        routes = [
            (n, [("public", "orders", "REGIONAL BY ROW"), ("public", "products", "GLOBAL")])
            if n == "SHOW TABLES"
            else (n, r)
            for n, r in routes
        ]
        # products GLOBAL == GLOBAL (clean); force a non-contradiction problem via a
        # missing table instead: drop products from SHOW TABLES.
        routes = [
            (n, [("public", "orders", "REGIONAL BY ROW")]) if n == "SHOW TABLES" else (n, r)
            for n, r in routes
        ]
        engine = _FakeEngine(routes)
        with pytest.raises(MultiregionCheckError):
            verify_multiregion_schema(engine, base, mode="validate")

    def test_warn_logs_but_does_not_raise_on_plain_problem(self, caplog):
        import logging

        base, *_ = _make_base()
        routes = _routes(orders_locality="REGIONAL BY ROW")
        routes = [
            (n, [("public", "orders", "REGIONAL BY ROW")]) if n == "SHOW TABLES" else (n, r)
            for n, r in routes
        ]
        engine = _FakeEngine(routes)
        with caplog.at_level(logging.WARNING):
            verify_multiregion_schema(engine, base, mode="warn")  # products missing -> warn
        assert any("multiregion check" in r.message for r in caplog.records)
