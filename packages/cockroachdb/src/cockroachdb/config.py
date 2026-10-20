"""Pydantic-based configuration for the CockroachDB Python Library."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    """Retry policy configuration."""

    max_retries: int = Field(default=3, ge=0, le=50)
    base_delay: float = Field(default=0.1, gt=0)
    max_delay: float = Field(default=5.0, gt=0)
    multiplier: float = Field(default=2.0, gt=1.0)
    jitter_factor: float = Field(default=0.1, ge=0, le=1.0)


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration."""

    enabled: bool = True
    failure_threshold: int = Field(default=5, ge=1)
    recovery_timeout: float = Field(default=30.0, gt=0)
    half_open_max_calls: int = Field(default=1, ge=1)


class RegionConfig(BaseModel):
    """Multi-region configuration."""

    default_region: str | None = None
    allowed_regions: list[str] = Field(default_factory=list)
    region_header: str = "X-CockroachDB-Region"
    validate_format: bool = True


class FollowerReadConfig(BaseModel):
    """Follower read configuration."""

    enabled: bool = True
    default_staleness: str = "follower_read_timestamp()"


class MetricsConfig(BaseModel):
    """Metrics and observability configuration."""

    enabled: bool = True
    prefix: str = "cockroachdb"


class AIConfig(BaseModel):
    """AI and vector search configuration."""

    default_metric: str = "cosine"
    default_limit: int = Field(default=10, ge=1)
    embedding_dimensions: int = Field(default=1536, ge=1)
    similarity_threshold: float = Field(default=0.7, ge=0, le=1.0)
    max_context_documents: int = Field(default=5, ge=1)
    vector_search_beam_size: int | None = Field(
        default=None,
        ge=1,
        description="Session-level vector_search_beam_size. "
        "Controls how many partitions are explored during vector index search. "
        "Default is None (use CockroachDB default of 32).",
    )


class CockroachDBConfig(BaseModel):
    """Root configuration for the CockroachDB Python Library."""

    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    region: RegionConfig = Field(default_factory=RegionConfig)
    follower_read: FollowerReadConfig = Field(default_factory=FollowerReadConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    ai: AIConfig = Field(default_factory=AIConfig)

    # NOTE: env_prefix only takes effect on a pydantic-settings BaseSettings
    # model; on a plain BaseModel it is inert. Kept to document intent — real
    # env loading is a separate feature (would require pydantic-settings).
    model_config = {"env_prefix": "CRDB_"}  # type: ignore[typeddict-unknown-key]
