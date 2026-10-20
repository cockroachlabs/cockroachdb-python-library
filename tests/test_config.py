"""Tests for cockroachdb.config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cockroachdb.config import (
    AIConfig,
    CircuitBreakerConfig,
    CockroachDBConfig,
    FollowerReadConfig,
    MetricsConfig,
    RegionConfig,
    RetryConfig,
)


class TestRetryConfig:
    """Tests for RetryConfig pydantic model."""

    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 0.1
        assert cfg.max_delay == 5.0
        assert cfg.multiplier == 2.0
        assert cfg.jitter_factor == 0.1

    def test_max_retries_ge_zero(self) -> None:
        cfg = RetryConfig(max_retries=0)
        assert cfg.max_retries == 0

    def test_max_retries_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=-1)

    def test_max_retries_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            RetryConfig(max_retries=51)

    def test_base_delay_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            RetryConfig(base_delay=0)

    def test_multiplier_must_exceed_one(self) -> None:
        with pytest.raises(ValidationError):
            RetryConfig(multiplier=1.0)

    def test_jitter_factor_range(self) -> None:
        RetryConfig(jitter_factor=0.0)  # ok
        RetryConfig(jitter_factor=1.0)  # ok
        with pytest.raises(ValidationError):
            RetryConfig(jitter_factor=1.5)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig pydantic model."""

    def test_defaults(self) -> None:
        cfg = CircuitBreakerConfig()
        assert cfg.enabled is True
        assert cfg.failure_threshold == 5
        assert cfg.recovery_timeout == 30.0
        assert cfg.half_open_max_calls == 1

    def test_failure_threshold_ge_one(self) -> None:
        with pytest.raises(ValidationError):
            CircuitBreakerConfig(failure_threshold=0)

    def test_recovery_timeout_positive(self) -> None:
        with pytest.raises(ValidationError):
            CircuitBreakerConfig(recovery_timeout=0)


class TestCockroachDBConfig:
    """Tests for the root CockroachDBConfig model."""

    def test_defaults(self) -> None:
        cfg = CockroachDBConfig()
        assert isinstance(cfg.retry, RetryConfig)
        assert isinstance(cfg.circuit_breaker, CircuitBreakerConfig)
        assert isinstance(cfg.region, RegionConfig)
        assert isinstance(cfg.follower_read, FollowerReadConfig)
        assert isinstance(cfg.metrics, MetricsConfig)
        assert isinstance(cfg.ai, AIConfig)

    def test_nested_override(self) -> None:
        cfg = CockroachDBConfig(retry=RetryConfig(max_retries=10))
        assert cfg.retry.max_retries == 10

    def test_ai_config_defaults(self) -> None:
        cfg = AIConfig()
        assert cfg.default_metric == "cosine"
        assert cfg.default_limit == 10
        assert cfg.embedding_dimensions == 1536
        assert cfg.similarity_threshold == 0.7
        assert cfg.vector_search_beam_size is None

    def test_ai_config_validation(self) -> None:
        with pytest.raises(ValidationError):
            AIConfig(default_limit=0)
        with pytest.raises(ValidationError):
            AIConfig(similarity_threshold=1.5)

    def test_ai_config_beam_size(self) -> None:
        cfg = AIConfig(vector_search_beam_size=64)
        assert cfg.vector_search_beam_size == 64

    def test_ai_config_beam_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            AIConfig(vector_search_beam_size=0)
