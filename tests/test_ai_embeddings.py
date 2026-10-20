"""Tests for cockroachdb.ai.embeddings — embedding providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cockroachdb.ai.embeddings import LocalEmbeddingProvider, OpenAIEmbeddingProvider


class TestLocalEmbeddingProvider:
    """Tests for LocalEmbeddingProvider stub."""

    def test_dimensions_raises_not_implemented(self):
        provider = LocalEmbeddingProvider()
        with pytest.raises(NotImplementedError, match="stub"):
            _ = provider.dimensions

    @pytest.mark.asyncio
    async def test_embed_raises_not_implemented(self):
        provider = LocalEmbeddingProvider()
        with pytest.raises(NotImplementedError, match="stub"):
            await provider.embed("hello")

    @pytest.mark.asyncio
    async def test_embed_batch_raises_not_implemented(self):
        provider = LocalEmbeddingProvider()
        with pytest.raises(NotImplementedError, match="stub"):
            await provider.embed_batch(["hello", "world"])


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAIEmbeddingProvider with mocked openai client."""

    def test_dimensions_property(self):
        mock_client = MagicMock()
        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            dimensions=768,
            client=mock_client,
        )
        assert provider.dimensions == 768

    def test_default_dimensions(self):
        mock_client = MagicMock()
        provider = OpenAIEmbeddingProvider(client=mock_client)
        assert provider.dimensions == 1536

    @pytest.mark.asyncio
    async def test_embed_calls_openai_api(self):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_data = MagicMock()
        mock_data.embedding = [0.1, 0.2, 0.3]
        mock_response.data = [mock_data]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            dimensions=3,
            client=mock_client,
        )

        result = await provider.embed("Hello, world!")

        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_awaited_once_with(
            model="text-embedding-3-small",
            input="Hello, world!",
            dimensions=3,
        )

    @pytest.mark.asyncio
    async def test_embed_batch_returns_ordered_results(self):
        mock_client = AsyncMock()
        mock_item_0 = MagicMock()
        mock_item_0.index = 0
        mock_item_0.embedding = [0.1]

        mock_item_1 = MagicMock()
        mock_item_1.index = 1
        mock_item_1.embedding = [0.2]

        mock_response = MagicMock()
        # Return in reversed order to test sorting
        mock_response.data = [mock_item_1, mock_item_0]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        provider = OpenAIEmbeddingProvider(
            model="test-model",
            dimensions=1,
            client=mock_client,
        )

        result = await provider.embed_batch(["a", "b"])

        assert result == [[0.1], [0.2]]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_input(self):
        mock_client = AsyncMock()
        provider = OpenAIEmbeddingProvider(client=mock_client)

        result = await provider.embed_batch([])
        assert result == []
        mock_client.embeddings.create.assert_not_awaited()

    def test_raises_import_error_without_openai(self):
        """ImportError is raised when openai package is not available."""
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(ImportError, match="openai"):
                OpenAIEmbeddingProvider(api_key="sk-fake")

    def test_custom_model_stored(self):
        mock_client = MagicMock()
        provider = OpenAIEmbeddingProvider(
            model="text-embedding-ada-002",
            client=mock_client,
        )
        assert provider._model == "text-embedding-ada-002"
