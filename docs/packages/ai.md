# cockroachdb-ai

Vector search, vector store, RAG pipeline, and embedding support for CockroachDB.

```bash
pip install cockroachdb-ai
```

**Depends on:** `cockroachdb-core`

## VectorSearchTemplate

Execute vector similarity searches against CockroachDB.

```python
from cockroachdb.ai import VectorSearchTemplate

vst = VectorSearchTemplate(
    dsn="postgresql://root@localhost:26257/defaultdb",
    table="documents",
    vector_column="embedding",
)

results = vst.search(query_vector=[0.1, 0.2, 0.3], top_k=5)
for doc in results:
    print(doc.id, doc.distance)
```

## CockroachDBVectorStore

Higher-level vector store with upsert, delete, and search.

```python
from cockroachdb.ai import CockroachDBVectorStore

store = CockroachDBVectorStore(
    dsn="postgresql://root@localhost:26257/defaultdb",
    table="documents",
    vector_column="embedding",
    dimensions=1536,
)

# Insert documents
store.upsert(id="doc-1", vector=[0.1, 0.2, ...], metadata={"title": "Hello"})

# Search
results = store.search(query_vector=[0.1, 0.2, ...], top_k=10)
```

## RAG Pipeline

End-to-end Retrieval-Augmented Generation pipeline.

```python
from cockroachdb.ai import RagPipeline

rag = RagPipeline(
    vector_store=store,
    embedding_fn=my_embedding_function,
)

# Index a document
rag.index("doc-1", "CockroachDB is a distributed SQL database.")

# Query with context retrieval
answer = rag.query("What is CockroachDB?")
```

## Embeddings

Pluggable embedding interface:

```python
from cockroachdb.ai import Embeddings


class OpenAIEmbeddings(Embeddings):
    def embed(self, text: str) -> list[float]:
        # Call OpenAI API
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Batch embedding
        ...
```

## API Summary

| Symbol | Type | Description |
|--------|------|-------------|
| `VectorSearchTemplate` | class | Low-level vector search |
| `CockroachDBVectorStore` | class | Vector store with CRUD |
| `RagPipeline` | class | RAG with retrieval + generation |
| `Embeddings` | protocol | Embedding provider interface |
