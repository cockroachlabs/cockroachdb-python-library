"""Tests for cockroachdb.ai.vector_search — low-level vector similarity search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cockroachdb.types import DistanceMetric, VectorSearchResult


class TestVectorSearchTemplateBuildQuery:
    """Tests for _build_query SQL generation."""

    def test_builds_cosine_query(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        vst = VectorSearchTemplate("postgresql://fake")
        sql, params = vst._build_query(
            table="documents",
            vector_column="embedding",
            query_vector=[0.1, 0.2, 0.3],
            metric=DistanceMetric.COSINE,
            limit=5,
            columns=None,
            filter_sql=None,
            filter_params=None,
        )

        assert "SELECT *" in sql
        assert "<=>" in sql  # cosine operator
        assert "ORDER BY _distance ASC" in sql
        assert "LIMIT" in sql
        assert params[-1] == 5

    def test_builds_l2_query(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        vst = VectorSearchTemplate("postgresql://fake")
        sql, params = vst._build_query(
            table="docs",
            vector_column="vec",
            query_vector=[1.0, 2.0],
            metric=DistanceMetric.EUCLIDEAN,
            limit=10,
            columns=["id", "content"],
            filter_sql=None,
            filter_params=None,
        )

        assert "SELECT id, content" in sql
        assert "<->" in sql  # L2 operator
        assert params[-1] == 10

    def test_builds_inner_product_query(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        vst = VectorSearchTemplate("postgresql://fake")
        sql, _params = vst._build_query(
            table="docs",
            vector_column="emb",
            query_vector=[0.5],
            metric=DistanceMetric.INNER_PRODUCT,
            limit=3,
            columns=None,
            filter_sql=None,
            filter_params=None,
        )

        assert "<#>" in sql  # inner product operator

    def test_includes_filter_sql_and_params(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        vst = VectorSearchTemplate("postgresql://fake")
        sql, params = vst._build_query(
            table="docs",
            vector_column="emb",
            query_vector=[0.1],
            metric=DistanceMetric.COSINE,
            limit=5,
            columns=None,
            filter_sql="category = %s",
            filter_params=["science"],
        )

        assert "WHERE category = %s" in sql
        assert "science" in params


class TestVectorSearchTemplateSearch:
    """Tests for VectorSearchTemplate.search() with mocked DB."""

    @patch("cockroachdb.ai.vector_search.psycopg")
    def test_search_returns_results(self, mock_psycopg):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": "doc1", "content": "hello", "embedding": "[0.1,0.2]", "_distance": 0.1},
        ]
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        vst = VectorSearchTemplate("postgresql://fake")
        results = vst.search(
            table="docs",
            vector_column="embedding",
            query_vector=[0.1, 0.2],
            limit=5,
        )

        assert len(results) == 1
        assert isinstance(results[0], VectorSearchResult)

    @patch("cockroachdb.ai.vector_search.psycopg")
    def test_search_uses_default_limit(self, mock_psycopg):
        from cockroachdb.ai.vector_search import VectorSearchTemplate
        from cockroachdb.config import AIConfig

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        config = AIConfig(default_limit=20)
        vst = VectorSearchTemplate("postgresql://fake", config=config)
        vst.search(table="docs", vector_column="emb", query_vector=[0.1])

        # The limit param should be 20 (from config)
        sql_call = mock_conn.execute.call_args
        assert sql_call[0][1][-1] == 20


class TestVectorSearchTemplateStoreEmbedding:
    """Tests for store_embedding UPSERT."""

    @patch("cockroachdb.ai.vector_search.psycopg")
    def test_store_embedding_upserts(self, mock_psycopg):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        vst = VectorSearchTemplate("postgresql://fake")
        vst.store_embedding(
            table="docs",
            id_column="id",
            id_value="doc1",
            vector_column="embedding",
            embedding=[0.1, 0.2, 0.3],
        )

        sql = mock_conn.execute.call_args[0][0]
        assert "UPSERT INTO docs" in sql
        assert "::vector" in sql
        mock_conn.commit.assert_called_once()

    @patch("cockroachdb.ai.vector_search.psycopg")
    def test_store_embedding_formats_vector_literal(self, mock_psycopg):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        vst = VectorSearchTemplate("postgresql://fake")
        vst.store_embedding("t", "id", "x", "vec", [1.5, 2.5])

        params = mock_conn.execute.call_args[0][1]
        assert params[0] == "x"
        assert params[1] == "[1.5,2.5]"

    @patch("cockroachdb.ai.vector_search.psycopg")
    def test_store_embedding_with_metadata(self, mock_psycopg):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        vst = VectorSearchTemplate("postgresql://fake")
        vst.store_embedding_with_metadata(
            table="docs",
            id_column="id",
            id_value="doc1",
            vector_column="emb",
            embedding=[0.1],
            metadata={"source": "test"},
        )

        sql = mock_conn.execute.call_args[0][0]
        assert "::jsonb" in sql
        mock_conn.commit.assert_called_once()


class TestRowsToResults:
    """Tests for the static _rows_to_results helper."""

    def test_converts_rows(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        rows = [
            {"id": "doc1", "content": "hi", "_distance": 0.15},
            {"id": "doc2", "content": "hey", "_distance": 0.3},
        ]
        results = VectorSearchTemplate._rows_to_results(rows, "embedding", DistanceMetric.COSINE)

        assert len(results) == 2
        assert results[0].distance == pytest.approx(0.15)
        assert results[0].similarity == pytest.approx(1.0 - 0.15)

    def test_removes_distance_and_vector_columns(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        rows = [{"id": "x", "embedding": "[0.1]", "_distance": 0.1}]
        results = VectorSearchTemplate._rows_to_results(rows, "embedding", DistanceMetric.COSINE)

        assert "embedding" not in results[0].document
        assert "_distance" not in results[0].document

    def test_empty_rows(self):
        from cockroachdb.ai.vector_search import VectorSearchTemplate

        results = VectorSearchTemplate._rows_to_results([], "emb", DistanceMetric.COSINE)
        assert results == []
