"""Tests for cockroachdb.core.metrics collectors."""

from __future__ import annotations

from cockroachdb.core.metrics import InMemoryMetricsCollector, NoopMetricsCollector
from cockroachdb.types import MetricsCollector, TransactionOutcome


class TestInMemoryMetricsCollector:
    """Tests for InMemoryMetricsCollector."""

    def test_record_transaction(self) -> None:
        m = InMemoryMetricsCollector()
        m.record_transaction(TransactionOutcome.COMMITTED, 15.0)
        m.record_transaction(TransactionOutcome.COMMITTED, 20.0)
        m.record_transaction(TransactionOutcome.FAILED, 5.0)

        assert len(m.transactions[TransactionOutcome.COMMITTED]) == 2
        assert len(m.transactions[TransactionOutcome.FAILED]) == 1
        assert m.total_transactions == 3

    def test_record_retry(self) -> None:
        m = InMemoryMetricsCollector()
        m.record_retry(1)
        m.record_retry(2)
        m.record_retry(3)

        assert m.retries == [1, 2, 3]
        assert m.total_retries == 3

    def test_record_follower_read(self) -> None:
        m = InMemoryMetricsCollector()
        m.record_follower_read(10.5)
        m.record_follower_read(20.3)

        assert m.follower_reads == [10.5, 20.3]

    def test_record_region_operation(self) -> None:
        m = InMemoryMetricsCollector()
        m.record_region_operation("us-east1", 5.0)
        m.record_region_operation("us-east1", 7.0)
        m.record_region_operation("eu-west1", 12.0)

        assert len(m.region_operations["us-east1"]) == 2
        assert len(m.region_operations["eu-west1"]) == 1

    def test_empty_initial_state(self) -> None:
        m = InMemoryMetricsCollector()
        assert m.total_transactions == 0
        assert m.total_retries == 0
        assert m.follower_reads == []

    def test_implements_metrics_protocol(self) -> None:
        m = InMemoryMetricsCollector()
        assert isinstance(m, MetricsCollector)


class TestNoopMetricsCollector:
    """Tests for NoopMetricsCollector."""

    def test_record_transaction_does_nothing(self) -> None:
        m = NoopMetricsCollector()
        # Should not raise
        m.record_transaction(TransactionOutcome.COMMITTED, 10.0)

    def test_record_retry_does_nothing(self) -> None:
        m = NoopMetricsCollector()
        m.record_retry(1)

    def test_record_follower_read_does_nothing(self) -> None:
        m = NoopMetricsCollector()
        m.record_follower_read(5.0)

    def test_record_region_operation_does_nothing(self) -> None:
        m = NoopMetricsCollector()
        m.record_region_operation("us-east1", 3.0)


class TestMetricsCollectorProtocol:
    """Tests that both collectors satisfy the MetricsCollector protocol."""

    def test_in_memory_is_metrics_collector(self) -> None:
        assert isinstance(InMemoryMetricsCollector(), MetricsCollector)

    def test_noop_is_metrics_collector(self) -> None:
        assert isinstance(NoopMetricsCollector(), MetricsCollector)

    def test_in_memory_transaction_durations(self) -> None:
        m = InMemoryMetricsCollector()
        m.record_transaction(TransactionOutcome.RETRIED, 100.0)
        assert m.transactions[TransactionOutcome.RETRIED] == [100.0]
