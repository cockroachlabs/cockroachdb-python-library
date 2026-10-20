"""Tests for Alembic integration — verifies against live CockroachDB.

Requires: docker-compose -f docker/docker-compose.1node.yml up -d
          pip install alembic
"""

import uuid

import pytest

CRDB_URL = "cockroachdb+psycopg://root@localhost:26257/defaultdb?sslmode=disable"


class TestAlembicRegistration:
    def test_cockroachdb_impl_exists(self):
        pytest.importorskip("alembic")
        from cockroachdb.sqla.alembic_impl import CockroachDBImpl

        assert CockroachDBImpl.__dialect__ == "cockroachdb"

    def test_transactional_ddl_is_false(self):
        pytest.importorskip("alembic")
        from cockroachdb.sqla.alembic_impl import CockroachDBImpl

        assert CockroachDBImpl.transactional_ddl is False

    def test_dialect_import_registers_alembic(self):
        alembic = pytest.importorskip("alembic")
        from cockroachdb.sqla.dialect import CockroachDBDialect  # noqa: F401

        assert "cockroachdb" in alembic.ddl.impl._impls

    def test_alembic_connects_to_live_crdb(self):
        pytest.importorskip("alembic")
        from sqlalchemy import create_engine, text

        engine = create_engine(CRDB_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()")).scalar()
            assert "CockroachDB" in result
        engine.dispose()

    def test_alembic_ddl_non_transactional_on_live(self):
        """Verify DDL auto-commits on CockroachDB (non-transactional)."""
        pytest.importorskip("alembic")
        from sqlalchemy import create_engine, text

        name = f"t_alembic_{uuid.uuid4().hex[:8]}"
        engine = create_engine(CRDB_URL)
        with engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE {name} (id INT8 PRIMARY KEY)"))
            conn.commit()
            result = conn.execute(
                text(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{name}'")
            ).scalar()
            assert result == 1
            conn.execute(text(f"DROP TABLE {name}"))
            conn.commit()
        engine.dispose()
