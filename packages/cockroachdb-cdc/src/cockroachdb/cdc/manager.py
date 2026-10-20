"""Programmatic changefeed lifecycle management for CockroachDB."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from cockroachdb.cdc.models import ChangefeedConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChangefeedJob:
    """Represents an active CockroachDB changefeed job.

    Attributes:
        job_id: The CockroachDB job identifier.
        description: Human-readable job description.
        status: Current job status (e.g. ``running``, ``paused``).
        created: Timestamp when the job was created.
        details: Additional metadata from SHOW CHANGEFEED JOBS.
    """

    job_id: int
    description: str
    status: str
    created: str
    details: dict[str, Any] = field(default_factory=dict)


class ChangefeedManager:
    """Manage CockroachDB changefeed lifecycle via SQL.

    Provides methods to create, cancel, pause, resume, and list changefeed
    jobs using a psycopg connection.

    Example::

        import psycopg
        from cockroachdb.cdc import ChangefeedManager, ChangefeedConfig

        conn = psycopg.connect("postgresql://root@localhost:26257/defaultdb")
        mgr = ChangefeedManager(conn)

        job_id = mgr.create(
            table="orders",
            webhook_url="http://localhost:8000/webhooks/orders",
            config=ChangefeedConfig(diff=True, updated=True),
        )
        print(f"Created changefeed job: {job_id}")

        mgr.cancel(job_id)
    """

    def __init__(self, connection: Any) -> None:
        """Initialise the manager with a psycopg connection.

        Args:
            connection: A ``psycopg.Connection`` or compatible object supporting
                ``execute`` and ``fetchall``.
        """
        self._conn = connection

    def create(
        self,
        table: str,
        webhook_url: str,
        *,
        config: ChangefeedConfig | None = None,
        options: dict[str, str] | None = None,
    ) -> int:
        """Create a new changefeed for the given table.

        Executes ``CREATE CHANGEFEED FOR <table> INTO '<webhook_url>'``
        with the supplied configuration options.

        Args:
            table: Fully-qualified table name to watch.
            webhook_url: Webhook sink URL that will receive CDC payloads.
            config: Optional changefeed configuration.
            options: Additional raw WITH options as key-value pairs.

        Returns:
            The CockroachDB job ID of the created changefeed.

        Raises:
            RuntimeError: If the CREATE CHANGEFEED statement fails.
        """
        cfg = config or ChangefeedConfig()
        options_sql = cfg.to_options_sql()

        if options:
            extra = ", ".join(f"{k} = '{v}'" for k, v in options.items())
            options_sql = f"{options_sql}, {extra}"

        sql = (
            f"CREATE CHANGEFEED FOR {table} "
            f"INTO 'webhook-https://{_strip_scheme(webhook_url)}' "
            f"WITH {options_sql}"
        )

        logger.info("Creating changefeed: %s", sql)
        try:
            cursor = self._conn.execute(sql)
            row = cursor.fetchone()
            if row:
                job_id = int(row[0])
                logger.info("Created changefeed job %d for table %s", job_id, table)
                return job_id
            raise RuntimeError("CREATE CHANGEFEED returned no job ID")
        except Exception as exc:
            raise RuntimeError(f"Failed to create changefeed for {table}: {exc}") from exc

    def cancel(self, job_id: int) -> None:
        """Cancel a running changefeed job.

        Args:
            job_id: The CockroachDB job ID to cancel.

        Raises:
            RuntimeError: If the CANCEL JOB statement fails.
        """
        sql = f"CANCEL JOB {job_id}"
        logger.info("Cancelling changefeed job %d", job_id)
        try:
            self._conn.execute(sql)
            logger.info("Cancelled changefeed job %d", job_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to cancel job {job_id}: {exc}") from exc

    def pause(self, job_id: int) -> None:
        """Pause a running changefeed job.

        Args:
            job_id: The CockroachDB job ID to pause.

        Raises:
            RuntimeError: If the PAUSE JOB statement fails.
        """
        sql = f"PAUSE JOB {job_id}"
        logger.info("Pausing changefeed job %d", job_id)
        try:
            self._conn.execute(sql)
            logger.info("Paused changefeed job %d", job_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to pause job {job_id}: {exc}") from exc

    def resume(self, job_id: int) -> None:
        """Resume a paused changefeed job.

        Args:
            job_id: The CockroachDB job ID to resume.

        Raises:
            RuntimeError: If the RESUME JOB statement fails.
        """
        sql = f"RESUME JOB {job_id}"
        logger.info("Resuming changefeed job %d", job_id)
        try:
            self._conn.execute(sql)
            logger.info("Resumed changefeed job %d", job_id)
        except Exception as exc:
            raise RuntimeError(f"Failed to resume job {job_id}: {exc}") from exc

    def list_active(self) -> list[ChangefeedJob]:
        """List all active changefeed jobs.

        Executes ``SHOW CHANGEFEED JOBS`` and returns structured results.

        Returns:
            List of active :class:`ChangefeedJob` instances.
        """
        sql = "SHOW CHANGEFEED JOBS"
        try:
            cursor = self._conn.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            jobs: list[ChangefeedJob] = []
            for row in rows:
                row_dict = dict(zip(columns, row, strict=False)) if columns else {}
                jobs.append(
                    ChangefeedJob(
                        job_id=int(row_dict.get("job_id", row[0])),
                        description=str(
                            row_dict.get("description", row[1] if len(row) > 1 else "")
                        ),
                        status=str(row_dict.get("status", row[2] if len(row) > 2 else "")),
                        created=str(row_dict.get("created", row[3] if len(row) > 3 else "")),
                        details=row_dict,
                    )
                )
            return jobs
        except Exception as exc:
            raise RuntimeError(f"Failed to list changefeed jobs: {exc}") from exc


def _strip_scheme(url: str) -> str:
    """Strip http:// or https:// from a URL for CockroachDB webhook sink format."""
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    return url
