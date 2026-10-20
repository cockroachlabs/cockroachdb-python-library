"""Low-level vector similarity search against CockroachDB + pgvector."""

from __future__ import annotations

import logging
from typing import Any

import psycopg
import psycopg.rows

from cockroachdb.config import AIConfig
from cockroachdb.types import DistanceMetric, VectorSearchResult

logger = logging.getLogger(__name__)


class VectorSearchTemplate:
    """Execute vector similarity searches against CockroachDB with pgvector.

    Provides both sync and async search methods, embedding storage, and
    distance-metric operator mapping.  Built on psycopg for connection
    management.

    Example::

        from cockroachdb.ai import VectorSearchTemplate

        vst = VectorSearchTemplate("postgresql://root@localhost:26257/defaultdb")
        results = vst.search(
            table="documents",
            vector_column="embedding",
            query_vector=[0.1, 0.2, ...],
            limit=5,
        )
    """

    def __init__(
        self,
        conninfo: str,
        config: AIConfig | None = None,
    ) -> None:
        """Initialise the search template.

        Args:
            conninfo: PostgreSQL-style connection string.
            config: Optional AI configuration overriding defaults.
        """
        self._conninfo = conninfo
        self._config = config or AIConfig()

    def search(
        self,
        table: str,
        vector_column: str,
        query_vector: list[float],
        *,
        metric: DistanceMetric = DistanceMetric.COSINE,
        limit: int | None = None,
        columns: list[str] | None = None,
        filter_sql: str | None = None,
        filter_params: list[Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Run a synchronous vector similarity search.

        Args:
            table: Table containing vector data.
            vector_column: Column storing embeddings.
            query_vector: The query embedding to compare against.
            metric: Distance metric (cosine, L2, inner product).
            limit: Maximum results to return; defaults to ``config.default_limit``.
            columns: Specific columns to return (default: all).
            filter_sql: Optional WHERE clause fragment (e.g. ``"category = %s"``).
            filter_params: Parameters for the filter clause.

        Returns:
            List of :class:`VectorSearchResult` ordered by similarity.
        """
        effective_limit = limit or self._config.default_limit
        sql, params = self._build_query(
            table,
            vector_column,
            query_vector,
            metric,
            effective_limit,
            columns,
            filter_sql,
            filter_params,
        )

        with psycopg.connect(self._conninfo, row_factory=psycopg.rows.dict_row) as conn:
            if self._config.vector_search_beam_size is not None:
                conn.execute(
                    f"SET vector_search_beam_size = {self._config.vector_search_beam_size}"
                )
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        return self._rows_to_results(rows, vector_column, metric)

    async def search_async(
        self,
        table: str,
        vector_column: str,
        query_vector: list[float],
        *,
        metric: DistanceMetric = DistanceMetric.COSINE,
        limit: int | None = None,
        columns: list[str] | None = None,
        filter_sql: str | None = None,
        filter_params: list[Any] | None = None,
    ) -> list[VectorSearchResult]:
        """Run an asynchronous vector similarity search.

        Arguments are identical to :meth:`search`.
        """
        effective_limit = limit or self._config.default_limit
        sql, params = self._build_query(
            table,
            vector_column,
            query_vector,
            metric,
            effective_limit,
            columns,
            filter_sql,
            filter_params,
        )

        async with await psycopg.AsyncConnection.connect(
            self._conninfo, row_factory=psycopg.rows.dict_row
        ) as conn:
            if self._config.vector_search_beam_size is not None:
                await conn.execute(
                    f"SET vector_search_beam_size = {self._config.vector_search_beam_size}"
                )
            cursor = await conn.execute(sql, params)
            rows = await cursor.fetchall()

        return self._rows_to_results(rows, vector_column, metric)

    def store_embedding(
        self,
        table: str,
        id_column: str,
        id_value: Any,
        vector_column: str,
        embedding: list[float],
    ) -> None:
        """Store or update a vector embedding for a row.

        Uses an UPSERT so the call is idempotent.

        Args:
            table: Target table.
            id_column: Primary key column name.
            id_value: Primary key value.
            vector_column: Column to store the embedding in.
            embedding: The vector to store.
        """
        vector_literal = f"[{','.join(str(v) for v in embedding)}]"
        sql = f"UPSERT INTO {table} ({id_column}, {vector_column}) VALUES (%s, %s::vector)"
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(sql, [id_value, vector_literal])
            conn.commit()

    def store_embedding_with_metadata(
        self,
        table: str,
        id_column: str,
        id_value: Any,
        vector_column: str,
        embedding: list[float],
        metadata: dict[str, Any],
        *,
        metadata_column: str = "metadata",
    ) -> None:
        """Store a vector embedding alongside JSONB metadata.

        Args:
            table: Target table.
            id_column: Primary key column name.
            id_value: Primary key value.
            vector_column: Column to store the embedding in.
            embedding: The vector to store.
            metadata: Arbitrary metadata stored as JSONB.
            metadata_column: Name of the JSONB metadata column.
        """
        import json

        vector_literal = f"[{','.join(str(v) for v in embedding)}]"
        sql = (
            f"UPSERT INTO {table} ({id_column}, {vector_column}, {metadata_column}) "
            f"VALUES (%s, %s::vector, %s::jsonb)"
        )
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(sql, [id_value, vector_literal, json.dumps(metadata)])
            conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_query(
        self,
        table: str,
        vector_column: str,
        query_vector: list[float],
        metric: DistanceMetric,
        limit: int,
        columns: list[str] | None,
        filter_sql: str | None,
        filter_params: list[Any] | None,
    ) -> tuple[str, list[Any]]:
        """Build the SELECT ... ORDER BY <operator> query."""
        vector_literal = f"[{','.join(str(v) for v in query_vector)}]"
        col_list = ", ".join(columns) if columns else "*"
        operator = metric.operator
        distance_expr = f"{vector_column} {operator} %s::vector"

        parts = [f"SELECT {col_list}, {distance_expr} AS _distance FROM {table}"]
        params: list[Any] = [vector_literal]

        if filter_sql:
            parts.append(f"WHERE {filter_sql}")
            if filter_params:
                params.extend(filter_params)

        parts.append("ORDER BY _distance ASC LIMIT %s")
        params.append(limit)

        sql = " ".join(parts)
        return sql, params

    @staticmethod
    def _rows_to_results(
        rows: list[dict[str, Any]],
        vector_column: str,
        metric: DistanceMetric,
    ) -> list[VectorSearchResult]:
        """Convert raw rows into VectorSearchResult instances."""
        results: list[VectorSearchResult] = []
        for row in rows:
            distance = float(row.pop("_distance", 0.0))
            row.pop(vector_column, None)
            first_key = next(iter(row), None)
            results.append(
                VectorSearchResult(
                    id=row.get(first_key) if first_key else None,
                    document=row,
                    distance=distance,
                    similarity=metric.to_similarity(distance),
                )
            )
        return results
