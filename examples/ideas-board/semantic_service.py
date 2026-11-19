"""Semantic search over ideas using the AI module's ``CockroachDBVectorStore`` on a
native ``VECTOR`` column.

A deterministic (no-model) embedding provider keeps the demo reproducible — a real
app swaps in ``OpenAIEmbeddingProvider`` or ``SentenceTransformerEmbeddingProvider``.
Ideas are stored with precomputed embeddings; the query is embedded through the same
provider, and ``similarity_search`` returns the nearest ideas by cosine distance.

Needs CockroachDB with the native ``VECTOR`` type (v25.2+). ``ensure_table()`` also
issues ``CREATE VECTOR INDEX`` (v26.2+); the integration test skips honestly when
the image lacks VECTOR support.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from cockroachdb.ai import CockroachDBVectorStore, Document
from cockroachdb.config import AIConfig

if TYPE_CHECKING:
    from cockroachdb.types import VectorSearchResult

DIMENSIONS = 3
TABLE = "idea_doc"


# tag::embedding-provider[]
class DeterministicEmbeddingProvider:
    """A no-model EmbeddingProvider: fixed text->vector mapping with a hash fallback.

    Satisfies the ``EmbeddingProvider`` protocol (``embed`` / ``embed_batch`` /
    ``dimensions``) so searches are reproducible with no external model or network.
    """

    def __init__(
        self, mapping: dict[str, list[float]], dimensions: int = DIMENSIONS
    ) -> None:
        self._mapping = mapping
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> list[float]:
        if text in self._mapping:
            return self._mapping[text]
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i] / 255.0 for i in range(self._dimensions)]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


# end::embedding-provider[]


# tag::vector-search[]
class SemanticIdeaService:
    """Store ideas with precomputed embeddings; find the nearest by cosine distance."""

    def __init__(self, dsn: str, provider: DeterministicEmbeddingProvider) -> None:
        self._store = CockroachDBVectorStore(
            conninfo=dsn,
            table=TABLE,
            vector_column="embedding",
            embedding_provider=provider,
            config=AIConfig(embedding_dimensions=DIMENSIONS, default_metric="cosine"),
        )

    def initialize(self) -> None:
        """Create the VECTOR table (and index). Safe to call repeatedly."""
        self._store.ensure_table()

    async def store(self, docs: list[Document]) -> list[str]:
        """Upsert ideas carrying precomputed embeddings."""
        return await self._store.add_documents(docs)

    async def find_similar(self, query: str, k: int = 4) -> list[VectorSearchResult]:
        """The ``k`` ideas nearest to ``query``, closest-first."""
        return await self._store.similarity_search(query, limit=k)


# end::vector-search[]
