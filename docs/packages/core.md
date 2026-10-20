# cockroachdb-core

The engine layer: retry logic, circuit breaker, transaction template, region context, follower reads, ASGI middleware, and metrics.

```bash
pip install cockroachdb-core
```

**Depends on:** `cockroachdb` (base), `psycopg[binary]`

## RetryEngine

Low-level retry engine used internally by `@crdb_retry` and `CockroachDBTemplate`.

```python
from cockroachdb.core import RetryEngine

engine = RetryEngine(max_retries=5, base_delay=0.1)
engine.execute(conn, my_transaction_fn)
```

## CockroachDBTemplate

Programmatic transaction execution with automatic retry.

```python
from cockroachdb.core import CockroachDBTemplate

template = CockroachDBTemplate("postgresql://root@localhost:26257/defaultdb")


def do_work(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO events (name) VALUES ('click')")


template.execute(do_work)
```

## CircuitBreaker

Protects against cascading failures by tracking error rates.

```python
from cockroachdb.core import CircuitBreaker

breaker = CircuitBreaker(threshold=5, reset_timeout=30.0)

with breaker:
    conn.execute("SELECT 1")
```

**States:** `CLOSED` (normal) -> `OPEN` (failing) -> `HALF_OPEN` (probing)

## RegionContext

Thread-safe region context using `contextvars`.

```python
from cockroachdb.core import RegionContext

with RegionContext("us-east1"):
    # All operations in this block use us-east1
    template.execute(do_work)
```

## FollowerReadContext

Enable follower reads within a context.

```python
from cockroachdb.core import FollowerReadContext

with FollowerReadContext():
    rows = template.query("SELECT * FROM products")
```

## CockroachDBMiddleware (ASGI)

FastAPI/Starlette middleware that sets region context from headers.

```python
from fastapi import FastAPI
from cockroachdb.core import CockroachDBMiddleware

app = FastAPI()
app.add_middleware(CockroachDBMiddleware)


@app.get("/users")
async def list_users():
    # Region is set from X-CockroachDB-Region header
    ...
```

## Metrics

Optional Prometheus metrics (install with `pip install cockroachdb-core[metrics]`).

```python
from cockroachdb.core import metrics

# Exposes: crdb_retries_total, crdb_circuit_breaker_state, crdb_transaction_duration_seconds
```

## API Summary

| Class | Description |
|-------|-------------|
| `RetryEngine` | Core retry logic with backoff |
| `CockroachDBTemplate` | Transaction template with retry |
| `CircuitBreaker` | Circuit breaker pattern |
| `RegionContext` | Region context manager |
| `FollowerReadContext` | Follower read context manager |
| `CockroachDBMiddleware` | ASGI middleware |
