"""High-level vector store with automatic embedding and document management."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg
import psycopg.rows

from cockroachdb.config import AIConfig
from cockroachdb.types import DistanceMetric, EmbeddingProvider, VectorSearchResult

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """A document to store in the vector store.

    Attributes:
        id: Unique identifier. Auto-generated if not provided.
        content: The text content of the document.
        metadata: Arbitrary metadata stored alongside the document.
        embedding: Pre-computed embedding vector. If ``None``, the store will
            compute it using the configured embedding provider.
    """

    content: str
    id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())


class CockroachDBVectorStore:
    """High-level vector store backed by CockroachDB and pgvector.

    Manages document storage with automatic embedding generation, similarity
    search, and table lifecycle.

    Example::

        from cockroachdb.ai import CockroachDBVectorStore, Document

        store = CockroachDBVectorStore(
            conninfo="postgresql://root@localhost:26257/defaultdb",
            table="docs",
            vector_column="embedding",
            embedding_provider=my_provider,
        )
        store.ensure_table()

        store.add_documents([
            Document(content="CockroachDB is a distributed SQL database."),
            Document(content="pgvector enables vector similarity search."),
        ])

        results = await store.similarity_search("distributed database", limit=3)
    """

    def __init__(
        self,
        conninfo: str,
        table: str,
        vector_column: str,
        embedding_provider: EmbeddingProvider,
        config: AIConfig | None = None,
        *,
        prefix_columns: list[str] | None = None,
    ) -> None:
        """Initialise the vector store.

        Args:
            conninfo: PostgreSQL connection string.
            table: Table name for document storage.
            vector_column: Column name for embedding vectors.
            embedding_provider: Provider implementing the
                :class:`~cockroachdb.types.EmbeddingProvider` protocol.
            config: Optional AI configuration.
            prefix_columns: Optional list of prefix columns for the vector
                index (CockroachDB v26.2+). For example, ``["tenant_id"]``
                creates an index ``(tenant_id, embedding vector_cosine_ops)``,
                which improves accuracy for filtered queries.
        """
        self._conninfo = conninfo
        self._table = table
        self._vector_column = vector_column
        self._provider = embedding_provider
        self._config = config or AIConfig()
        self._prefix_columns = prefix_columns or []

    async def add_documents(self, documents: list[Document]) -> list[str]:
        """Embed and store documents.

        Documents without pre-computed embeddings will have them generated
        via the configured embedding provider.

        Args:
            documents: List of documents to store.

        Returns:
            List of document IDs that were stored.
        """
        texts_to_embed: list[str] = []
        indices_needing_embed: list[int] = []

        for i, doc in enumerate(documents):
            if doc.embedding is None:
                texts_to_embed.append(doc.content)
                indices_needing_embed.append(i)

        if texts_to_embed:
            embeddings = await self._provider.embed_batch(texts_to_embed)
            for idx, embedding in zip(indices_needing_embed, embeddings, strict=False):
                documents[idx].embedding = embedding

        ids: list[str] = []
        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            for doc in documents:
                vector_literal = f"[{','.join(str(v) for v in doc.embedding)}]"  # type: ignore[union-attr]
                sql = (
                    f"UPSERT INTO {self._table} "
                    f"(id, content, {self._vector_column}, metadata) "
                    f"VALUES (%s, %s, %s::vector, %s::jsonb)"
                )
                await conn.execute(
                    sql,
                    [doc.id, doc.content, vector_literal, json.dumps(doc.metadata)],
                )
                ids.append(doc.id)
            await conn.commit()

        logger.info("Stored %d documents in %s", len(ids), self._table)
        return ids

    async def similarity_search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[VectorSearchResult]:
        """Search for documents similar to the query text.

        Embeds the query using the configured provider, then performs a
        vector similarity search.

        Args:
            query: Natural-language query string.
            limit: Maximum results; defaults to ``config.default_limit``.

        Returns:
            List of search results ordered by similarity.
        """
        results = await self.similarity_search_with_score(query, limit)
        return results

    async def similarity_search_with_score(
        self,
        query: str,
        limit: int | None = None,
        *,
        metric: DistanceMetric | None = None,
    ) -> list[VectorSearchResult]:
        """Search for documents with similarity scores.

        Args:
            query: Natural-language query string.
            limit: Maximum results; defaults to ``config.default_limit``.
            metric: Override distance metric; defaults to config value.

        Returns:
            List of :class:`VectorSearchResult` with distance and similarity scores.
        """
        effective_limit = limit or self._config.default_limit
        effective_metric = metric or DistanceMetric(self._config.default_metric)

        query_embedding = await self._provider.embed(query)
        vector_literal = f"[{','.join(str(v) for v in query_embedding)}]"
        operator = effective_metric.operator
        distance_expr = f"{self._vector_column} {operator} %s::vector"

        sql = (
            f"SELECT id, content, metadata, {distance_expr} AS _distance "
            f"FROM {self._table} "
            f"ORDER BY _distance ASC LIMIT %s"
        )

        async with await psycopg.AsyncConnection.connect(
            self._conninfo, row_factory=psycopg.rows.dict_row
        ) as conn:
            if self._config.vector_search_beam_size is not None:
                await conn.execute(
                    f"SET vector_search_beam_size = {self._config.vector_search_beam_size}"
                )
            cursor = await conn.execute(sql, [vector_literal, effective_limit])
            rows = await cursor.fetchall()

        results: list[VectorSearchResult] = []
        for row in rows:
            distance = float(row["_distance"])
            metadata = row.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            results.append(
                VectorSearchResult(
                    id=row["id"],
                    document={"content": row["content"], "metadata": metadata},
                    distance=distance,
                    similarity=effective_metric.to_similarity(distance),
                )
            )
        return results

    async def delete(self, ids: list[str]) -> int:
        """Remove documents by their IDs.

        Args:
            ids: List of document IDs to delete.

        Returns:
            Number of rows deleted.
        """
        if not ids:
            return 0

        placeholders = ", ".join(["%s"] * len(ids))
        sql = f"DELETE FROM {self._table} WHERE id IN ({placeholders})"

        async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
            cursor = await conn.execute(sql, ids)
            await conn.commit()
            return cursor.rowcount

    def _build_vector_index_ddl(self) -> str:
        """Build the CREATE VECTOR INDEX DDL for CockroachDB v26.2+.

        Returns the DDL string using the new ``CREATE VECTOR INDEX`` syntax
        with optional prefix columns and the opclass derived from the
        configured distance metric.
        """
        metric = DistanceMetric(self._config.default_metric)
        opclass = metric.opclass

        index_columns: list[str] = list(self._prefix_columns)
        index_columns.append(f"{self._vector_column} {opclass}")
        columns_clause = ", ".join(index_columns)

        return (
            f"CREATE VECTOR INDEX IF NOT EXISTS "
            f"idx_{self._table}_{self._vector_column} "
            f"ON {self._table} ({columns_clause})"
        )

    def ensure_table(self) -> None:
        """Create the document table and vector index if they do not exist.

        Creates a table with columns: ``id`` (text PK), ``content`` (text),
        ``embedding`` (vector), and ``metadata`` (jsonb).  Also creates a
        vector index using the CockroachDB v26.2+ ``CREATE VECTOR INDEX``
        syntax with the opclass matching the configured distance metric.

        If ``prefix_columns`` were specified at construction time, they are
        included in the index definition for improved filtered-search
        accuracy.

        The method also enables the ``feature.vector_index.enabled`` cluster
        setting and, if ``config.vector_search_beam_size`` is set, configures
        the session-level ``vector_search_beam_size``.
        """
        dimensions = self._config.embedding_dimensions
        with psycopg.connect(self._conninfo) as conn:
            # Enable vector index feature (required for CREATE VECTOR INDEX)
            conn.execute("SET CLUSTER SETTING feature.vector_index.enabled = true")

            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    {self._vector_column} VECTOR({dimensions}),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )

            conn.execute(self._build_vector_index_ddl())

            # Set session-level beam size if configured
            if self._config.vector_search_beam_size is not None:
                conn.execute(
                    f"SET vector_search_beam_size = {self._config.vector_search_beam_size}"
                )

            conn.commit()
            logger.info(
                "Ensured table %s with vector column %s (%d dimensions)",
                self._table,
                self._vector_column,
                dimensions,
            )
