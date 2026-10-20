"""Tests for CockroachDB DDL compiler — all against live CockroachDB.

Every test creates real tables on a running CockroachDB instance and
verifies the results via SQL queries.

Requires: docker-compose -f docker/docker-compose.1node.yml up -d
"""

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

CRDB_URL = "cockroachdb+psycopg://root@localhost:26257/defaultdb?sslmode=disable"


@pytest.fixture(scope="module")
def engine():
    e = create_engine(CRDB_URL)
    yield e
    e.dispose()


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _get_index_names(engine, table_name: str) -> set[str]:
    with engine.connect() as conn:
        result = conn.execute(text(f"SHOW INDEXES FROM {table_name}"))
        return {row._mapping["index_name"] for row in result}


class TestInlineIndexes:
    def test_inline_single_column_index(self, engine):
        name = _unique_name("t_single")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("customer", String(100)),
            Index("idx_cust_s", "customer"),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_cust_s" in indexes
        finally:
            metadata.drop_all(engine)

    def test_inline_composite_index(self, engine):
        name = _unique_name("t_comp")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("region", String(50)),
            Column("total", Integer),
            Index("idx_reg_tot", "region", "total"),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_reg_tot" in indexes
        finally:
            metadata.drop_all(engine)

    def test_inline_index_with_storing(self, engine):
        name = _unique_name("t_store")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("customer", String(100)),
            Column("email", String(200)),
            Index("idx_cust_st", "customer", cockroachdb_storing=["email"]),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_cust_st" in indexes
            with engine.connect() as conn:
                result = conn.execute(text(f"SHOW INDEXES FROM {name}"))
                storing_rows = [
                    r._mapping
                    for r in result
                    if r._mapping["index_name"] == "idx_cust_st"
                    and r._mapping.get("storing", False)
                ]
                assert len(storing_rows) > 0
        finally:
            metadata.drop_all(engine)

    def test_unique_index_not_inlined_but_created(self, engine):
        name = _unique_name("t_uniq")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("code", String(20)),
            Index("idx_code_u", "code", unique=True),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_code_u" in indexes
            with engine.connect() as conn:
                conn.execute(text(f"INSERT INTO {name} (id, code) VALUES (1, 'A')"))
                conn.commit()
                with pytest.raises(Exception, match="duplicate"):
                    conn.execute(text(f"INSERT INTO {name} (id, code) VALUES (2, 'A')"))
                    conn.commit()
        finally:
            metadata.drop_all(engine)

    def test_multiple_indexes_all_created(self, engine):
        name = _unique_name("t_multi")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("a", String(50)),
            Column("b", String(50)),
            Column("c", Integer),
            Index("idx_a", "a"),
            Index("idx_b", "b"),
            Index("idx_c", "c"),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert {"idx_a", "idx_b", "idx_c"}.issubset(indexes)
        finally:
            metadata.drop_all(engine)


class TestComputedColumns:
    def test_computed_column_stored_calculates(self, engine):
        name = _unique_name("t_comp_s")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("price", Integer),
            Column("qty", Integer),
            Column("total", Integer, Computed("price * qty", persisted=True)),
        )
        metadata.create_all(engine)
        try:
            with engine.connect() as conn:
                conn.execute(text(f"INSERT INTO {name} (id, price, qty) VALUES (1, 10, 5)"))
                conn.commit()
                row = conn.execute(text(f"SELECT total FROM {name} WHERE id = 1")).fetchone()
                assert row[0] == 50
        finally:
            metadata.drop_all(engine)

    def test_computed_column_default_persisted(self, engine):
        name = _unique_name("t_comp_d")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("price", Integer),
            Column("doubled", Integer, Computed("price * 2")),
        )
        metadata.create_all(engine)
        try:
            with engine.connect() as conn:
                conn.execute(text(f"INSERT INTO {name} (id, price) VALUES (1, 7)"))
                conn.commit()
                row = conn.execute(text(f"SELECT doubled FROM {name} WHERE id = 1")).fetchone()
                assert row[0] == 14
        finally:
            metadata.drop_all(engine)

    def test_computed_column_virtual_raises(self, engine):
        from sqlalchemy import exc

        name = _unique_name("t_comp_v")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("price", Integer),
            Column("doubled", Integer, Computed("price * 2", persisted=False)),
        )
        with pytest.raises(exc.CompileError, match="virtual"):
            metadata.create_all(engine)


class TestVisitCreateIndex:
    def test_inline_indexes_dont_create_separate_statements(self, engine):
        """Verify that non-unique indexes are inlined, not separate CREATE INDEX."""
        name = _unique_name("t_nosep")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("val", String(100)),
            Index("idx_val_nosep", "val"),
        )
        from sqlalchemy.schema import CreateTable

        ddl = str(CreateTable(metadata.tables[name]).compile(dialect=engine.dialect))
        assert "INDEX idx_val_nosep" in ddl
        assert ddl.count("INDEX idx_val_nosep") == 1

        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_val_nosep" in indexes
        finally:
            metadata.drop_all(engine)

    def test_unique_index_emitted_as_separate_statement(self, engine):
        name = _unique_name("t_usep")
        metadata = MetaData()
        Table(
            name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("code", String(20)),
            Index("idx_code_sep", "code", unique=True),
        )
        metadata.create_all(engine)
        try:
            indexes = _get_index_names(engine, name)
            assert "idx_code_sep" in indexes
        finally:
            metadata.drop_all(engine)
