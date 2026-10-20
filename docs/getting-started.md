# Getting Started

## Prerequisites

- Python 3.11+
- A running CockroachDB cluster (local or cloud)

## Installation

```bash
# Minimal: just the base decorators and types
pip install cockroachdb

# Core: adds retry engine, circuit breaker, template
pip install cockroachdb-core

# With SQLAlchemy support
pip install cockroachdb-sqlalchemy

# Everything
pip install cockroachdb cockroachdb-core cockroachdb-sqlalchemy cockroachdb-cdc cockroachdb-ai cockroachdb-testing
```

For development, clone the monorepo and use [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/cockroachdb/cockroachdb-python-library.git
cd cockroachdb-python-library
uv sync --all-packages --all-extras
```

## First Retry Example

```python
import psycopg
from cockroachdb import crdb_retry


@crdb_retry(max_retries=5, base_delay=0.1)
def insert_user(conn: psycopg.Connection, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (name) VALUES (%s)", (name,))
    conn.commit()


with psycopg.connect("postgresql://root@localhost:26257/defaultdb") as conn:
    insert_user(conn, "Alice")
```

The `@crdb_retry` decorator catches `SQLSTATE 40001` (serialization failure) and retries with exponential backoff.

## Using CockroachDBTemplate

For a programmatic API without decorators:

```python
from cockroachdb.core import CockroachDBTemplate

template = CockroachDBTemplate("postgresql://root@localhost:26257/defaultdb")


def do_transfer(conn, from_id: int, to_id: int, amount: float) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_id))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_id))


template.execute(do_transfer, from_id=1, to_id=2, amount=100.0)
```

## Configuration

All packages read from `CockroachDBConfig` (Pydantic settings):

```python
from cockroachdb import CockroachDBConfig

config = CockroachDBConfig(
    dsn="postgresql://root@localhost:26257/defaultdb",
    max_retries=5,
    base_delay=0.1,
    circuit_breaker_threshold=10,
)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COCKROACHDB_DSN` | -- | Connection string |
| `COCKROACHDB_MAX_RETRIES` | `3` | Max serialization retry attempts |
| `COCKROACHDB_BASE_DELAY` | `0.05` | Initial backoff delay (seconds) |
| `COCKROACHDB_CIRCUIT_BREAKER_THRESHOLD` | `5` | Failures before circuit opens |
| `COCKROACHDB_REGION` | -- | Default region for multi-region ops |

## Next Steps

- [Packages overview](packages/base.md) -- explore each package
- [Examples](examples.md) -- runnable code samples
- [API Reference](api-reference.md) -- class and function signatures
