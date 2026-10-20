"""Circuit breaker example.

Demonstrates the circuit breaker pattern for CockroachDB fault tolerance:
    - Creating a ``CircuitBreaker`` with default and custom policies
    - Wrapping operations with ``breaker.call()``
    - Handling ``CircuitBreakerOpenError`` when the breaker trips
    - Observing state transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    - Recovery after the timeout elapses

Prerequisites:
    pip install cockroachdb cockroachdb-core

Usage:
    python examples/circuit_breaker.py
"""

from __future__ import annotations

import contextlib
import time

from cockroachdb import CircuitBreakerOpenError
from cockroachdb.core.circuit_breaker import CircuitBreaker
from cockroachdb.types import CircuitBreakerPolicy, CircuitBreakerState

# ---------------------------------------------------------------------------
# 1. Basic circuit breaker with defaults
# ---------------------------------------------------------------------------


def demonstrate_basic_circuit_breaker() -> None:
    """Create a circuit breaker with default policy.

    Defaults:
        - failure_threshold=5 — trips after 5 consecutive failures
        - recovery_timeout=30.0 — stays open for 30 seconds
        - half_open_max_calls=1 — allows 1 test call in half-open state
    """
    print("--- Basic circuit breaker ---")

    breaker = CircuitBreaker()

    print(f"  Initial state: {breaker.state}")

    # Successful call
    result = breaker.call(lambda: "connected")
    print(f"  Successful call result: {result}")
    print(f"  State after success: {breaker.state}")
    print(f"  Failure count: {breaker.failure_count}")
    print()


# ---------------------------------------------------------------------------
# 2. Custom circuit breaker policy
# ---------------------------------------------------------------------------


def demonstrate_custom_policy() -> None:
    """Create a circuit breaker with custom thresholds.

    A lower failure_threshold makes the breaker trip faster, useful
    for operations where you want to fail fast on database outages.
    """
    print("--- Custom circuit breaker policy ---")

    policy = CircuitBreakerPolicy(
        failure_threshold=3,  # Trip after 3 failures (instead of default 5)
        recovery_timeout=2.0,  # Try to recover after 2 seconds (instead of 30)
        half_open_max_calls=2,  # Allow 2 test calls in half-open state
    )

    breaker = CircuitBreaker(policy=policy)
    print(
        f"  Policy: threshold={policy.failure_threshold}, "
        f"timeout={policy.recovery_timeout}s, "
        f"half_open_max={policy.half_open_max_calls}"
    )
    print(f"  Initial state: {breaker.state}")
    print()


# ---------------------------------------------------------------------------
# 3. Tripping the breaker
# ---------------------------------------------------------------------------


def demonstrate_tripping() -> None:
    """Show how consecutive failures trip the circuit breaker.

    After ``failure_threshold`` consecutive failures, the breaker
    transitions from CLOSED to OPEN. In the OPEN state, all calls
    are rejected immediately with ``CircuitBreakerOpenError`` without
    executing the wrapped function.
    """
    print("--- Tripping the circuit breaker ---")

    policy = CircuitBreakerPolicy(
        failure_threshold=3,
        recovery_timeout=2.0,
    )
    breaker = CircuitBreaker(policy=policy)

    # Inject failures
    for i in range(3):
        try:
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("db unreachable")))
        except ConnectionError:
            print(f"  Failure {i + 1}: state={breaker.state}, failures={breaker.failure_count}")

    # Breaker should now be OPEN
    print(f"  After 3 failures: state={breaker.state}")
    assert breaker.state == CircuitBreakerState.OPEN

    # Subsequent calls are rejected immediately
    try:
        breaker.call(lambda: "this won't execute")
    except CircuitBreakerOpenError as e:
        print(f"  CircuitBreakerOpenError caught — remaining timeout: {e.remaining_timeout:.1f}s")

    print()


# ---------------------------------------------------------------------------
# 4. Recovery: OPEN -> HALF_OPEN -> CLOSED
# ---------------------------------------------------------------------------


def demonstrate_recovery() -> None:
    """Show the full recovery lifecycle.

    After ``recovery_timeout`` elapses, the breaker moves to HALF_OPEN.
    In HALF_OPEN, it allows a limited number of test calls:
        - If a test call succeeds, the breaker returns to CLOSED.
        - If a test call fails, the breaker returns to OPEN.
    """
    print("--- Recovery lifecycle ---")

    policy = CircuitBreakerPolicy(
        failure_threshold=2,
        recovery_timeout=1.0,  # Short timeout for demo purposes
        half_open_max_calls=1,
    )
    breaker = CircuitBreaker(policy=policy)

    # Trip the breaker
    for _ in range(2):
        with contextlib.suppress(ConnectionError):
            breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("down")))

    print(f"  Breaker tripped: state={breaker.state}")

    # Wait for recovery timeout
    print(f"  Waiting {policy.recovery_timeout}s for recovery timeout...")
    time.sleep(policy.recovery_timeout + 0.1)

    # Next call transitions to HALF_OPEN and allows one test call
    result = breaker.call(lambda: "recovered!")
    print(f"  Test call result: {result}")
    print(f"  State after successful test: {breaker.state}")
    print(f"  Failure count reset: {breaker.failure_count}")

    assert breaker.state == CircuitBreakerState.CLOSED
    print()


# ---------------------------------------------------------------------------
# 5. Practical pattern: wrapping database operations
# ---------------------------------------------------------------------------


def demonstrate_practical_usage() -> None:
    """Show a realistic pattern for wrapping database operations.

    In production, you would create a single CircuitBreaker instance
    per database connection pool and wrap all operations through it.
    """
    print("--- Practical usage pattern ---")

    # One breaker per connection pool / data source
    db_breaker = CircuitBreaker(
        policy=CircuitBreakerPolicy(
            failure_threshold=5,
            recovery_timeout=30.0,
        )
    )

    def query_with_breaker(query: str) -> str:
        """Execute a query through the circuit breaker."""
        try:
            return db_breaker.call(lambda: f"Result of: {query}")
        except CircuitBreakerOpenError:
            # Fall back to cache, return stale data, or propagate
            return f"FALLBACK: circuit breaker open, serving cached data for: {query}"

    # Normal operation
    print(f"  {query_with_breaker('SELECT * FROM users')}")

    # Simulate outage
    for _ in range(5):
        with contextlib.suppress(ConnectionError):
            db_breaker.call(lambda: (_ for _ in ()).throw(ConnectionError("timeout")))

    # Now the breaker is open — calls use fallback
    print(f"  {query_with_breaker('SELECT * FROM users')}")
    print(f"  Breaker state: {db_breaker.state}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB Circuit Breaker Examples ===\n")

    demonstrate_basic_circuit_breaker()
    demonstrate_custom_policy()
    demonstrate_tripping()
    demonstrate_recovery()
    demonstrate_practical_usage()

    print("Done.")
