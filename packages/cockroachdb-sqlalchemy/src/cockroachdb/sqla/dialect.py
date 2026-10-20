"""CockroachDB SQLAlchemy dialect.

Registers as ``cockroachdb://`` URL scheme, providing CockroachDB-specific
type mapping, column reflection, DDL compilation with inline indexes,
and savepoint-restart retry protocol support.

Usage::

    from sqlalchemy import create_engine
    engine = create_engine("cockroachdb://root@localhost:26257/defaultdb")
"""

from __future__ import annotations

import re
import threading
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import schema as sa_schema
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from .ddl_compiler import CockroachDDLCompiler
from .stmt_compiler import CockroachCompiler, CockroachIdentifierPreparer
from .types import resolve_type

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


class _SavepointState(threading.local):
    """Thread-local state for savepoint name rewriting.

    When ``cockroach_restart`` is True, savepoint operations are
    rewritten to use ``SAVEPOINT cockroach_restart`` — the CockroachDB
    server-side retry protocol.
    """

    def __init__(self):
        self.cockroach_restart = False


savepoint_state = _SavepointState()


class CockroachDBDialect(PGDialect_psycopg):
    """SQLAlchemy dialect for CockroachDB.

    Extends the PostgreSQL dialect with CockroachDB-specific behaviour:
    type mapping, column reflection, DDL compilation (inline indexes,
    computed columns), and the ``cockroach_restart`` savepoint protocol.
    """

    name = "cockroachdb"
    driver = "psycopg"
    supports_empty_insert = True
    supports_multivalues_insert = True
    supports_sequences = False
    supports_statement_cache = True

    statement_compiler = CockroachCompiler
    preparer = CockroachIdentifierPreparer
    ddl_compiler = CockroachDDLCompiler

    construct_arguments: ClassVar = [
        (
            sa_schema.Index,
            {"storing": []},
        ),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # --- Version detection ------------------------------------------------

    def _get_server_version_info(self, connection):
        """Parse CockroachDB version string.

        CockroachDB returns ``CockroachDB CCL v24.3.33 (...)`` instead
        of PostgreSQL's ``PostgreSQL 15.4 ...``.  We extract the CRDB
        version and present it as a tuple so SQLAlchemy doesn't crash.
        """
        v = connection.exec_driver_sql("select version()").scalar()
        m = re.match(r".*?v(\d+)\.(\d+)\.(\d+)", v)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (24, 3, 0)

    # --- Column reflection ------------------------------------------------

    def get_columns(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = None,
        **kw: Any,
    ) -> list[dict[str, Any]]:
        """Reflect columns using CockroachDB's ``crdb_sql_type``."""
        include_hidden = kw.get("include_hidden", False)

        sql = (
            "SELECT column_name, data_type, is_nullable::bool, column_default, "
            "numeric_precision, numeric_scale, character_maximum_length, "
            "CASE is_generated WHEN 'ALWAYS' THEN true WHEN 'NEVER' THEN false "
            "ELSE is_generated::bool END AS is_generated, "
            "generation_expression, is_hidden::bool, crdb_sql_type, "
            "column_comment AS comment "
            "FROM information_schema.columns "
            "WHERE table_schema = :table_schema AND table_name = :table_name "
        )
        if not include_hidden:
            sql += "AND NOT is_hidden::bool "
        sql += "ORDER BY ordinal_position"

        rows = connection.execute(
            text(sql),
            {
                "table_schema": schema or self.default_schema_name,
                "table_name": table_name,
            },
        )

        result: list[dict[str, Any]] = []
        for row in rows:
            name = row.column_name
            is_array = row.data_type == "ARRAY"

            type_str = row.crdb_sql_type if hasattr(row, "crdb_sql_type") else row.data_type
            if type_str:
                type_str = type_str.lower()
                if is_array and type_str.endswith("[]"):
                    type_str = type_str[:-2]

            typ = resolve_type(type_str or "")
            if is_array:
                typ = ARRAY(type(typ))

            default = row.column_default
            autoincrement = False
            if default is not None and re.search(r"unique_rowid\(\)", default):
                autoincrement = True

            column_info: dict[str, Any] = {
                "name": name,
                "type": typ,
                "nullable": row.is_nullable,
                "default": default,
                "autoincrement": autoincrement,
                "comment": row.comment,
            }

            if row.is_generated:
                column_info["computed"] = {
                    "sqltext": row.generation_expression,
                    "persisted": True,
                }
                column_info["default"] = None

            result.append(column_info)

        return result

    def get_multi_columns(self, connection: Connection, **kw: Any) -> Any:
        """Route batch column reflection through the CRDB-safe ``get_columns``.

        SQLAlchemy 2.1's ``MetaData.reflect()`` uses the batch
        ``get_multi_columns`` API, whose PostgreSQL implementation queries
        ``pg_catalog.pg_collation_is_visible()`` — a function CockroachDB does
        not implement.  Delegating to the generic per-table reflection makes
        it call our ``information_schema``-based :meth:`get_columns` instead.
        """
        return self._default_multi_reflect(self.get_columns, connection, **kw)

    # --- Index reflection -------------------------------------------------

    def get_indexes(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = None,
        **kw: Any,
    ) -> list[dict[str, Any]]:
        """Reflect indexes, removing ``duplicates_constraint`` from unique indexes."""
        indexes = super().get_indexes(connection, table_name, schema, **kw)
        for index in indexes:
            if index.get("unique") and "duplicates_constraint" in index:
                del index["duplicates_constraint"]
        return indexes

    # --- Savepoint protocol -----------------------------------------------

    def do_savepoint(self, connection, name):
        if savepoint_state.cockroach_restart:
            connection.execute(text("SAVEPOINT cockroach_restart"))
        else:
            super().do_savepoint(connection, name)

    def do_rollback_to_savepoint(self, connection, name):
        if savepoint_state.cockroach_restart:
            connection.execute(text("ROLLBACK TO SAVEPOINT cockroach_restart"))
        else:
            super().do_rollback_to_savepoint(connection, name)

    def do_release_savepoint(self, connection, name):
        if savepoint_state.cockroach_restart:
            connection.execute(text("RELEASE SAVEPOINT cockroach_restart"))
        else:
            super().do_release_savepoint(connection, name)


# --- Alembic integration (side-effect import) ---
from . import alembic_impl as _alembic_impl  # noqa: E402, F401
