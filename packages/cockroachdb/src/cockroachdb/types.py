"""Core types, protocols, and enumerations for the CockroachDB Python Library."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class IsolationLevel(StrEnum):
    """CockroachDB transaction isolation levels."""

    SERIALIZABLE = "serializable"
    READ_COMMITTED = "read committed"


class DistanceMetric(StrEnum):
    """Vector distance metrics for pgvector operations."""

    COSINE = "cosine"
    EUCLIDEAN = "l2"
    INNER_PRODUCT = "inner_product"

    @property
    def operator(self) -> str:
        return {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}[self.value]

    @property
    def opclass(self) -> str:
        """Return the pgvector opclass name for this distance metric."""
        return {
            "cosine": "vector_cosine_ops",
            "l2": "vector_l2_ops",
            "inner_product": "vector_ip_ops",
        }[self.value]

    def to_similarity(self, distance: float) -> float:
        if self == DistanceMetric.COSINE:
            return 1.0 - distance
        if self == DistanceMetric.INNER_PRODUCT:
            return -distance
        return 1.0 / (1.0 + distance)


class TransactionOutcome(StrEnum):
    """Outcome of a CockroachDB transaction execution."""

    COMMITTED = "committed"
    RETRIED = "retried"
    FAILED = "failed"


class CDCOperation(StrEnum):
    """Change Data Capture operation types."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class CircuitBreakerState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for retry behavior on serialization conflicts."""

    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = 5.0
    multiplier: float = 2.0
    jitter_factor: float = 0.1


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1


@dataclass(frozen=True)
class RegionConfig:
    """Multi-region configuration."""

    default_region: str | None = None
    allowed_regions: list[str] = field(default_factory=list)
    region_header: str = "X-CockroachDB-Region"


@runtime_checkable
class ExceptionClassifier(Protocol):
    """Protocol for classifying database exceptions as retryable."""

    def is_retryable(self, error: Exception) -> bool: ...
    def is_serialization_error(self, error: Exception) -> bool: ...


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol for collecting CockroachDB operation metrics."""

    def record_transaction(self, outcome: TransactionOutcome, duration_ms: float) -> None: ...
    def record_retry(self, attempt: int) -> None: ...
    def record_follower_read(self, duration_ms: float) -> None: ...
    def record_region_operation(self, region: str, duration_ms: float) -> None: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for generating vector embeddings from text."""

    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dimensions(self) -> int: ...


@dataclass(frozen=True)
class VectorSearchResult:
    """Result of a vector similarity search."""

    id: Any
    document: dict[str, Any]
    distance: float
    similarity: float
