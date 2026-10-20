"""Metrics collection for CockroachDB AI operations."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class AIMetrics(Protocol):
    """Protocol for recording AI-related operational metrics.

    Implementations should be lightweight and non-blocking so they
    do not affect request latency.
    """

    def record_vector_search(
        self, table: str, metric: str, num_results: int, duration_ms: float
    ) -> None:
        """Record a vector similarity search execution.

        Args:
            table: Table that was searched.
            metric: Distance metric used.
            num_results: Number of results returned.
            duration_ms: Search duration in milliseconds.
        """
        ...

    def record_embedding(
        self, provider: str, num_texts: int, dimensions: int, duration_ms: float
    ) -> None:
        """Record an embedding generation call.

        Args:
            provider: Embedding provider name.
            num_texts: Number of texts embedded.
            dimensions: Dimensionality of output vectors.
            duration_ms: Embedding duration in milliseconds.
        """
        ...

    def record_chat_completion(self, provider: str, num_messages: int, duration_ms: float) -> None:
        """Record a chat completion call.

        Args:
            provider: Chat provider name.
            num_messages: Number of messages in the conversation.
            duration_ms: Completion duration in milliseconds.
        """
        ...


class NoopAIMetrics:
    """No-op metrics implementation that silently discards all recordings."""

    def record_vector_search(
        self, table: str, metric: str, num_results: int, duration_ms: float
    ) -> None:
        pass

    def record_embedding(
        self, provider: str, num_texts: int, dimensions: int, duration_ms: float
    ) -> None:
        pass

    def record_chat_completion(self, provider: str, num_messages: int, duration_ms: float) -> None:
        pass


@dataclass
class _MetricRecord:
    """Single recorded metric event."""

    name: str
    timestamp: float
    attributes: dict[str, object] = field(default_factory=dict)


class InMemoryAIMetrics:
    """In-memory metrics collector for testing and debugging.

    Stores all recorded metrics in a list for later inspection.

    Example::

        metrics = InMemoryAIMetrics()
        # ... run operations ...
        assert metrics.search_count == 3
        assert metrics.total_results == 15
    """

    def __init__(self) -> None:
        self._records: list[_MetricRecord] = []
        self.search_count: int = 0
        self.total_results: int = 0
        self.embedding_count: int = 0
        self.total_texts_embedded: int = 0
        self.chat_count: int = 0
        self.total_search_ms: float = 0.0
        self.total_embedding_ms: float = 0.0
        self.total_chat_ms: float = 0.0

    def record_vector_search(
        self, table: str, metric: str, num_results: int, duration_ms: float
    ) -> None:
        """Record a vector search and update counters."""
        self.search_count += 1
        self.total_results += num_results
        self.total_search_ms += duration_ms
        self._records.append(
            _MetricRecord(
                name="vector_search",
                timestamp=time.time(),
                attributes={
                    "table": table,
                    "metric": metric,
                    "num_results": num_results,
                    "duration_ms": duration_ms,
                },
            )
        )

    def record_embedding(
        self, provider: str, num_texts: int, dimensions: int, duration_ms: float
    ) -> None:
        """Record an embedding call and update counters."""
        self.embedding_count += 1
        self.total_texts_embedded += num_texts
        self.total_embedding_ms += duration_ms
        self._records.append(
            _MetricRecord(
                name="embedding",
                timestamp=time.time(),
                attributes={
                    "provider": provider,
                    "num_texts": num_texts,
                    "dimensions": dimensions,
                    "duration_ms": duration_ms,
                },
            )
        )

    def record_chat_completion(self, provider: str, num_messages: int, duration_ms: float) -> None:
        """Record a chat completion and update counters."""
        self.chat_count += 1
        self.total_chat_ms += duration_ms
        self._records.append(
            _MetricRecord(
                name="chat_completion",
                timestamp=time.time(),
                attributes={
                    "provider": provider,
                    "num_messages": num_messages,
                    "duration_ms": duration_ms,
                },
            )
        )

    @property
    def records(self) -> list[_MetricRecord]:
        """All recorded metric events, in chronological order."""
        return list(self._records)

    def reset(self) -> None:
        """Clear all recorded metrics and reset counters to zero."""
        self._records.clear()
        self.search_count = 0
        self.total_results = 0
        self.embedding_count = 0
        self.total_texts_embedded = 0
        self.chat_count = 0
        self.total_search_ms = 0.0
        self.total_embedding_ms = 0.0
        self.total_chat_ms = 0.0
