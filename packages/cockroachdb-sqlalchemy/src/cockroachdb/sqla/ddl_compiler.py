"""CockroachDB DDL compiler with inline index support.

Inlines non-unique indexes inside ``CREATE TABLE`` statements for a ~25x
speedup on CockroachDB (single schema-change job vs one per index).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import exc
from sqlalchemy.dialects.postgresql.base import PGDDLCompiler


class CockroachDDLCompiler(PGDDLCompiler):
    """DDL compiler that inlines indexes and handles computed columns."""

    def visit_computed_column(self, generated: Any, **kw: Any) -> str:
        """CockroachDB computed columns must be STORED (no virtual)."""
        if generated.persisted is False:
            raise exc.CompileError(
                "CockroachDB computed columns do not support 'virtual' "
                "persistence; set the 'persisted' flag to None or True for "
                "CockroachDB support."
            )
        sqltext = self.sql_compiler.process(
            generated.sqltext, include_table=False, literal_binds=True
        )
        return f"AS ({sqltext}) STORED"

    def visit_create_table(self, create: Any, **kw: Any) -> str:
        """Override CREATE TABLE to inject inline indexes before closing paren.

        CockroachDB processes inline indexes in a single schema-change job,
        whereas separate ``CREATE INDEX`` statements each trigger their own
        job — resulting in ~25x slower table creation.
        """
        table = create.element
        ddl: str = super().visit_create_table(create, **kw)  # type: ignore[no-untyped-call]

        inline_parts: list[str] = []
        for index in table.indexes:
            if index.unique:
                continue

            cols = ", ".join(self.preparer.format_column(col) for col in index.columns)
            idx_name = self.preparer.format_index(index)

            storing = ""
            storing_cols = index.dialect_options.get("cockroachdb", {}).get("storing", [])
            if storing_cols:
                storing_formatted = ", ".join(self.preparer.quote(c) for c in storing_cols)
                storing = f" STORING ({storing_formatted})"

            inline_parts.append(f",\n  INDEX {idx_name} ({cols}){storing}")

        if inline_parts:
            index_sql = "".join(inline_parts)
            close_paren_pos = ddl.rfind("\n)")
            if close_paren_pos == -1:
                close_paren_pos = ddl.rfind(")")
            if close_paren_pos != -1:
                ddl = ddl[:close_paren_pos] + index_sql + ddl[close_paren_pos:]

        return ddl

    def visit_create_index(self, create: Any, **kw: Any) -> str:  # type: ignore[override]
        """Skip non-unique indexes — they were already inlined."""
        index = create.element
        if not index.unique and hasattr(index, "table") and index.table is not None:
            return ""
        return super().visit_create_index(create, **kw)  # type: ignore[no-untyped-call,no-any-return]
