"""SQLAlchemy event listeners for CockroachDB context injection.

Automatically injects ``SET crdb_region`` and
``SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp()``
statements based on active :mod:`contextvars`.

These listeners are registered once per engine via
:func:`setup_cockroachdb_events` and operate transparently — no
application code changes are needed beyond setting the context.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import event

from cockroachdb.config import CockroachDBConfig
from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def setup_cockroachdb_events(
    engine: Engine,
    config: CockroachDBConfig | None = None,
) -> None:
    """Register all CockroachDB event listeners on *engine*.

    Safe to call multiple times — listeners are idempotent because
    SQLAlchemy deduplicates identical listener registrations.

    Args:
        engine: The SQLAlchemy engine to instrument.
        config: Optional configuration; controls follower-read staleness
            expression and whether listeners are active.
    """
    resolved = config or CockroachDBConfig()

    @event.listens_for(engine, "connect")
    def _on_connect(
        dbapi_connection: Any,
        connection_record: Any,
    ) -> None:
        """Log new physical connections for observability."""
        logger.debug("CockroachDB: new physical connection established")

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> tuple[str, Any] | None:
        """Inject SET statements for region and follower-read contexts.

        Reads from :data:`RegionContext` and :data:`FollowerReadContext`
        contextvars. When a context is active, the corresponding SQL
        ``SET`` statement is executed on the raw DBAPI cursor *before*
        the user's statement runs.
        """
        region = RegionContext.current()
        follower_active = FollowerReadContext.is_active()

        if region is not None:
            logger.debug("CockroachDB: injecting SET crdb_region = %r", region)
            cursor.execute(f"SET crdb_region = '{region}'")

        if follower_active and resolved.follower_read.enabled:
            staleness = (
                FollowerReadContext.current_staleness() or resolved.follower_read.default_staleness
            )
            logger.debug(
                "CockroachDB: injecting follower read AS OF SYSTEM TIME %s",
                staleness,
            )
            cursor.execute(f"SET TRANSACTION AS OF SYSTEM TIME {staleness}")

        return None

    logger.debug("CockroachDB event listeners registered on engine %s", engine.url)
