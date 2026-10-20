"""Integration tests for DDL compiler against live CockroachDB clusters."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import (
    Column,
    Computed,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    text,
)

pytestmark = pytest.mark.integration


class TestInlineIndexes1Node:
    """Inline index DDL tests on a single-node cluster."""

    def test_create_table_with_inline_indexes(self, crdb_1node):
        table_name = f"test_inline_{uuid.uuid4().hex[:8]}"
        engine = create_engine(crdb_1node)
        metadata = MetaData()

        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("customer", String(100)),
            Column("region", String(50)),
            Column("total", Integer),
            Index("idx_customer", "customer"),
            Index("idx_region_total", "region", "total"),
        )

        metadata.create_all(engine)

        with engine.connect() as conn:
            result = conn.execute(text(f"SHOW INDEXES FROM {table_name}"))
            indexes = [row._mapping for row in result]
            index_names = {r["index_name"] for r in indexes}

            assert "idx_customer" in index_names
            assert "idx_region_total" in index_names

        metadata.drop_all(engine)
        engine.dispose()

    def test_inline_index_with_storing(self, crdb_1node):
        table_name = f"test_storing_{uuid.uuid4().hex[:8]}"
        engine = create_engine(crdb_1node)
        metadata = MetaData()

        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(100)),
            Column("email", String(200)),
            Index("idx_name_store", "name", cockroachdb_storing=["email"]),
        )

        metadata.create_all(engine)

        with engine.connect() as conn:
            result = conn.execute(text(f"SHOW INDEXES FROM {table_name}"))
            storing_cols = [
                r._mapping
                for r in result
                if r._mapping["index_name"] == "idx_name_store"
                and r._mapping.get("storing", False)
            ]
            assert len(storing_cols) > 0

        metadata.drop_all(engine)
        engine.dispose()

    def test_computed_column(self, crdb_1node):
        table_name = f"test_computed_{uuid.uuid4().hex[:8]}"
        engine = create_engine(crdb_1node)
        metadata = MetaData()

        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("price", Integer),
            Column("qty", Integer),
            Column("total", Integer, Computed("price * qty", persisted=True)),
        )

        metadata.create_all(engine)

        with engine.connect() as conn:
            conn.execute(text(f"INSERT INTO {table_name} (id, price, qty) VALUES (1, 10, 5)"))
            conn.commit()
            row = conn.execute(text(f"SELECT total FROM {table_name} WHERE id = 1")).fetchone()
            assert row[0] == 50

        metadata.drop_all(engine)
        engine.dispose()


class TestInlineIndexes3Node:
    """Same tests on a 3-node cluster."""

    def test_create_table_with_inline_indexes(self, crdb_3node):
        table_name = f"test_3n_inline_{uuid.uuid4().hex[:8]}"
        engine = create_engine(crdb_3node)
        metadata = MetaData()

        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("customer", String(100)),
            Column("total", Integer),
            Index("idx_cust_3n", "customer"),
            Index("idx_total_3n", "total"),
        )

        metadata.create_all(engine)

        with engine.connect() as conn:
            result = conn.execute(text(f"SHOW INDEXES FROM {table_name}"))
            index_names = {r._mapping["index_name"] for r in result}
            assert "idx_cust_3n" in index_names
            assert "idx_total_3n" in index_names

        metadata.drop_all(engine)
        engine.dispose()


class TestDialectConnection:
    """Test that the cockroachdb:// dialect URL works."""

    def test_cockroachdb_url_connects(self, crdb_1node):
        url = crdb_1node.replace("postgresql://", "cockroachdb://")
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            assert result == 1
        engine.dispose()

    def test_column_reflection(self, crdb_1node):
        table_name = f"test_reflect_{uuid.uuid4().hex[:8]}"
        engine = create_engine(crdb_1node)

        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {table_name} ("
                    "id INT8 PRIMARY KEY DEFAULT unique_rowid(), "
                    "name STRING NOT NULL, "
                    "data BYTES, "
                    "score FLOAT8, "
                    "meta JSONB)"
                )
            )
            conn.commit()

        metadata = MetaData()
        metadata.reflect(bind=engine, only=[table_name])

        t = metadata.tables[table_name]
        col_types = {c.name: type(c.type).__name__ for c in t.columns}

        assert "id" in col_types
        assert "name" in col_types
        assert "data" in col_types

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE {table_name}"))
            conn.commit()
        engine.dispose()
