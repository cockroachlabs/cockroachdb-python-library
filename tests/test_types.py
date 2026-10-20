"""Tests for cockroachdb.types."""

from __future__ import annotations

import pytest

from cockroachdb.types import (
    CircuitBreakerPolicy,
    DistanceMetric,
    IsolationLevel,
    RetryPolicy,
    TransactionOutcome,
    VectorSearchResult,
)


class TestDistanceMetric:
    """Tests for DistanceMetric enum."""

    def test_cosine_operator(self) -> None:
        assert DistanceMetric.COSINE.operator == "<=>"

    def test_euclidean_operator(self) -> None:
        assert DistanceMetric.EUCLIDEAN.operator == "<->"

    def test_inner_product_operator(self) -> None:
        assert DistanceMetric.INNER_PRODUCT.operator == "<#>"

    def test_cosine_to_similarity(self) -> None:
        assert DistanceMetric.COSINE.to_similarity(0.25) == pytest.approx(0.75)

    def test_cosine_to_similarity_zero(self) -> None:
        assert DistanceMetric.COSINE.to_similarity(0.0) == pytest.approx(1.0)

    def test_euclidean_to_similarity(self) -> None:
        # 1 / (1 + 0.5) = 0.6667
        assert DistanceMetric.EUCLIDEAN.to_similarity(0.5) == pytest.approx(1.0 / 1.5)

    def test_euclidean_to_similarity_zero(self) -> None:
        assert DistanceMetric.EUCLIDEAN.to_similarity(0.0) == pytest.approx(1.0)

    def test_inner_product_to_similarity(self) -> None:
        assert DistanceMetric.INNER_PRODUCT.to_similarity(0.3) == pytest.approx(-0.3)

    def test_enum_values(self) -> None:
        assert DistanceMetric.COSINE.value == "cosine"
        assert DistanceMetric.EUCLIDEAN.value == "l2"
        assert DistanceMetric.INNER_PRODUCT.value == "inner_product"

    def test_cosine_opclass(self) -> None:
        assert DistanceMetric.COSINE.opclass == "vector_cosine_ops"

    def test_euclidean_opclass(self) -> None:
        assert DistanceMetric.EUCLIDEAN.opclass == "vector_l2_ops"

    def test_inner_product_opclass(self) -> None:
        assert DistanceMetric.INNER_PRODUCT.opclass == "vector_ip_ops"


class TestIsolationLevel:
    """Tests for IsolationLevel enum."""

    def test_serializable(self) -> None:
        assert IsolationLevel.SERIALIZABLE.value == "serializable"

    def test_read_committed(self) -> None:
        assert IsolationLevel.READ_COMMITTED.value == "read committed"

    def test_is_string_enum(self) -> None:
        assert isinstance(IsolationLevel.SERIALIZABLE, str)


class TestTransactionOutcome:
    """Tests for TransactionOutcome enum."""

    def test_values(self) -> None:
        assert TransactionOutcome.COMMITTED.value == "committed"
        assert TransactionOutcome.RETRIED.value == "retried"
        assert TransactionOutcome.FAILED.value == "failed"


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_defaults(self) -> None:
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay == 0.1
        assert policy.max_delay == 5.0
        assert policy.multiplier == 2.0
        assert policy.jitter_factor == 0.1

    def test_custom_values(self) -> None:
        policy = RetryPolicy(max_retries=10, base_delay=0.5)
        assert policy.max_retries == 10
        assert policy.base_delay == 0.5

    def test_frozen(self) -> None:
        policy = RetryPolicy()
        with pytest.raises(AttributeError):
            policy.max_retries = 5  # type: ignore[misc]


class TestCircuitBreakerPolicy:
    """Tests for CircuitBreakerPolicy dataclass."""

    def test_defaults(self) -> None:
        policy = CircuitBreakerPolicy()
        assert policy.failure_threshold == 5
        assert policy.recovery_timeout == 30.0
        assert policy.half_open_max_calls == 1


class TestVectorSearchResult:
    """Tests for VectorSearchResult dataclass."""

    def test_fields(self) -> None:
        result = VectorSearchResult(
            id="abc", document={"text": "hello"}, distance=0.1, similarity=0.9
        )
        assert result.id == "abc"
        assert result.document == {"text": "hello"}
        assert result.distance == 0.1
        assert result.similarity == 0.9
