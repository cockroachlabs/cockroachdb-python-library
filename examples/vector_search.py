"""Vector search example.

Demonstrates CockroachDB's pgvector integration for similarity search:
    - ``VectorSearchTemplate`` for low-level vector operations
    - Storing embeddings with ``store_embedding()``
    - Similarity search with ``search()``
    - Using ``DistanceMetric`` enum (COSINE, EUCLIDEAN, INNER_PRODUCT)
    - Async search with ``search_async()``

Prerequisites:
    pip install cockroachdb-ai psycopg[binary]

    CockroachDB v26.2+ with vector index support enabled:
        SET CLUSTER SETTING feature.vector_index.enabled = true;

    Create the documents table with a vector index (v26.2 syntax):
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            title TEXT,
            embedding VECTOR(3),
            category TEXT
        );

        -- CockroachDB v26.2 uses CREATE VECTOR INDEX (replaces USING cspann/hnsw)
        CREATE VECTOR INDEX ON documents (embedding vector_cosine_ops);

        -- With prefix columns for filtered queries:
        CREATE VECTOR INDEX ON documents (category, embedding vector_cosine_ops);

Usage:
    python examples/vector_search.py
"""

from __future__ import annotations

from cockroachdb import DistanceMetric
from cockroachdb.ai import VectorSearchTemplate

# Connection string — adjust for your CockroachDB instance
CONN_STRING = "postgresql://root@localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# 1. Setting up VectorSearchTemplate
# ---------------------------------------------------------------------------


def create_template() -> VectorSearchTemplate:
    """Create a VectorSearchTemplate instance.

    The template provides low-level vector operations (search, store)
    against any CockroachDB table with a pgvector column.
    """
    return VectorSearchTemplate(CONN_STRING)


# ---------------------------------------------------------------------------
# 2. Storing embeddings
# ---------------------------------------------------------------------------


def demonstrate_store_embeddings(vst: VectorSearchTemplate) -> None:
    """Store vector embeddings in CockroachDB.

    ``store_embedding()`` uses UPSERT, so it's idempotent — safe to
    call multiple times with the same ID.
    """
    print("--- Storing embeddings ---")

    # Store individual embeddings
    embeddings = [
        ("doc-1", [0.1, 0.2, 0.3]),
        ("doc-2", [0.4, 0.5, 0.6]),
        ("doc-3", [0.7, 0.8, 0.9]),
        ("doc-4", [0.15, 0.25, 0.35]),
    ]

    for doc_id, embedding in embeddings:
        vst.store_embedding(
            table="documents",
            id_column="id",
            id_value=doc_id,
            vector_column="embedding",
            embedding=embedding,
        )
        print(f"  Stored embedding for {doc_id}: {embedding}")

    print()


# ---------------------------------------------------------------------------
# 3. Similarity search with cosine distance
# ---------------------------------------------------------------------------


def demonstrate_cosine_search(vst: VectorSearchTemplate) -> None:
    """Run a cosine similarity search.

    Cosine distance measures the angle between vectors, ignoring
    magnitude. Values range from 0 (identical) to 2 (opposite).
    Similarity = 1 - distance.
    """
    print("--- Cosine similarity search ---")

    query_vector = [0.12, 0.22, 0.32]

    results = vst.search(
        table="documents",
        vector_column="embedding",
        query_vector=query_vector,
        metric=DistanceMetric.COSINE,
        limit=3,
    )

    for r in results:
        print(f"  ID: {r.id}, distance: {r.distance:.4f}, similarity: {r.similarity:.4f}")

    print()


# ---------------------------------------------------------------------------
# 4. Euclidean (L2) distance search
# ---------------------------------------------------------------------------


def demonstrate_l2_search(vst: VectorSearchTemplate) -> None:
    """Run an L2 (Euclidean) distance search.

    L2 distance measures the straight-line distance between points.
    Smaller values mean more similar vectors.
    """
    print("--- L2 (Euclidean) distance search ---")

    query_vector = [0.4, 0.5, 0.6]

    results = vst.search(
        table="documents",
        vector_column="embedding",
        query_vector=query_vector,
        metric=DistanceMetric.EUCLIDEAN,
        limit=3,
    )

    for r in results:
        print(f"  ID: {r.id}, distance: {r.distance:.4f}, similarity: {r.similarity:.4f}")

    print()


# ---------------------------------------------------------------------------
# 5. Inner product search
# ---------------------------------------------------------------------------


def demonstrate_inner_product_search(vst: VectorSearchTemplate) -> None:
    """Run an inner product search.

    Inner product measures the projection of one vector onto another.
    Higher values (less negative distance) mean more similar vectors.
    """
    print("--- Inner product search ---")

    query_vector = [0.5, 0.5, 0.5]

    results = vst.search(
        table="documents",
        vector_column="embedding",
        query_vector=query_vector,
        metric=DistanceMetric.INNER_PRODUCT,
        limit=3,
    )

    for r in results:
        print(f"  ID: {r.id}, distance: {r.distance:.4f}, similarity: {r.similarity:.4f}")

    print()


# ---------------------------------------------------------------------------
# 6. Filtered search
# ---------------------------------------------------------------------------


def demonstrate_filtered_search(vst: VectorSearchTemplate) -> None:
    """Run a similarity search with SQL filter predicates.

    You can combine vector similarity with traditional SQL filters
    to narrow results by metadata columns.
    """
    print("--- Filtered similarity search ---")

    query_vector = [0.1, 0.2, 0.3]

    results = vst.search(
        table="documents",
        vector_column="embedding",
        query_vector=query_vector,
        metric=DistanceMetric.COSINE,
        limit=5,
        filter_sql="category = %s",
        filter_params=["technical"],
    )

    for r in results:
        print(f"  ID: {r.id}, distance: {r.distance:.4f}")

    print()


# ---------------------------------------------------------------------------
# 7. Select specific columns
# ---------------------------------------------------------------------------


def demonstrate_column_selection(vst: VectorSearchTemplate) -> None:
    """Return only specific columns from the search results.

    By default, all columns are returned. Pass ``columns`` to limit
    the result set and reduce data transfer.
    """
    print("--- Column selection ---")

    results = vst.search(
        table="documents",
        vector_column="embedding",
        query_vector=[0.1, 0.2, 0.3],
        columns=["id", "title"],
        limit=3,
    )

    for r in results:
        print(f"  ID: {r.id}, document: {r.document}")

    print()


# ---------------------------------------------------------------------------
# 8. Distance metric operators
# ---------------------------------------------------------------------------


def demonstrate_distance_metrics() -> None:
    """Show the SQL operators and similarity conversion for each metric.

    Each DistanceMetric maps to a pgvector SQL operator:
        - COSINE    -> <=>  (cosine distance)
        - EUCLIDEAN -> <->  (L2 distance)
        - INNER_PRODUCT -> <#>  (negative inner product)
    """
    print("--- Distance metric details ---")

    for metric in DistanceMetric:
        print(f"  {metric.name}:")
        print(f"    Value: {metric.value}")
        print(f"    SQL operator: {metric.operator}")
        print(f"    Similarity(0.25): {metric.to_similarity(0.25):.4f}")

    print()


# ---------------------------------------------------------------------------
# 9. Async search
# ---------------------------------------------------------------------------


async def demonstrate_async_search(vst: VectorSearchTemplate) -> None:
    """Run an asynchronous vector search.

    ``search_async()`` uses psycopg's AsyncConnection for non-blocking
    I/O — ideal for FastAPI and other async frameworks.
    """
    print("--- Async similarity search ---")

    results = await vst.search_async(
        table="documents",
        vector_column="embedding",
        query_vector=[0.1, 0.2, 0.3],
        metric=DistanceMetric.COSINE,
        limit=3,
    )

    for r in results:
        print(f"  ID: {r.id}, distance: {r.distance:.4f}, similarity: {r.similarity:.4f}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB Vector Search Examples ===\n")

    # Distance metric details work without a database
    demonstrate_distance_metrics()

    # The remaining examples require CockroachDB with pgvector.
    # Uncomment below when connected to a real cluster:

    # vst = create_template()
    # demonstrate_store_embeddings(vst)
    # demonstrate_cosine_search(vst)
    # demonstrate_l2_search(vst)
    # demonstrate_inner_product_search(vst)
    # demonstrate_filtered_search(vst)
    # demonstrate_column_selection(vst)
    # asyncio.run(demonstrate_async_search(vst))

    print("Done.")
