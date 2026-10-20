"""Embedding providers for CockroachDB AI vector operations."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider:
    """Stub embedding provider that raises NotImplementedError.

    Serves as a placeholder — users must supply their own provider that
    implements the :class:`~cockroachdb.types.EmbeddingProvider` protocol.

    Example::

        class MyProvider:
            async def embed(self, text: str) -> list[float]:
                return my_model.encode(text).tolist()

            async def embed_batch(self, texts: list[str]) -> list[list[float]]:
                return [self.embed(t) for t in texts]

            @property
            def dimensions(self) -> int:
                return 384
    """

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions.

        Raises:
            NotImplementedError: Always. Subclass or replace with a real provider.
        """
        raise NotImplementedError(
            "LocalEmbeddingProvider is a stub. Provide a real EmbeddingProvider implementation."
        )

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "LocalEmbeddingProvider is a stub. Provide a real EmbeddingProvider implementation."
        )

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "LocalEmbeddingProvider is a stub. Provide a real EmbeddingProvider implementation."
        )


class SentenceTransformerEmbeddingProvider:
    """Embedding provider wrapping the sentence-transformers library.

    Runs models locally on CPU or GPU. Requires the ``sentence-transformers``
    package. Install with::

        pip install cockroachdb-ai[local]

    Example::

        from cockroachdb.ai import SentenceTransformerEmbeddingProvider

        provider = SentenceTransformerEmbeddingProvider()
        vector = await provider.embed("Hello, world!")

    Raises:
        ImportError: If ``sentence-transformers`` is not installed.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimensions: int = 384,
    ) -> None:
        """Initialise the sentence-transformers embedding provider.

        Args:
            model_name: HuggingFace model identifier.
            dimensions: Expected output vector dimensions for the model.
        """
        self._dimensions = dimensions
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "The sentence-transformers package is required for "
                "SentenceTransformerEmbeddingProvider. "
                "Install it with: pip install cockroachdb-ai[local]"
            ) from exc
        self._model = SentenceTransformer(model_name)

    @property
    def dimensions(self) -> int:
        """Number of dimensions in the output vectors."""
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string using the local model.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        vector: Any = self._model.encode(text)
        return vector.tolist()  # type: ignore[no-any-return]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors, one per input text, in the same order.
        """
        if not texts:
            return []
        vectors: Any = self._model.encode(texts)
        return [v.tolist() for v in vectors]  # type: ignore[union-attr]


class OpenAIEmbeddingProvider:
    """Embedding provider wrapping the OpenAI embeddings API.

    Requires the ``openai`` package to be installed. Install with::

        pip install cockroachdb-ai[openai]

    Example::

        from cockroachdb.ai import OpenAIEmbeddingProvider

        provider = OpenAIEmbeddingProvider(
            api_key="sk-...",
            model="text-embedding-3-small",
        )
        vector = await provider.embed("Hello, world!")
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        *,
        client: Any | None = None,
    ) -> None:
        """Initialise the OpenAI embedding provider.

        Args:
            api_key: OpenAI API key. If ``None``, the ``openai`` library reads
                from the ``OPENAI_API_KEY`` environment variable.
            model: Embedding model name.
            dimensions: Output vector dimensions.
            client: Optional pre-configured ``openai.AsyncOpenAI`` client.
                If provided, ``api_key`` is ignored.
        """
        self._model = model
        self._dimensions = dimensions

        if client is not None:
            self._client = client
        else:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "The openai package is required for OpenAIEmbeddingProvider. "
                    "Install it with: pip install cockroachdb-ai[openai]"
                ) from exc
            self._client = openai.AsyncOpenAI(api_key=api_key)

    @property
    def dimensions(self) -> int:
        """Number of dimensions in the output vectors."""
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string via the OpenAI API.

        Args:
            text: Input text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call.

        Args:
            texts: List of input texts.

        Returns:
            List of embedding vectors, one per input text, in the same order.
        """
        if not texts:
            return []

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [item.embedding for item in sorted_data]
