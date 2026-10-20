"""RAG (Retrieval-Augmented Generation) pipeline example.

Demonstrates building a RAG pipeline backed by CockroachDB:
    - ``OpenAIEmbeddingProvider`` for generating embeddings via OpenAI
    - ``CockroachDBVectorStore`` for document storage and retrieval
    - ``RagPipeline`` for end-to-end question answering
    - Custom ``ChatProvider`` for LLM integration

The RAG flow:
    1. Embed the user's question using the embedding provider
    2. Search CockroachDB for relevant documents (vector similarity)
    3. Build a context prompt from the retrieved documents
    4. Send the context + question to an LLM for answer generation

Prerequisites:
    pip install cockroachdb-ai psycopg[binary] openai

    Set the OPENAI_API_KEY environment variable.

    CockroachDB v26.2+ with vector index support:
        SET CLUSTER SETTING feature.vector_index.enabled = true;

Usage:
    export OPENAI_API_KEY=sk-...
    python examples/rag_pipeline.py
"""

from __future__ import annotations

import os

from cockroachdb.ai import (
    ChatProvider,
    CockroachDBVectorStore,
    Document,
    OpenAIEmbeddingProvider,
    RagPipeline,
    RagResponse,
)

# Connection string
CONN_STRING = "postgresql://root@localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# 1. Set up the embedding provider
# ---------------------------------------------------------------------------


def create_embedding_provider() -> OpenAIEmbeddingProvider:
    """Create an OpenAI embedding provider.

    Uses the ``text-embedding-3-small`` model by default (1536 dimensions).
    The API key is read from the ``OPENAI_API_KEY`` environment variable
    or can be passed directly.
    """
    return OpenAIEmbeddingProvider(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="text-embedding-3-small",
        dimensions=1536,
    )


# ---------------------------------------------------------------------------
# 2. Set up the vector store
# ---------------------------------------------------------------------------


def create_vector_store(
    embedding_provider: OpenAIEmbeddingProvider,
) -> CockroachDBVectorStore:
    """Create a CockroachDB-backed vector store.

    The store manages a table with columns for document ID, content,
    embedding vector, and optional JSONB metadata.

    ``ensure_table()`` creates the table and vector index using the
    CockroachDB v26.2+ ``CREATE VECTOR INDEX`` syntax.  It also
    enables the ``feature.vector_index.enabled`` cluster setting.

    Prefix columns can be specified to improve filtered-search
    accuracy. For example, if you filter by ``topic``, pass
    ``prefix_columns=["topic"]`` so the vector index includes that
    column.
    """
    store = CockroachDBVectorStore(
        conninfo=CONN_STRING,
        table="rag_documents",
        vector_column="embedding",
        embedding_provider=embedding_provider,
        # Uncomment to create a prefix-column vector index:
        # prefix_columns=["topic"],
    )

    # Create the table and vector index if they don't exist
    store.ensure_table()

    return store


# ---------------------------------------------------------------------------
# 3. Add documents to the store
# ---------------------------------------------------------------------------


async def add_sample_documents(store: CockroachDBVectorStore) -> None:
    """Add documents to the vector store.

    Each ``Document`` has content and optional metadata. The store
    automatically generates embeddings using the configured provider
    and stores them in CockroachDB.
    """
    documents = [
        Document(
            content="CockroachDB is a distributed SQL database designed for "
            "cloud-native applications. It provides horizontal scalability, "
            "strong consistency, and survivability across data centers.",
            metadata={"source": "docs", "topic": "overview"},
        ),
        Document(
            content="CockroachDB uses a multi-active availability architecture "
            "where every node can serve reads and writes. There is no "
            "single point of failure.",
            metadata={"source": "docs", "topic": "architecture"},
        ),
        Document(
            content="CockroachDB supports multi-region deployments with REGIONAL "
            "BY ROW tables, GLOBAL tables, and follower reads for low-latency "
            "access patterns.",
            metadata={"source": "docs", "topic": "multi-region"},
        ),
        Document(
            content="pgvector is a PostgreSQL extension that adds support for "
            "vector similarity search. CockroachDB supports pgvector for "
            "AI/ML workloads.",
            metadata={"source": "blog", "topic": "vector-search"},
        ),
        Document(
            content="CockroachDB Changefeeds (CDC) stream row-level changes "
            "in real time. They support webhook sinks, Kafka, and "
            "cloud storage destinations.",
            metadata={"source": "docs", "topic": "cdc"},
        ),
    ]

    await store.add_documents(documents)
    print(f"  Added {len(documents)} documents to the vector store")


# ---------------------------------------------------------------------------
# 4. Define a ChatProvider for the LLM
# ---------------------------------------------------------------------------


class OpenAIChatProvider:
    """Chat provider wrapping the OpenAI chat completions API.

    Implements the ``ChatProvider`` protocol required by ``RagPipeline``.
    The protocol requires a single ``complete`` method that accepts
    OpenAI-style message dicts and returns the assistant's reply.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        try:
            import openai

            self._client = openai.AsyncOpenAI()
        except ImportError:
            raise ImportError("Install openai: pip install openai")
        self._model = model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Send messages to OpenAI and return the assistant's reply."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.3,
        )
        return response.choices[0].message.content or ""


class MockChatProvider:
    """Mock chat provider for testing without an API key.

    Returns a canned response that includes the context documents,
    demonstrating the RAG flow without calling an actual LLM.
    """

    async def complete(self, messages: list[dict[str, str]]) -> str:
        # Extract context from the system message
        context = "no context found"
        for msg in messages:
            if msg["role"] == "system" and "Context:" in msg["content"]:
                context = msg["content"].split("Context:")[-1][:200]
                break

        user_question = messages[-1]["content"] if messages else "unknown"
        return (
            f"[Mock LLM Response]\n"
            f"Question: {user_question}\n"
            f"Based on context: {context.strip()[:100]}..."
        )


# ---------------------------------------------------------------------------
# 5. Build and run the RAG pipeline
# ---------------------------------------------------------------------------


async def run_rag_pipeline(
    store: CockroachDBVectorStore,
    chat_provider: ChatProvider,
) -> None:
    """Build a RAG pipeline and answer questions.

    The pipeline:
        1. Embeds the question using the store's embedding provider
        2. Searches CockroachDB for the top-k most similar documents
        3. Builds a context prompt from the retrieved documents
        4. Sends context + question to the chat provider
    """
    pipeline = RagPipeline(
        vector_store=store,
        chat_provider=chat_provider,
        system_prompt=(
            "You are a CockroachDB expert. Answer questions using only "
            "the provided context. If the context doesn't contain the "
            "answer, say so."
        ),
    )

    # Ask questions
    questions = [
        "What is CockroachDB?",
        "How does CockroachDB handle multi-region deployments?",
        "What is pgvector used for in CockroachDB?",
    ]

    for question in questions:
        print(f"\n  Q: {question}")
        response: RagResponse = await pipeline.query(question)
        print(f"  A: {response.answer[:200]}...")
        print(f"  Sources: {response.sources}")
        print(f"  Context docs: {len(response.context_documents)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB RAG Pipeline Example ===\n")

    # Check for OpenAI API key
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))

    if has_api_key:
        print("OpenAI API key found. Using real providers.\n")
        print("To run the full pipeline, ensure CockroachDB is running")
        print("with pgvector enabled.\n")

        # Uncomment to run with real providers:
        # provider = create_embedding_provider()
        # store = create_vector_store(provider)
        # await add_sample_documents(store)
        # chat = OpenAIChatProvider()
        # asyncio.run(run_rag_pipeline(store, chat))
    else:
        print("No OPENAI_API_KEY set. Showing mock pipeline flow.\n")
        print("Set OPENAI_API_KEY to use real embeddings and LLM.\n")

    # Demonstrate the mock flow (no API key needed)
    print("--- Mock RAG pipeline demonstration ---")
    print("  The pipeline would:")
    print("  1. Embed the question with OpenAIEmbeddingProvider")
    print("  2. Search CockroachDB for similar documents")
    print("  3. Build context from retrieved documents")
    print("  4. Send context + question to the LLM")
    print("  5. Return RagResponse with answer, sources, and context docs")

    print("\nDone.")
