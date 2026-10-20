"""Tests for CockroachDB SQLAlchemy dialect — all against live CockroachDB.

Verifies type mapping, column reflection, version parsing, and dialect
properties by connecting to a running CockroachDB instance.

Requires: docker-compose -f docker/docker-compose.1node.yml up -d
"""

import uuid

import pytest
from sqlalchemy import MetaData, create_engine, text

from cockroachdb.sqla.types import CRDB_TYPE_MAP, resolve_type

CRDB_URL = "cockroachdb+psycopg://root@localhost:26257/defaultdb?sslmode=disable"


@pytest.fixture(scope="module")
def engine():
    e = create_engine(CRDB_URL)
    yield e
    e.dispose()


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestDialectProperties:
    def test_dialect_name(self, engine):
        assert engine.dialect.name == "cockroachdb"

    def test_supports_sequences_false(self, engine):
        assert engine.dialect.supports_sequences is False

    def test_supports_empty_insert(self, engine):
        assert engine.dialect.supports_empty_insert is True

    def test_supports_multivalues_insert(self, engine):
        assert engine.dialect.supports_multivalues_insert is True

    def test_version_parsed_from_live_crdb(self, engine):
        with engine.connect():
            ver = engine.dialect.server_version_info
            assert ver is not None
            assert ver[0] >= 23


class TestTypeMapping:
    """Verify type mapping by creating actual tables with each type and reflecting."""

    def test_int_types_roundtrip(self, engine):
        name = _unique_name("t_int")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} ("
                    "id INT8 PRIMARY KEY DEFAULT unique_rowid(), "
                    "small_val INT2, "
                    "med_val INT4, "
                    "big_val INT8)"
                )
            )
            conn.commit()
            conn.execute(
                text(f"INSERT INTO {name} (small_val, med_val, big_val) VALUES (1, 1000, 9999999)")
            )
            conn.commit()
            row = conn.execute(
                text(f"SELECT small_val, med_val, big_val FROM {name} LIMIT 1")
            ).fetchone()
            assert row[0] == 1
            assert row[1] == 1000
            assert row[2] == 9999999
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_string_bytes_roundtrip(self, engine):
        name = _unique_name("t_str")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} ("
                    "id INT8 PRIMARY KEY DEFAULT unique_rowid(), "
                    "s STRING, "
                    "b BYTES)"
                )
            )
            conn.commit()
            conn.execute(text(f"INSERT INTO {name} (s, b) VALUES ('hello', '\\x48454c4c4f')"))
            conn.commit()
            row = conn.execute(text(f"SELECT s, b FROM {name} LIMIT 1")).fetchone()
            assert row[0] == "hello"
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_jsonb_roundtrip(self, engine):
        name = _unique_name("t_json")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} (id INT8 PRIMARY KEY DEFAULT unique_rowid(), data JSONB)"
                )
            )
            conn.commit()
            conn.execute(
                text(f"""INSERT INTO {name} (data) VALUES ('{{"key": "value"}}'::jsonb)""")
            )
            conn.commit()
            row = conn.execute(text(f"SELECT data->>'key' FROM {name} LIMIT 1")).fetchone()
            assert row[0] == "value"
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_uuid_roundtrip(self, engine):
        name = _unique_name("t_uuid")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), val INT8)"
                )
            )
            conn.commit()
            conn.execute(text(f"INSERT INTO {name} (val) VALUES (42)"))
            conn.commit()
            row = conn.execute(text(f"SELECT id, val FROM {name} LIMIT 1")).fetchone()
            assert len(str(row[0])) == 36  # UUID format
            assert row[1] == 42
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_timestamp_roundtrip(self, engine):
        name = _unique_name("t_ts")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} ("
                    "id INT8 PRIMARY KEY DEFAULT unique_rowid(), "
                    "ts TIMESTAMPTZ DEFAULT now())"
                )
            )
            conn.commit()
            conn.execute(text(f"INSERT INTO {name} DEFAULT VALUES"))
            conn.commit()
            row = conn.execute(text(f"SELECT ts FROM {name} LIMIT 1")).fetchone()
            assert row[0] is not None
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    @pytest.mark.parametrize(
        "crdb_type,expected",
        [
            ("int2", "SmallInteger"),
            ("int4", "Integer"),
            ("int8", "BigInteger"),
            ("string", "String"),
            ("bytes", "LargeBinary"),
            ("bool", "Boolean"),
            ("float8", "Float"),
            ("jsonb", "JSONB"),
            ("uuid", "UUID"),
            ("inet", "INET"),
            ("timestamp", "DateTime"),
            ("timestamptz", "DateTime"),
            ("text", "Text"),
            ("decimal", "Numeric"),
        ],
    )
    def test_type_map_entries(self, crdb_type, expected):
        typ = CRDB_TYPE_MAP[crdb_type]
        assert type(typ).__name__ == expected

    def test_resolve_unknown_returns_nulltype(self):
        from sqlalchemy import types as sqltypes

        assert resolve_type("unknown_weird_type") is sqltypes.NULLTYPE

    def test_resolve_array(self):
        typ = resolve_type("int4[]")
        assert "ARRAY" in type(typ).__name__.upper()


class TestColumnReflection:
    def test_reflect_crdb_types(self, engine):
        name = _unique_name("t_reflect")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} ("
                    "id INT8 PRIMARY KEY DEFAULT unique_rowid(), "
                    "name STRING NOT NULL, "
                    "score FLOAT8, "
                    "data BYTES, "
                    "meta JSONB, "
                    "uid UUID DEFAULT gen_random_uuid())"
                )
            )
            conn.commit()

        metadata = MetaData()
        metadata.reflect(bind=engine, only=[name])
        t = metadata.tables[name]
        col_names = {c.name for c in t.columns}

        assert {"id", "name", "score", "data", "meta", "uid"} == col_names

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_reflect_computed_column(self, engine):
        name = _unique_name("t_ref_comp")
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE TABLE {name} ("
                    "id INT8 PRIMARY KEY, "
                    "a INT8, b INT8, "
                    "c INT8 AS (a + b) STORED)"
                )
            )
            conn.commit()

        cols = engine.dialect.get_columns(engine.connect(), name)
        computed_cols = [c for c in cols if c.get("computed")]
        assert len(computed_cols) == 1
        assert computed_cols[0]["name"] == "c"
        assert computed_cols[0]["computed"]["persisted"] is True

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()

    def test_reflect_autoincrement_unique_rowid(self, engine):
        name = _unique_name("t_ref_auto")
        with engine.connect() as conn:
            conn.execute(
                text(f"CREATE TABLE {name} (id INT8 PRIMARY KEY DEFAULT unique_rowid(), val TEXT)")
            )
            conn.commit()

        cols = engine.dialect.get_columns(engine.connect(), name)
        id_col = next(c for c in cols if c["name"] == "id")
        assert id_col["autoincrement"] is True

        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()


class TestReservedWords:
    def test_crdb_reserved_words(self):
        from cockroachdb.sqla.stmt_compiler import CockroachIdentifierPreparer

        assert "virtual" in CockroachIdentifierPreparer.reserved_words
        assert "storing" in CockroachIdentifierPreparer.reserved_words

    def test_index_hint_format_works_on_live(self, engine):
        name = _unique_name("t_hint")
        with engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE {name} (id INT8 PRIMARY KEY, val STRING)"))
            conn.commit()
            conn.execute(text(f"CREATE INDEX idx_val_hint ON {name} (val)"))
            conn.commit()
            row = conn.execute(
                text(f"SELECT val FROM {name}@idx_val_hint WHERE val = 'test'")
            ).fetchone()
            assert row is None  # empty table, just verify the hint syntax works
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()
