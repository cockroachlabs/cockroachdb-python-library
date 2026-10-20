# cockroachdb (Base Package)

The foundation package providing decorators, types, exceptions, and Pydantic configuration.

```bash
pip install cockroachdb
```

## Decorators

### `@crdb_retry`

Automatic serialization retry with exponential backoff.

```python
from cockroachdb import crdb_retry


@crdb_retry(max_retries=5, base_delay=0.1)
def transfer(conn, from_id: int, to_id: int, amount: float) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_id))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_id))
    conn.commit()
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `base_delay` | `float` | `0.05` | Initial backoff delay (seconds) |

### `@crdb_region`

Pin a function to a specific CockroachDB region.

```python
from cockroachdb import crdb_region


@crdb_region("us-east1")
def create_us_user(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (name, region) VALUES (%s, 'us-east1')", (name,))
    conn.commit()
```

### `@regional_by_row` / `@global_table`

Mark ORM models for multi-region topology.

```python
from cockroachdb import regional_by_row, global_table


@regional_by_row(default_region="us-east1")
class UserProfile: ...


@global_table
class CountryList: ...
```

### `@follower_read`

Enable stale reads from the nearest follower replica.

```python
from cockroachdb import follower_read


@follower_read
def get_product_catalog(conn) -> list:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM products")
        return cur.fetchall()
```

## Configuration

```python
from cockroachdb import CockroachDBConfig

config = CockroachDBConfig(
    dsn="postgresql://root@localhost:26257/defaultdb",
    max_retries=5,
    base_delay=0.1,
    circuit_breaker_threshold=10,
)
```

## Types

- `RetryPolicy` -- dataclass holding retry parameters
- `RegionConfig` -- multi-region topology settings
- `SerializationError` -- raised on SQLSTATE 40001

## Exceptions

| Exception | Description |
|-----------|-------------|
| `CockroachDBError` | Base exception for all library errors |
| `SerializationError` | Serialization failure (40001) |
| `RetryExhaustedError` | All retry attempts failed |
| `CircuitOpenError` | Circuit breaker is open |
