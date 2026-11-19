"""Integration test for semantic search — needs a VECTOR-capable CockroachDB.

The native ``VECTOR`` type requires v25.2+; ``ensure_table()`` also issues
``CREATE VECTOR INDEX`` (v26.2+). Boots the image named by ``CRDB_VECTOR_IMAGE``
(default ``cockroachdb/cockroach:latest-v25.2``). Skips cleanly when Docker is
unavailable, and skips honestly (rather than faking a pass) if the chosen image
lacks VECTOR support. Mirrors the Java ``SemanticSearchIT``.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from semantic_service import DeterministicEmbeddingProvider, SemanticIdeaService

from cockroachdb.ai import Document

IMAGE = os.environ.get("CRDB_VECTOR_IMAGE", "cockroachdb/cockroach:latest-v25.2")

# Four deterministic 3-dim vectors pointing in distinct directions.
DOCS = {
    "dark-mode": ("Dark mode toggle", [1.0, 0.0, 0.0]),
    "mobile": ("Mobile dark theme", [0.8, 0.2, 0.0]),
    "search": ("Full-text search", [0.0, 1.0, 0.0]),
    "export": ("CSV export", [0.0, 0.0, 1.0]),
}
QUERY = "near dark mode"
QUERY_VEC = [0.95, 0.05, 0.0]


@pytest.fixture(scope="module")
def dsn() -> str:
    try:
        from crdb_container import insecure_crdb
    except Exception as exc:
        pytest.skip(f"testcontainers unavailable: {exc}")
    try:
        with insecure_crdb(image=IMAGE) as url:
            yield url
    except Exception as exc:
        pytest.skip(f"Docker/CockroachDB container unavailable: {exc}")


def _skip_if_no_vector(exc: Exception) -> None:
    if "vector" in str(exc).lower():
        pytest.skip(f"VECTOR unsupported on {IMAGE}: {exc}")
    raise exc


# tag::semantic-it[]
def test_find_similar_returns_nearest_first(dsn: str) -> None:
    provider = DeterministicEmbeddingProvider({QUERY: QUERY_VEC})
    service = SemanticIdeaService(dsn, provider)
    try:
        service.initialize()
    except Exception as exc:
        _skip_if_no_vector(exc)

    docs = [Document(id=k, content=t, embedding=v) for k, (t, v) in DOCS.items()]
    asyncio.run(service.store(docs))

    hits = asyncio.run(service.find_similar(QUERY, k=4))

    assert [h.id for h in hits] == ["dark-mode", "mobile", "search", "export"]
    distances = [h.distance for h in hits]
    assert distances == sorted(distances)  # closest-first
    assert hits[0].distance < 0.01  # query sits almost on dark-mode


# end::semantic-it[]
