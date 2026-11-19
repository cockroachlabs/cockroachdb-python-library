"""Fast unit test for semantic search — no Docker, no database.

Covers the deterministic embedding provider (reproducible, right width) and the
``Document`` mapping that carries a precomputed embedding, plus the cosine
similarity ordering. Real similarity search over a VECTOR column needs a
vector-capable cluster (see ``test_semantic_it.py``). Mirrors the Java semantic
unit test.
"""

from __future__ import annotations

import asyncio

from semantic_service import DIMENSIONS, DeterministicEmbeddingProvider

from cockroachdb.ai import Document
from cockroachdb.types import DistanceMetric


# tag::semantic-unit-test[]
def test_provider_is_deterministic_and_right_width() -> None:
    provider = DeterministicEmbeddingProvider({"dark mode": [1.0, 0.0, 0.0]})
    v1 = asyncio.run(provider.embed("dark mode"))
    v2 = asyncio.run(provider.embed("dark mode"))
    assert v1 == v2 == [1.0, 0.0, 0.0]  # mapped text is stable
    assert provider.dimensions == DIMENSIONS
    assert len(asyncio.run(provider.embed("unmapped"))) == DIMENSIONS  # hash fallback width


def test_document_carries_precomputed_embedding() -> None:
    doc = Document(content="Dark mode toggle", embedding=[1.0, 0.0, 0.0])
    assert doc.embedding == [1.0, 0.0, 0.0]  # passed through, not regenerated
    assert doc.id  # auto-assigned uuid when omitted


def test_cosine_similarity_is_monotonic_in_distance() -> None:
    cos = DistanceMetric.COSINE
    assert cos.to_similarity(0.0) > cos.to_similarity(0.5)  # nearer => more similar


# end::semantic-unit-test[]
