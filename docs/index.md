# CockroachDB Python Library

Production-grade Python toolkit for CockroachDB. Automatic serialization retries, circuit breakers, multi-region support, CDC webhooks, and AI/vector search -- all in composable packages.

## Architecture

<p align="center">
  <img src="architecture.svg" alt="Architecture" width="900"/>
</p>

<p align="center">
  <img src="flow.svg" alt="Request Flow" width="900"/>
</p>

## Features

- **`@crdb_retry`** -- decorator-based serialization retry with exponential backoff
- **`CockroachDBTemplate`** -- programmatic transaction template (like Spring's `JdbcTemplate`)
- **Circuit breaker** -- protect against cascading failures
- **Multi-region** -- `@crdb_region`, `@regional_by_row`, `@global_table`
- **Follower reads** -- `@follower_read` for low-latency stale reads
- **SQLAlchemy integration** -- retry-aware engine and session
- **CDC webhooks** -- `@changefeed_handler` for real-time event routing
- **Vector search** -- `VectorSearchTemplate` and `CockroachDBVectorStore`
- **RAG pipeline** -- `RagPipeline` with embedding support
- **ASGI middleware** -- `CockroachDBMiddleware` for FastAPI/Starlette
- **Testing** -- `CockroachDBFixture` (Testcontainers), `RetrySimulator`, factories

## Quick Install

```bash
# Base package (decorators, types, config)
pip install cockroachdb

# Core engine (retry, circuit breaker, template)
pip install cockroachdb-core

# All packages
pip install cockroachdb cockroachdb-core cockroachdb-sqlalchemy cockroachdb-cdc cockroachdb-ai cockroachdb-testing
```

## Package Dependency Graph

```
cockroachdb-testing ───────────────────────────────┐
                                                   │
cockroachdb-sqlalchemy ──┐                    cockroachdb
cockroachdb-cdc ─────────┼──► cockroachdb-core ──► (base)
cockroachdb-ai ──────────┘
```

Install only what you need. Each package declares its dependencies explicitly.

## Quick Example

```python
from cockroachdb import crdb_retry


@crdb_retry(max_retries=5, base_delay=0.1)
def transfer(conn, from_id: int, to_id: int, amount: float) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_id))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_id))
    conn.commit()
```

See [Getting Started](getting-started.md) for full setup instructions.
