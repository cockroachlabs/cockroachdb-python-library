"""Metered upvotes: run each read-modify-write through the core RetryEngine so
retry and transaction counters move under contention.

Fundamentals (``service.py``) proves ``@crdb_retry`` lands every vote. This layers
the library's metrics on top: ``RetryEngine`` records one transaction per run
(COMMITTED or RETRIED) and one retry per serialization conflict (40001) into any
``MetricsCollector`` — here the ``InMemoryMetricsCollector`` you can inspect.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import psycopg
import repository

# tag::metrics-config[]
from cockroachdb.core import RetryEngine
from cockroachdb.core.metrics import InMemoryMetricsCollector
from cockroachdb.types import RetryPolicy

# end::metrics-config[]

if TYPE_CHECKING:
    from cockroachdb.types import MetricsCollector

# Pause between read and write to widen the conflict window. Same knob as the
# fundamentals demo. ponytail: fixed delay, tune per cluster.
CONTENTION_DELAY = 0.05


class MeteredIdeaService:
    """Upvotes wrapped in ``RetryEngine.run`` so every attempt is counted."""

    def __init__(
        self,
        dsn: str,
        metrics: MetricsCollector | None = None,
        *,
        max_retries: int = 25,
    ) -> None:
        self._dsn = dsn
        self.metrics = metrics or InMemoryMetricsCollector()
        # tag::metrics-engine[]
        self._engine = RetryEngine(
            policy=RetryPolicy(max_retries=max_retries, base_delay=0.02),
            metrics=self.metrics,
        )
        # end::metrics-engine[]

    # tag::metered-upvote[]
    def upvote(self, idea_id: int) -> None:
        """One metered upvote. ``RetryEngine.run`` records the transaction outcome
        and any 40001 retries into the attached metrics collector."""
        self._engine.run(lambda: self._apply_upvote(idea_id))

    # end::metered-upvote[]

    def _apply_upvote(self, idea_id: int) -> None:
        """Read current votes, add one, write it back — in one SERIALIZABLE tx."""
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            with conn.transaction(), conn.cursor() as cur:
                votes = repository.current_votes(cur, idea_id)
                time.sleep(CONTENTION_DELAY)
                repository.update_votes(cur, idea_id, votes + 1)
