"""Psycopg-specific exception classifier for CockroachDB retryable errors."""

from __future__ import annotations

_SERIALIZATION_FAILURE = "40001"
_DEADLOCK_DETECTED = "40P01"
_RETRYABLE_SQLSTATES = frozenset({_SERIALIZATION_FAILURE, _DEADLOCK_DETECTED})


class PsycopgExceptionClassifier:
    """Classifies psycopg exceptions by walking the exception chain.

    Implements the ``ExceptionClassifier`` protocol from ``cockroachdb.types``.
    """

    def _extract_sqlstate(self, error: Exception) -> str | None:
        sqlstate = getattr(error, "sqlstate", None)
        if sqlstate:
            return str(sqlstate)
        pgcode = getattr(error, "pgcode", None)
        if pgcode:
            return str(pgcode)
        return None

    def _walk_chain(self, error: Exception) -> str | None:
        """Walk __cause__ chain to find the first SQLSTATE."""
        current: Exception | None = error
        while current is not None:
            sqlstate = self._extract_sqlstate(current)
            if sqlstate:
                return sqlstate
            current = current.__cause__  # type: ignore[assignment]
        return None

    def is_retryable(self, error: Exception) -> bool:
        sqlstate = self._walk_chain(error)
        return sqlstate in _RETRYABLE_SQLSTATES if sqlstate else False

    def is_serialization_error(self, error: Exception) -> bool:
        sqlstate = self._walk_chain(error)
        return sqlstate == _SERIALIZATION_FAILURE
