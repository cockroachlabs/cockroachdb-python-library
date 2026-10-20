"""CockroachDB CDC — webhook handlers, changefeed management, and framework integration."""

from __future__ import annotations

from cockroachdb.cdc.handler import ChangefeedHandlerRegistry
from cockroachdb.cdc.manager import ChangefeedManager
from cockroachdb.cdc.metrics import (
    CDCMetrics,
    InMemoryCDCMetrics,
    NoopCDCMetrics,
)
from cockroachdb.cdc.models import ChangefeedConfig, ChangefeedEvent, ChangefeedPayload
from cockroachdb.cdc.router import create_fastapi_router, create_flask_blueprint

__all__ = [
    "CDCMetrics",
    "ChangefeedConfig",
    "ChangefeedEvent",
    "ChangefeedHandlerRegistry",
    "ChangefeedManager",
    "ChangefeedPayload",
    "InMemoryCDCMetrics",
    "NoopCDCMetrics",
    "create_fastapi_router",
    "create_flask_blueprint",
]

# PrometheusCDCMetrics is only available when prometheus-client is installed.
try:
    from cockroachdb.cdc.metrics import PrometheusCDCMetrics as PrometheusCDCMetrics

    __all__.append("PrometheusCDCMetrics")
except ImportError:
    pass
