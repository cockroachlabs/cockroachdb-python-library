"""CockroachDB SQL statement compiler for SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql.base import PGCompiler, PGIdentifierPreparer


class CockroachIdentifierPreparer(PGIdentifierPreparer):
    """Identifier preparer with CockroachDB-specific reserved words."""

    reserved_words = PGIdentifierPreparer.reserved_words | {
        "virtual",
        "nothing",
        "storing",
        "interleave",
        "locality",
    }


class CockroachCompiler(PGCompiler):
    """SQL compiler with CockroachDB-specific features."""

    def format_from_hint_text(self, table, text, is_lateral):
        """Support CockroachDB index hints: ``table@index_name``."""
        return table.name + "@" + text
