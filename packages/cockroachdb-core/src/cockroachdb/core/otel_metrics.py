"""OpenTelemetry-based metrics collector for CockroachDB operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cockroachdb.types import TransactionOutcome

try:
    from opentelemetry import metrics as otel_metrics

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


class OpenTelemetryMetricsCollector:
    """Metrics collector exporting to OpenTelemetry.

    Implements the :class:`~cockroachdb.types.MetricsCollector` protocol using
    the OpenTelemetry Metrics API. Requires the ``opentelemetry-api`` package.

    Install with::

        pip install cockroachdb-core[otel]

    Example::

        from cockroachdb.core import OpenTelemetryMetricsCollector

        metrics = OpenTelemetryMetricsCollector()

    Raises:
        ImportError: If ``opentelemetry-api`` is not installed.
    """

    def __init__(
        self,
        meter_name: str = "cockroachdb",
        meter_version: str = "0.1.0",
    ) -> None:
        """Initialise the OpenTelemetry metrics collector.

        Args:
            meter_name: Name for the OpenTelemetry Meter.
            meter_version: Version string for the Meter.

        Raises:
            ImportError: If the ``opentelemetry-api`` package is not installed.
        """
        if not _HAS_OTEL:
            raise ImportError(
                "The opentelemetry-api package is required for "
                "OpenTelemetryMetricsCollector. "
                "Install it with: pip install cockroachdb-core[otel]"
            )

        meter = otel_metrics.get_meter(meter_name, meter_version)

        self._tx_duration = meter.create_histogram(
            name="cockroachdb.transaction.duration",
            description="Transaction duration in milliseconds",
            unit="ms",
        )
        self._tx_count = meter.create_counter(
            name="cockroachdb.transaction.count",
            description="Total transactions by outcome",
        )
        self._retry_count = meter.create_counter(
            name="cockroachdb.retry.count",
            description="Total retry attempts",
        )
        self._follower_read_duration = meter.create_histogram(
            name="cockroachdb.follower_read.duration",
            description="Follower read duration in milliseconds",
            unit="ms",
        )
        self._region_op_duration = meter.create_histogram(
            name="cockroachdb.region.operation.duration",
            description="Region operation duration in milliseconds",
            unit="ms",
        )

    def record_transaction(self, outcome: TransactionOutcome, duration_ms: float) -> None:
        """Record a transaction execution.

        Args:
            outcome: Transaction outcome (committed, retried, failed).
            duration_ms: Duration in milliseconds.
        """
        self._tx_duration.record(duration_ms, {"outcome": outcome.value})
        self._tx_count.add(1, {"outcome": outcome.value})

    def record_retry(self, attempt: int) -> None:
        """Record a retry attempt.

        Args:
            attempt: The retry attempt number.
        """
        self._retry_count.add(1, {"attempt": str(attempt)})

    def record_follower_read(self, duration_ms: float) -> None:
        """Record a follower read duration.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._follower_read_duration.record(duration_ms)

    def record_region_operation(self, region: str, duration_ms: float) -> None:
        """Record a region-scoped operation duration.

        Args:
            region: Region identifier.
            duration_ms: Duration in milliseconds.
        """
        self._region_op_duration.record(duration_ms, {"region": region})
