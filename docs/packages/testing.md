# cockroachdb-testing

Test fixtures, simulators, and factories for CockroachDB applications.

```bash
pip install cockroachdb-testing
```

**Depends on:** `cockroachdb`, `cockroachdb-core`, `pytest`, `testcontainers[cockroachdb]`

## CockroachDBFixture

Spins up a real CockroachDB instance via Testcontainers for integration tests.

```python
import pytest
from cockroachdb.testing import CockroachDBFixture


@pytest.fixture
def crdb():
    with CockroachDBFixture() as fixture:
        fixture.execute("CREATE TABLE users (id INT PRIMARY KEY, name STRING)")
        yield fixture


def test_insert_user(crdb):
    crdb.execute("INSERT INTO users VALUES (1, 'Alice')")
    rows = crdb.fetch_all("SELECT * FROM users")
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"
```

**Fixture methods:**

| Method | Description |
|--------|-------------|
| `execute(sql)` | Run a SQL statement |
| `fetch_all(sql)` | Run a query and return all rows |
| `fetch_one(sql)` | Run a query and return one row |
| `connection()` | Get the underlying `psycopg` connection |

## RetrySimulator

Simulate serialization failures to test retry logic without a real cluster.

```python
from cockroachdb.testing import RetrySimulator

simulator = RetrySimulator(failure_rate=0.5, max_failures=3)


@simulator.wrap
def my_transaction(conn):
    conn.execute("INSERT INTO events (name) VALUES ('test')")


# Will raise SerializationError ~50% of attempts, up to 3 times
my_transaction(mock_conn)
```

## Concurrency Testing

Helpers for testing concurrent transaction behavior:

```python
from cockroachdb.testing import ConcurrencyRunner

runner = ConcurrencyRunner(crdb.connection_string)
results = runner.run_concurrent(
    fn=transfer_funds,
    args_list=[(1, 2, 100.0), (2, 1, 50.0)],
    workers=4,
)
assert all(r.success for r in results)
```

## Factories

Generate test data for common CockroachDB patterns:

```python
from cockroachdb.testing import factories

# Generate random rows matching a schema
rows = factories.generate_rows("users", count=100)
crdb.bulk_insert("users", rows)
```

## API Summary

| Symbol | Type | Description |
|--------|------|-------------|
| `CockroachDBFixture` | class | Testcontainers-based fixture |
| `RetrySimulator` | class | Mock serialization failures |
| `ConcurrencyRunner` | class | Concurrent transaction runner |
| `factories` | module | Test data generators |
