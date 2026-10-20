"""Tests for cockroachdb.ai.vector_store — high-level vector store."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cockroachdb.ai.vector_store import CockroachDBVectorStore, Document
from cockroachdb.config import AIConfig
from cockroachdb.types import DistanceMetric, VectorSearchResult


class FakeEmbeddingProvider:
    """Fake embedding provider for tests."""

    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    @property
    def dimensions(self) -> int:
        return 3


class TestDocument:
    """Tests for the Document dataclass."""

    def test_auto_generates_id(self):
        doc = Document(content="hello")
        assert doc.id != ""
        assert len(doc.id) > 0

    def test_preserves_given_id(self):
        doc = Document(content="hello", id="my-id")
        assert doc.id == "my-id"

    def test_default_metadata_empty(self):
        doc = Document(content="hello")
        assert doc.metadata == {}

    def test_embedding_default_none(self):
        doc = Document(content="hello")
        assert doc.embedding is None


class TestCockroachDBVectorStoreAddDocuments:
    """Tests for CockroachDBVectorStore.add_documents()."""

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_embeds_documents_without_embeddings(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        docs = [Document(content="doc 1"), Document(content="doc 2")]
        ids = await store.add_documents(docs)

        assert len(ids) == 2
        assert mock_conn.execute.await_count == 2
        mock_conn.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_skips_embedding_for_precomputed(self, mock_psycopg):
        provider = AsyncMock(spec=FakeEmbeddingProvider)
        provider.embed_batch = AsyncMock(return_value=[])
        provider.dimensions = 3

        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        docs = [Document(content="doc 1", embedding=[0.5, 0.6, 0.7])]
        ids = await store.add_documents(docs)

        assert len(ids) == 1
        # embed_batch should not be called since all docs have embeddings
        provider.embed_batch.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_returns_document_ids(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        docs = [Document(content="a", id="id-1"), Document(content="b", id="id-2")]
        ids = await store.add_documents(docs)

        assert ids == ["id-1", "id-2"]


class TestCockroachDBVectorStoreSimilaritySearch:
    """Tests for similarity_search and similarity_search_with_score."""

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_similarity_search_embeds_query(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {"id": "doc1", "content": "hello", "metadata": "{}", "_distance": 0.1},
            ]
        )
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        results = await store.similarity_search("test query")

        assert len(results) == 1
        assert isinstance(results[0], VectorSearchResult)

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_similarity_search_with_score_uses_cosine(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="emb",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(
            return_value=[
                {"id": "d1", "content": "hi", "metadata": {}, "_distance": 0.2},
            ]
        )
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        results = await store.similarity_search_with_score("query")

        assert results[0].distance == pytest.approx(0.2)
        assert results[0].similarity == pytest.approx(0.8)

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_similarity_search_sql_uses_operator(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="emb",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        await store.similarity_search_with_score("q", metric=DistanceMetric.EUCLIDEAN)

        sql = mock_conn.execute.call_args[0][0]
        assert "<->" in sql


class TestCockroachDBVectorStoreEnsureTable:
    """Tests for ensure_table() — CockroachDB v26.2 DDL generation."""

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_uses_create_vector_index(self, mock_psycopg):
        """Verify CREATE VECTOR INDEX syntax (v26.2) replaces old USING hnsw."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        # Should enable vector index feature
        assert any("feature.vector_index.enabled" in s for s in executed_sqls)
        # Should use CREATE VECTOR INDEX (not USING hnsw)
        vector_index_sql = [s for s in executed_sqls if "CREATE VECTOR INDEX" in s]
        assert len(vector_index_sql) == 1
        assert "embedding vector_cosine_ops" in vector_index_sql[0]
        # Should NOT contain old syntax
        assert not any("USING hnsw" in s for s in executed_sqls)
        assert not any("USING cspann" in s for s in executed_sqls)

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_with_prefix_columns(self, mock_psycopg):
        """Verify prefix columns are included in the vector index DDL."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
            prefix_columns=["tenant_id"],
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        vector_index_sql = [s for s in executed_sqls if "CREATE VECTOR INDEX" in s]
        assert len(vector_index_sql) == 1
        assert "tenant_id, embedding vector_cosine_ops" in vector_index_sql[0]

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_with_multiple_prefix_columns(self, mock_psycopg):
        """Verify multiple prefix columns in vector index DDL."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="items",
            vector_column="emb",
            embedding_provider=provider,
            prefix_columns=["department_id", "category_id"],
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        vector_index_sql = [s for s in executed_sqls if "CREATE VECTOR INDEX" in s]
        assert "department_id, category_id, emb vector_cosine_ops" in vector_index_sql[0]

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_l2_metric(self, mock_psycopg):
        """Verify correct opclass for L2 distance metric."""
        provider = FakeEmbeddingProvider()
        config = AIConfig(default_metric="l2")
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
            config=config,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        vector_index_sql = [s for s in executed_sqls if "CREATE VECTOR INDEX" in s]
        assert "embedding vector_l2_ops" in vector_index_sql[0]

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_inner_product_metric(self, mock_psycopg):
        """Verify correct opclass for inner product distance metric."""
        provider = FakeEmbeddingProvider()
        config = AIConfig(default_metric="inner_product")
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
            config=config,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        vector_index_sql = [s for s in executed_sqls if "CREATE VECTOR INDEX" in s]
        assert "embedding vector_ip_ops" in vector_index_sql[0]

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_sets_beam_size(self, mock_psycopg):
        """Verify vector_search_beam_size is set when configured."""
        provider = FakeEmbeddingProvider()
        config = AIConfig(vector_search_beam_size=64)
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
            config=config,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        assert any("vector_search_beam_size = 64" in s for s in executed_sqls)

    @patch("cockroachdb.ai.vector_store.psycopg")
    def test_ensure_table_no_beam_size_when_not_configured(self, mock_psycopg):
        """Verify beam_size SET is skipped when not configured."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        store.ensure_table()

        executed_sqls = [c[0][0] for c in mock_conn.execute.call_args_list]
        assert not any("vector_search_beam_size" in s for s in executed_sqls)

    def test_build_vector_index_ddl_default(self):
        """Test DDL generation with defaults (cosine, no prefix columns)."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )
        ddl = store._build_vector_index_ddl()
        assert ddl == (
            "CREATE VECTOR INDEX IF NOT EXISTS idx_docs_embedding "
            "ON docs (embedding vector_cosine_ops)"
        )

    def test_build_vector_index_ddl_with_prefix(self):
        """Test DDL generation with prefix columns."""
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="items",
            vector_column="emb",
            embedding_provider=provider,
            prefix_columns=["tenant_id", "category"],
        )
        ddl = store._build_vector_index_ddl()
        assert ddl == (
            "CREATE VECTOR INDEX IF NOT EXISTS idx_items_emb "
            "ON items (tenant_id, category, emb vector_cosine_ops)"
        )


class TestCockroachDBVectorStoreDelete:
    """Tests for CockroachDBVectorStore.delete()."""

    @pytest.mark.asyncio
    @patch("cockroachdb.ai.vector_store.psycopg")
    async def test_delete_returns_count(self, mock_psycopg):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 2
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_psycopg.AsyncConnection.connect = AsyncMock(return_value=mock_conn)

        count = await store.delete(["id-1", "id-2"])
        assert count == 2

    @pytest.mark.asyncio
    async def test_delete_empty_list_returns_zero(self):
        provider = FakeEmbeddingProvider()
        store = CockroachDBVectorStore(
            conninfo="postgresql://fake",
            table="docs",
            vector_column="embedding",
            embedding_provider=provider,
        )

        count = await store.delete([])
        assert count == 0
