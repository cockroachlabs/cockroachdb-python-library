"""Metrics collectors implementing the MetricsCollector protocol."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cockroachdb.types import TransactionOutcome


class NoopMetricsCollector:
    """Silently discards all metrics. Use as a default when metrics are disabled."""

    def record_transaction(self, outcome: TransactionOutcome, duration_ms: float) -> None:
        pass

    def record_retry(self, attempt: int) -> None:
        pass

    def record_follower_read(self, duration_ms: float) -> None:
        pass

    def record_region_operation(self, region: str, duration_ms: float) -> None:
        pass


class InMemoryMetricsCollector:
    """Stores metrics in dictionaries for testing and inspection."""

    def __init__(self) -> None:
        self.transactions: dict[TransactionOutcome, list[float]] = defaultdict(list)
        self.retries: list[int] = []
        self.follower_reads: list[float] = []
        self.region_operations: dict[str, list[float]] = defaultdict(list)

    def record_transaction(self, outcome: TransactionOutcome, duration_ms: float) -> None:
        self.transactions[outcome].append(duration_ms)

    def record_retry(self, attempt: int) -> None:
        self.retries.append(attempt)

    def record_follower_read(self, duration_ms: float) -> None:
        self.follower_reads.append(duration_ms)

    def record_region_operation(self, region: str, duration_ms: float) -> None:
        self.region_operations[region].append(duration_ms)

    @property
    def total_transactions(self) -> int:
        return sum(len(v) for v in self.transactions.values())

    @property
    def total_retries(self) -> int:
        return len(self.retries)


try:
    from prometheus_client import Counter, Histogram

    class PrometheusMetricsCollector:
        """Exports metrics to Prometheus using prometheus_client."""

        def __init__(self, prefix: str = "cockroachdb") -> None:
            self._tx_total = Counter(
                f"{prefix}_transactions_total",
                "Total transactions by outcome",
                ["outcome"],
            )
            self._tx_duration = Histogram(
                f"{prefix}_transaction_duration_ms",
                "Transaction duration in milliseconds",
                ["outcome"],
            )
            self._retry_total = Counter(
                f"{prefix}_retries_total",
                "Total retry attempts",
            )
            self._follower_read_duration = Histogram(
                f"{prefix}_follower_read_duration_ms",
                "Follower read duration in milliseconds",
            )
            self._region_op_duration = Histogram(
                f"{prefix}_region_operation_duration_ms",
                "Region operation duration in milliseconds",
                ["region"],
            )

        def record_transaction(self, outcome: TransactionOutcome, duration_ms: float) -> None:
            self._tx_total.labels(outcome=outcome.value).inc()
            self._tx_duration.labels(outcome=outcome.value).observe(duration_ms)

        def record_retry(self, attempt: int) -> None:
            self._retry_total.inc()

        def record_follower_read(self, duration_ms: float) -> None:
            self._follower_read_duration.observe(duration_ms)

        def record_region_operation(self, region: str, duration_ms: float) -> None:
            self._region_op_duration.labels(region=region).observe(duration_ms)

except ImportError:
    pass
