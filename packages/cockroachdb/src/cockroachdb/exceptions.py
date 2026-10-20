"""Exception hierarchy for the CockroachDB Python Library."""

from __future__ import annotations


class CockroachDBError(Exception):
    """Base exception for all CockroachDB library errors."""


class CockroachDBRetryExhausted(CockroachDBError):  # noqa: N818  # public API; name predates the Error-suffix convention
    """Raised when all retry attempts are exhausted on serialization conflicts."""

    def __init__(self, max_retries: int, last_error: Exception | None = None) -> None:
        self.max_retries = max_retries
        self.last_error = last_error
        super().__init__(
            f"Transaction failed after {max_retries} retries. Last error: {last_error}"
        )


class CircuitBreakerOpenError(CockroachDBError):
    """Raised when the circuit breaker is open and rejecting calls."""

    def __init__(self, recovery_seconds: float) -> None:
        self.recovery_seconds = recovery_seconds
        super().__init__(f"Circuit breaker is open. Recovery in {recovery_seconds:.1f}s")


class RegionValidationError(CockroachDBError):
    """Raised when a region name fails validation."""

    def __init__(self, region: str, reason: str) -> None:
        self.region = region
        self.reason = reason
        super().__init__(f"Invalid region '{region}': {reason}")


class FollowerReadError(CockroachDBError):
    """Raised when a follower read operation fails."""


class ChangefeedError(CockroachDBError):
    """Raised when a changefeed operation fails."""


class VectorSearchError(CockroachDBError):
    """Raised when a vector search operation fails."""


class ConfigurationError(CockroachDBError):
    """Raised when library configuration is invalid."""


# SQLSTATE codes used by CockroachDB
RETRYABLE_SQLSTATES = frozenset(
    {
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
    }
)


def is_retryable_error(error: BaseException) -> bool:
    """Check if an exception is a retryable CockroachDB error (SQLSTATE 40001/40P01)."""
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate and sqlstate in RETRYABLE_SQLSTATES:
        return True

    pgcode = getattr(error, "pgcode", None)
    if pgcode and pgcode in RETRYABLE_SQLSTATES:
        return True

    if hasattr(error, "__cause__") and error.__cause__ is not None:
        return is_retryable_error(error.__cause__)

    return False
