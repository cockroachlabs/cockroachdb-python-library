"""Tests for cockroachdb.ai.rag — RAG pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cockroachdb.ai.rag import RagPipeline, RagResponse
from cockroachdb.config import AIConfig
from cockroachdb.types import VectorSearchResult


class FakeChatProvider:
    """Fake chat provider for testing."""

    async def complete(self, messages: list[dict[str, str]]) -> str:
        return "This is the answer."


class TestRagPipelineQuery:
    """Tests for RagPipeline.query()."""

    @pytest.mark.asyncio
    async def test_full_pipeline_embed_search_chat(self):
        """query() calls similarity_search_with_score -> build context -> chat.complete."""
        mock_store = AsyncMock()
        mock_store.similarity_search_with_score = AsyncMock(
            return_value=[
                VectorSearchResult(
                    id="doc1",
                    document={"content": "CockroachDB is great."},
                    distance=0.1,
                    similarity=0.9,
                ),
            ]
        )

        chat = FakeChatProvider()
        config = AIConfig(similarity_threshold=0.5)
        pipeline = RagPipeline(vector_store=mock_store, chat_provider=chat, config=config)

        response = await pipeline.query("What is CockroachDB?")

        assert isinstance(response, RagResponse)
        assert response.answer == "This is the answer."
        assert "doc1" in response.sources
        assert len(response.context_documents) == 1
        mock_store.similarity_search_with_score.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_no_context_answer_when_below_threshold(self):
        """When all results are below similarity_threshold, a default answer is returned."""
        mock_store = AsyncMock()
        mock_store.similarity_search_with_score = AsyncMock(
            return_value=[
                VectorSearchResult(
                    id="doc1",
                    document={"content": "irrelevant"},
                    distance=0.8,
                    similarity=0.2,
                ),
            ]
        )

        chat = FakeChatProvider()
        config = AIConfig(similarity_threshold=0.5)
        pipeline = RagPipeline(vector_store=mock_store, chat_provider=chat, config=config)

        response = await pipeline.query("Unknown question")

        assert "don't have enough context" in response.answer
        assert response.sources == []
        assert response.context_documents == []

    @pytest.mark.asyncio
    async def test_returns_no_context_answer_when_no_results(self):
        """When search returns empty, a default answer is returned."""
        mock_store = AsyncMock()
        mock_store.similarity_search_with_score = AsyncMock(return_value=[])

        chat = FakeChatProvider()
        pipeline = RagPipeline(vector_store=mock_store, chat_provider=chat)

        response = await pipeline.query("Nothing here")

        assert "don't have enough context" in response.answer

    @pytest.mark.asyncio
    async def test_custom_system_prompt_used(self):
        """Custom system_prompt is sent to the chat provider."""
        mock_store = AsyncMock()
        mock_store.similarity_search_with_score = AsyncMock(
            return_value=[
                VectorSearchResult(
                    id="d1",
                    document={"content": "data"},
                    distance=0.05,
                    similarity=0.95,
                ),
            ]
        )

        mock_chat = AsyncMock()
        mock_chat.complete = AsyncMock(return_value="answer")

        pipeline = RagPipeline(
            vector_store=mock_store,
            chat_provider=mock_chat,
            system_prompt="You are a SQL expert.",
        )

        await pipeline.query("How?")

        messages = mock_chat.complete.call_args[0][0]
        assert messages[0]["content"] == "You are a SQL expert."


class TestRagPipelineBuildContext:
    """Tests for the _build_context helper."""

    def test_concatenates_documents(self):
        pipeline = RagPipeline(
            vector_store=MagicMock(),
            chat_provider=MagicMock(),
        )

        docs = [
            VectorSearchResult(
                id="a", document={"content": "first"}, distance=0.1, similarity=0.9
            ),
            VectorSearchResult(
                id="b", document={"content": "second"}, distance=0.2, similarity=0.8
            ),
        ]

        context = pipeline._build_context(docs)

        assert "[Source a]" in context
        assert "first" in context
        assert "[Source b]" in context
        assert "second" in context
        assert "---" in context

    def test_handles_missing_content(self):
        pipeline = RagPipeline(
            vector_store=MagicMock(),
            chat_provider=MagicMock(),
        )

        docs = [
            VectorSearchResult(id="x", document={}, distance=0.1, similarity=0.9),
        ]

        context = pipeline._build_context(docs)
        assert "[Source x]" in context

    def test_handles_missing_id(self):
        pipeline = RagPipeline(
            vector_store=MagicMock(),
            chat_provider=MagicMock(),
        )

        docs = [
            VectorSearchResult(
                id=None, document={"content": "text"}, distance=0.1, similarity=0.9
            ),
        ]

        context = pipeline._build_context(docs)
        assert "[Source doc-1]" in context


class TestRagPipelineBuildMessages:
    """Tests for the _build_messages helper."""

    def test_returns_system_and_user_messages(self):
        pipeline = RagPipeline(
            vector_store=MagicMock(),
            chat_provider=MagicMock(),
            system_prompt="Be helpful.",
        )

        messages = pipeline._build_messages("What?", "Some context")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Be helpful."
        assert messages[1]["role"] == "user"
        assert "What?" in messages[1]["content"]
        assert "Some context" in messages[1]["content"]

    def test_user_message_includes_instructions(self):
        pipeline = RagPipeline(
            vector_store=MagicMock(),
            chat_provider=MagicMock(),
        )

        messages = pipeline._build_messages("Q?", "ctx")
        user_msg = messages[1]["content"]
        assert "Answer based on the context" in user_msg

    def test_default_system_prompt(self):
        prompt = RagPipeline._default_system_prompt()
        assert "helpful assistant" in prompt
        assert "context" in prompt
