"""Basic retry decorator example.

Demonstrates the ``@crdb_retry`` decorator for automatic transaction
retry on CockroachDB serialization conflicts (SQLSTATE 40001).

Features shown:
    - Basic retry with default settings
    - Custom retry configuration (max_retries, backoff, jitter)
    - on_retry callback for logging/observability
    - Async function retry
    - Pattern for use with psycopg3

Prerequisites:
    pip install cockroachdb psycopg[binary]

Usage:
    python examples/basic_retry.py
"""

from __future__ import annotations

import logging

import psycopg

from cockroachdb import CockroachDBRetryExhausted, IsolationLevel, crdb_retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Connection string — adjust for your CockroachDB instance
CONN_STRING = "postgresql://root@localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# 1. Basic retry with defaults (3 retries, exponential backoff)
# ---------------------------------------------------------------------------


@crdb_retry()
def transfer_funds(conn_string: str, from_id: int, to_id: int, amount: float) -> str:
    """Transfer funds between two accounts with automatic retry.

    If CockroachDB detects a serialization conflict (two concurrent
    transactions modifying the same row), the decorator re-executes
    the entire function — exactly what CockroachDB's retry protocol
    requires.
    """
    with psycopg.connect(conn_string) as conn, conn.transaction():
        conn.execute(
            "UPDATE accounts SET balance = balance - %s WHERE id = %s",
            (amount, from_id),
        )
        conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (amount, to_id),
        )
    return f"Transferred {amount} from account {from_id} to {to_id}"


# ---------------------------------------------------------------------------
# 2. Custom retry configuration
# ---------------------------------------------------------------------------


@crdb_retry(
    max_retries=5,  # Try up to 5 times before giving up
    base_delay=0.2,  # Start with 200ms delay
    max_delay=10.0,  # Never wait longer than 10 seconds
    multiplier=3.0,  # Triple the delay each retry
    jitter_factor=0.25,  # Add up to 25% random jitter
    isolation=IsolationLevel.SERIALIZABLE,
)
def batch_insert(conn_string: str, rows: list[dict]) -> int:
    """Insert a batch of rows with aggressive retry settings.

    Long-running batch operations benefit from more retries and a
    higher backoff ceiling.
    """
    with psycopg.connect(conn_string) as conn, conn.transaction():
        for row in rows:
            conn.execute(
                "INSERT INTO events (name, payload) VALUES (%s, %s)",
                (row["name"], row["payload"]),
            )
    return len(rows)


# ---------------------------------------------------------------------------
# 3. on_retry callback for observability
# ---------------------------------------------------------------------------


def log_retry(attempt: int, error: Exception) -> None:
    """Called on each retry — useful for metrics, alerts, or structured logging."""
    logger.warning(
        "Retry attempt %d due to: %s",
        attempt,
        error,
    )


@crdb_retry(
    max_retries=3,
    on_retry=log_retry,
)
def update_inventory(conn_string: str, product_id: int, delta: int) -> None:
    """Decrement inventory with retry logging.

    The ``on_retry`` callback receives (attempt_number, exception) on
    each serialization conflict so you can emit metrics or log structured
    data.
    """
    with psycopg.connect(conn_string) as conn, conn.transaction():
        conn.execute(
            "UPDATE inventory SET quantity = quantity + %s WHERE product_id = %s",
            (delta, product_id),
        )


# ---------------------------------------------------------------------------
# 4. Async retry
# ---------------------------------------------------------------------------


@crdb_retry(max_retries=3, on_retry=log_retry)
async def async_transfer(conn_string: str, from_id: int, to_id: int, amount: float) -> str:
    """Async version of the transfer function.

    ``@crdb_retry`` detects async functions automatically and uses
    ``asyncio.sleep`` instead of ``time.sleep`` for non-blocking backoff.
    """
    async with await psycopg.AsyncConnection.connect(conn_string) as conn, conn.transaction():
        await conn.execute(
            "UPDATE accounts SET balance = balance - %s WHERE id = %s",
            (amount, from_id),
        )
        await conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (amount, to_id),
        )
    return f"Async transfer of {amount} from {from_id} to {to_id}"


# ---------------------------------------------------------------------------
# 5. Handling exhausted retries
# ---------------------------------------------------------------------------


def demonstrate_exhaustion() -> None:
    """Show how to handle CockroachDBRetryExhausted."""

    @crdb_retry(max_retries=2)
    def always_conflicts() -> None:
        raise type("FakeError", (Exception,), {"pgcode": "40001"})("simulated conflict")

    try:
        always_conflicts()
    except CockroachDBRetryExhausted as exc:
        logger.error(
            "All %d retries exhausted. Last error: %s",
            exc.attempts,
            exc.last_error,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB Retry Decorator Examples ===\n")

    # These require a running CockroachDB instance with the right tables.
    # Uncomment the lines below when connected to a real cluster.

    # result = transfer_funds(CONN_STRING, from_id=1, to_id=2, amount=50.0)
    # print(result)

    # count = batch_insert(CONN_STRING, [{"name": "evt1", "payload": "{}"}])
    # print(f"Inserted {count} rows")

    # update_inventory(CONN_STRING, product_id=42, delta=-1)

    # asyncio.run(async_transfer(CONN_STRING, from_id=1, to_id=2, amount=25.0))

    # Exhaustion handling works without a database:
    print("--- Demonstrating retry exhaustion ---")
    demonstrate_exhaustion()
    print("\nDone.")
