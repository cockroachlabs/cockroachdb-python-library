"""CockroachDB Python Library — core engine layer.

Provides the template pattern, retry engine, circuit breaker,
region context, and follower read support for CockroachDB.
"""

from __future__ import annotations

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.otel_metrics import OpenTelemetryMetricsCollector
from cockroachdb.core.region import RegionContext
from cockroachdb.core.retry import RetryEngine
from cockroachdb.core.template import AsyncCockroachDBTemplate, CockroachDBTemplate
from cockroachdb.core.vcluster import VClusterContext, VClusterSettings

__version__ = "0.1.0"

__all__ = [
    "AsyncCockroachDBTemplate",
    "CockroachDBTemplate",
    "FollowerReadContext",
    "OpenTelemetryMetricsCollector",
    "RegionContext",
    "RetryEngine",
    "VClusterContext",
    "VClusterSettings",
    "__version__",
]
