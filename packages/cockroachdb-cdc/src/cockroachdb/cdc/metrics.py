"""CDC-specific metrics collectors for changefeed event processing."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol, runtime_checkable


@runtime_checkable
class CDCMetrics(Protocol):
    """Protocol for collecting CDC changefeed metrics."""

    def record_event(self, table: str, operation: str, duration_ms: float) -> None:
        """Record a changefeed event processing duration.

        Args:
            table: Table name that emitted the event.
            operation: CDC operation type (insert, update, delete).
            duration_ms: Time spent processing the event in milliseconds.
        """
        ...

    def record_dispatch(self, table: str, success: bool) -> None:
        """Record a handler dispatch outcome.

        Args:
            table: Table name the handler is bound to.
            success: Whether the dispatch completed without error.
        """
        ...

    def record_error(self, table: str, error: Exception) -> None:
        """Record a processing error.

        Args:
            table: Table name where the error occurred.
            error: The exception that was raised.
        """
        ...


class NoopCDCMetrics:
    """Silently discards all CDC metrics. Use as a default when metrics are disabled."""

    def record_event(self, table: str, operation: str, duration_ms: float) -> None:
        pass

    def record_dispatch(self, table: str, success: bool) -> None:
        pass

    def record_error(self, table: str, error: Exception) -> None:
        pass


class InMemoryCDCMetrics:
    """Stores CDC metrics in dictionaries for testing and inspection."""

    def __init__(self) -> None:
        self.events: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.dispatches: dict[str, list[bool]] = defaultdict(list)
        self.errors: dict[str, list[str]] = defaultdict(list)

    def record_event(self, table: str, operation: str, duration_ms: float) -> None:
        self.events[table].append((operation, duration_ms))

    def record_dispatch(self, table: str, success: bool) -> None:
        self.dispatches[table].append(success)

    def record_error(self, table: str, error: Exception) -> None:
        self.errors[table].append(type(error).__name__)

    @property
    def total_events(self) -> int:
        """Total number of recorded events across all tables."""
        return sum(len(v) for v in self.events.values())

    @property
    def total_errors(self) -> int:
        """Total number of recorded errors across all tables."""
        return sum(len(v) for v in self.errors.values())

    @property
    def total_dispatches(self) -> int:
        """Total number of recorded dispatches across all tables."""
        return sum(len(v) for v in self.dispatches.values())


try:
    from prometheus_client import Counter, Histogram

    class PrometheusCDCMetrics:
        """Exports CDC metrics to Prometheus using prometheus_client.

        Requires the ``prometheus-client`` package. Install with::

            pip install prometheus-client
        """

        def __init__(self, prefix: str = "cockroachdb_cdc") -> None:
            self._event_duration = Histogram(
                f"{prefix}_event_duration_ms",
                "CDC event processing duration in milliseconds",
                ["table", "operation"],
            )
            self._event_total = Counter(
                f"{prefix}_events_total",
                "Total CDC events processed",
                ["table", "operation"],
            )
            self._dispatch_total = Counter(
                f"{prefix}_dispatches_total",
                "Total handler dispatches by outcome",
                ["table", "success"],
            )
            self._error_total = Counter(
                f"{prefix}_errors_total",
                "Total CDC processing errors",
                ["table"],
            )

        def record_event(self, table: str, operation: str, duration_ms: float) -> None:
            self._event_total.labels(table=table, operation=operation).inc()
            self._event_duration.labels(table=table, operation=operation).observe(duration_ms)

        def record_dispatch(self, table: str, success: bool) -> None:
            self._dispatch_total.labels(table=table, success=str(success)).inc()

        def record_error(self, table: str, error: Exception) -> None:
            self._error_total.labels(table=table).inc()

except ImportError:
    pass
