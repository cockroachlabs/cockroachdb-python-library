"""Retrieval-Augmented Generation pipeline backed by CockroachDB vector search."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from cockroachdb.config import AIConfig

if TYPE_CHECKING:
    from cockroachdb.types import VectorSearchResult

logger = logging.getLogger(__name__)


@runtime_checkable
class ChatProvider(Protocol):
    """Protocol for LLM chat completion providers.

    Implementations must supply a ``complete`` method that accepts a list of
    message dicts (OpenAI-style ``[{"role": ..., "content": ...}]``) and
    returns the assistant's reply as a string.
    """

    async def complete(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class RagResponse:
    """Result of a RAG pipeline query.

    Attributes:
        answer: The generated answer from the LLM.
        sources: Source document IDs used to build context.
        context_documents: Full search results provided as context.
    """

    answer: str
    sources: list[str] = field(default_factory=list)
    context_documents: list[VectorSearchResult] = field(default_factory=list)


class RagPipeline:
    """End-to-end Retrieval-Augmented Generation pipeline.

    Orchestrates the full RAG flow: embed the question, search for relevant
    documents in CockroachDB, build a context prompt, and call the LLM.

    Example::

        from cockroachdb.ai import RagPipeline, CockroachDBVectorStore

        pipeline = RagPipeline(
            vector_store=my_store,
            chat_provider=my_llm,
        )
        response = await pipeline.query("What is CockroachDB?")
        print(response.answer)
    """

    def __init__(
        self,
        vector_store: Any,
        chat_provider: ChatProvider,
        config: AIConfig | None = None,
        *,
        system_prompt: str | None = None,
    ) -> None:
        """Initialise the RAG pipeline.

        Args:
            vector_store: A :class:`CockroachDBVectorStore` or compatible object
                with a ``similarity_search_with_score`` async method.
            chat_provider: LLM provider implementing :class:`ChatProvider`.
            config: Optional AI configuration.
            system_prompt: Custom system prompt. If ``None``, a default prompt
                instructing the model to answer based on context is used.
        """
        self._store = vector_store
        self._chat = chat_provider
        self._config = config or AIConfig()
        self._system_prompt = system_prompt or self._default_system_prompt()

    async def query(self, question: str) -> RagResponse:
        """Execute the full RAG pipeline.

        Steps:
            1. Embed the question and search the vector store.
            2. Filter results below the similarity threshold.
            3. Build a context string from matching documents.
            4. Send system prompt + context + question to the LLM.
            5. Return the answer with source references.

        Args:
            question: The user's natural-language question.

        Returns:
            A :class:`RagResponse` with the answer, sources, and context.
        """
        context_docs = await self._store.similarity_search_with_score(
            question,
            limit=self._config.max_context_documents,
        )

        filtered = [
            doc for doc in context_docs if doc.similarity >= self._config.similarity_threshold
        ]

        if not filtered:
            logger.info("No documents above similarity threshold for: %s", question)
            return RagResponse(
                answer="I don't have enough context to answer that question.",
                sources=[],
                context_documents=[],
            )

        context_text = self._build_context(filtered)
        messages = self._build_messages(question, context_text)

        answer = await self._chat.complete(messages)
        sources = [str(doc.id) for doc in filtered if doc.id is not None]

        logger.info(
            "RAG query completed: %d context docs, %d sources",
            len(filtered),
            len(sources),
        )

        return RagResponse(
            answer=answer,
            sources=sources,
            context_documents=filtered,
        )

    async def query_async(self, question: str) -> RagResponse:
        """Async alias for :meth:`query` (both are async).

        Args:
            question: The user's natural-language question.

        Returns:
            A :class:`RagResponse`.
        """
        return await self.query(question)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, documents: list[VectorSearchResult]) -> str:
        """Concatenate document contents into a context block."""
        parts: list[str] = []
        for i, doc in enumerate(documents, 1):
            content = doc.document.get("content", "")
            source_id = doc.id or f"doc-{i}"
            parts.append(f"[Source {source_id}]\n{content}")
        return "\n\n---\n\n".join(parts)

    def _build_messages(self, question: str, context: str) -> list[dict[str, str]]:
        """Assemble the message list for the LLM."""
        return [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {question}\n\n"
                    "Answer based on the context provided. "
                    "If the context does not contain relevant information, say so."
                ),
            },
        ]

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "You are a helpful assistant that answers questions based on the "
            "provided context documents. Cite your sources using the source "
            "identifiers when possible. If the context does not contain enough "
            "information to answer the question, clearly state that."
        )
