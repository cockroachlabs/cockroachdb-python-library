"""SQLAlchemy engine factory with CockroachDB-optimized defaults.

Creates engines pre-configured for CockroachDB best practices:
pool_pre_ping for connection health checks, conservative pool recycling,
and automatic event listener registration for region/follower-read injection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine

from cockroachdb.config import CockroachDBConfig
from cockroachdb.sqla.events import setup_cockroachdb_events

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_COCKROACHDB_ENGINE_DEFAULTS: dict[str, Any] = {
    "pool_size": 10,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}


def create_cockroachdb_engine(
    url: str,
    config: CockroachDBConfig | None = None,
    multiregion_base: type | None = None,
    multiregion_mode: str = "warn",
    **kwargs: Any,
) -> Engine:
    """Create a SQLAlchemy engine with CockroachDB-optimized defaults.

    Applies sensible defaults for CockroachDB workloads:
    - ``pool_size=10`` — balanced for typical multi-region deployments.
    - ``pool_pre_ping=True`` — detects stale connections before use.
    - ``pool_recycle=1800`` — recycles connections every 30 minutes to
      avoid load-balancer idle timeouts.

    Registers SQLAlchemy event listeners that automatically inject
    ``SET crdb_region`` and ``SET TRANSACTION AS OF SYSTEM TIME``
    statements when :class:`RegionContext` or :class:`FollowerReadContext`
    contextvars are active.

    Args:
        url: SQLAlchemy connection URL (e.g.,
            ``cockroachdb://user:pass@host:26257/db``).
        config: Optional library configuration. When ``None`` a default
            :class:`CockroachDBConfig` is used.
        multiregion_base: Opt-in. When given a SQLAlchemy declarative base,
            runs the read-only multi-region schema check (see
            :func:`verify_multiregion_schema`) against the just-created engine.
            Omit it (the default ``None``) to skip the check entirely.
        multiregion_mode: ``"none"`` | ``"warn"`` | ``"validate"`` — how the
            check reacts (default ``"warn"``). Only used when ``multiregion_base``
            is provided.
        **kwargs: Additional keyword arguments forwarded to
            :func:`sqlalchemy.create_engine`. These override the
            CockroachDB defaults listed above.

    Returns:
        A fully configured :class:`sqlalchemy.engine.Engine`.
    """
    merged = {**_COCKROACHDB_ENGINE_DEFAULTS, **kwargs}
    engine = create_engine(url, **merged)

    resolved_config = config or CockroachDBConfig()
    setup_cockroachdb_events(engine, resolved_config)

    logger.info(
        "CockroachDB engine created: pool_size=%s, pool_pre_ping=%s, pool_recycle=%s",
        merged.get("pool_size"),
        merged.get("pool_pre_ping"),
        merged.get("pool_recycle"),
    )

    if multiregion_base is not None:
        from cockroachdb.sqla.multiregion import verify_multiregion_schema

        verify_multiregion_schema(engine, multiregion_base, mode=multiregion_mode)

    return engine
