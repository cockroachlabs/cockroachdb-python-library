"""Alembic integration for the CockroachDB dialect.

Registers ``CockroachDBImpl`` so that Alembic recognises the
``cockroachdb`` dialect and treats DDL as non-transactional
(CockroachDB auto-commits each DDL statement).

This module is imported as a side-effect from :mod:`cockroachdb.sqla.dialect`
and requires ``alembic`` to be installed.
"""

from __future__ import annotations

from typing import Any

try:
    import alembic.ddl.postgresql
    from sqlalchemy.ext.compiler import compiles
except ImportError:
    pass
else:

    class CockroachDBImpl(alembic.ddl.postgresql.PostgresqlImpl):
        """Alembic implementation for CockroachDB.

        CockroachDB DDL is non-transactional — each DDL statement is
        auto-committed.  Setting ``transactional_ddl = False`` tells
        Alembic not to wrap migrations in a transaction.
        """

        __dialect__ = "cockroachdb"
        transactional_ddl = False

    @compiles(alembic.ddl.postgresql.PostgresqlColumnType, "cockroachdb")
    def visit_column_type(*args: Any, **kwargs: Any) -> Any:
        return alembic.ddl.postgresql.visit_column_type(*args, **kwargs)

    @compiles(alembic.ddl.postgresql.ColumnComment, "cockroachdb")  # type: ignore[attr-defined]
    def visit_column_comment(*args: Any, **kwargs: Any) -> Any:
        return alembic.ddl.postgresql.visit_column_comment(*args, **kwargs)
