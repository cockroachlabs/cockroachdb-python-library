# Examples

Standalone example scripts demonstrating features of the CockroachDB Python Library.

Each file is self-contained with a docstring explaining prerequisites and usage.

| Example | Description |
|---------|-------------|
| [`basic_retry.py`](basic_retry.py) | `@crdb_retry` decorator with sync/async functions, custom backoff, and `on_retry` callbacks |
| [`regions_and_follower_reads.py`](regions_and_follower_reads.py) | Multi-region context managers, `@crdb_region`, `@follower_read`, and region validation |
| [`sqlalchemy_integration.py`](sqlalchemy_integration.py) | SQLAlchemy engine, session with retry, `RegionalByRowMixin`, `GlobalTableMixin`, follower reads |
| [`circuit_breaker.py`](circuit_breaker.py) | Circuit breaker pattern with custom thresholds, state transitions, and recovery |
| [`cdc_webhook.py`](cdc_webhook.py) | CDC changefeed webhook handlers with `@changefeed_handler` and FastAPI router |
| [`vector_search.py`](vector_search.py) | pgvector similarity search, embedding storage, distance metrics |
| [`rag_pipeline.py`](rag_pipeline.py) | RAG pipeline with OpenAI embeddings, CockroachDB vector store, and LLM integration |
| [`fastapi_app.py`](fastapi_app.py) | Complete FastAPI app with ASGI middleware, retry endpoints, follower reads, and CDC webhooks |
| [`django_app.py`](django_app.py) | Complete Django app with middleware, model mixins, retry-safe writes, database routing, and signals |
| [`testing_demo.py`](testing_demo.py) | Testing utilities: `RetrySimulator`, `ChangefeedEventFactory`, `VectorSearchResultFactory`, `ConcurrencyRunner` |

## Quick start

```bash
# Install the base package
pip install cockroachdb

# Run an example that works without a database
python examples/circuit_breaker.py
python examples/regions_and_follower_reads.py
python examples/testing_demo.py

# For database-connected examples, start CockroachDB first
cockroach start-single-node --insecure --listen-addr=localhost:26257

# For the FastAPI app
pip install cockroachdb-cdc[fastapi] uvicorn
uvicorn examples.fastapi_app:app --port 8000

# For the Django app (demo mode — no browser needed)
pip install cockroachdb cockroachdb-core cockroachdb-django django
python examples/django_app.py

# Django dev server
python examples/django_app.py runserver 8000
```

## Package dependencies by example

| Example | Packages |
|---------|----------|
| `basic_retry.py` | `cockroachdb`, `psycopg[binary]` |
| `regions_and_follower_reads.py` | `cockroachdb`, `cockroachdb-core` |
| `sqlalchemy_integration.py` | `cockroachdb-sqlalchemy`, `sqlalchemy`, `psycopg2-binary` |
| `circuit_breaker.py` | `cockroachdb`, `cockroachdb-core` |
| `cdc_webhook.py` | `cockroachdb`, `cockroachdb-cdc[fastapi]`, `uvicorn` |
| `vector_search.py` | `cockroachdb-ai`, `psycopg[binary]` |
| `rag_pipeline.py` | `cockroachdb-ai`, `psycopg[binary]`, `openai` |
| `fastapi_app.py` | `cockroachdb`, `cockroachdb-core`, `cockroachdb-cdc[fastapi]`, `uvicorn` |
| `django_app.py` | `cockroachdb`, `cockroachdb-core`, `cockroachdb-django`, `django` |
| `testing_demo.py` | `cockroachdb`, `cockroachdb-testing` |
