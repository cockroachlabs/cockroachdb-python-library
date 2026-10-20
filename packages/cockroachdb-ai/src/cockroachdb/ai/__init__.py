"""CockroachDB AI — vector search, RAG pipelines, and embedding providers for pgvector."""

from __future__ import annotations

from cockroachdb.ai.embeddings import (
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from cockroachdb.ai.metrics import AIMetrics, InMemoryAIMetrics, NoopAIMetrics
from cockroachdb.ai.rag import ChatProvider, RagPipeline, RagResponse
from cockroachdb.ai.vector_search import VectorSearchTemplate
from cockroachdb.ai.vector_store import CockroachDBVectorStore, Document

__all__ = [
    "AIMetrics",
    "ChatProvider",
    "CockroachDBVectorStore",
    "Document",
    "InMemoryAIMetrics",
    "LocalEmbeddingProvider",
    "NoopAIMetrics",
    "OpenAIEmbeddingProvider",
    "RagPipeline",
    "RagResponse",
    "SentenceTransformerEmbeddingProvider",
    "VectorSearchTemplate",
]
