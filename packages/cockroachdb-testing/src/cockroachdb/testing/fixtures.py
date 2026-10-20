"""CockroachDB test fixtures using testcontainers.

Provides a managed CockroachDB container for integration testing
with automatic lifecycle management and pytest fixture support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from testcontainers.cockroachdb import CockroachDBContainer

if TYPE_CHECKING:
    from collections.abc import Generator

    import psycopg


class CockroachDBFixture:
    """Managed CockroachDB container for integration tests.

    Wraps testcontainers ``CockroachDBContainer`` with a simplified API
    for starting, stopping, and interacting with a disposable CockroachDB
    instance.

    Usage::

        fixture = CockroachDBFixture(image="cockroachdb/cockroach:v24.3.0")
        fixture.start()
        fixture.execute_sql("CREATE TABLE t (id INT PRIMARY KEY)")
        fixture.stop()

    Or as a context manager::

        with CockroachDBFixture() as db:
            db.execute_sql("SELECT 1")
    """

    def __init__(
        self,
        image: str = "cockroachdb/cockroach:v24.3.0",
        port: int = 26257,
    ) -> None:
        self._image = image
        self._port = port
        self._container: CockroachDBContainer | None = None

    def start(self) -> CockroachDBFixture:
        """Start the CockroachDB container.

        Returns:
            Self for fluent chaining.

        Raises:
            RuntimeError: If the container is already running.
        """
        if self._container is not None:
            msg = "Container is already running — call stop() first"
            raise RuntimeError(msg)

        self._container = CockroachDBContainer(
            image=self._image,
        )
        self._container.with_exposed_ports(self._port)
        self._container.start()
        return self

    def stop(self) -> None:
        """Stop and remove the CockroachDB container."""
        if self._container is not None:
            self._container.stop()
            self._container = None

    @property
    def connection_url(self) -> str:
        """Return the connection string for the running container.

        Returns:
            A ``postgresql://`` connection URL pointing at the container.

        Raises:
            RuntimeError: If the container has not been started.
        """
        container = self._ensure_running()
        return container.get_connection_url()

    def get_connection(self) -> psycopg.Connection[Any]:
        """Open a new psycopg connection to the running container.

        Returns:
            An open ``psycopg.Connection``.

        Raises:
            RuntimeError: If the container has not been started.
        """
        import psycopg

        return psycopg.connect(self.connection_url)

    def execute_sql(self, sql: str) -> list[Any]:
        """Execute a SQL statement and return all rows.

        Args:
            sql: The SQL statement to execute.

        Returns:
            A list of result rows (empty for DDL/DML without RETURNING).
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                if cur.description is not None:
                    return cur.fetchall()
                conn.commit()
                return []
        finally:
            conn.close()

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> CockroachDBFixture:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.stop()

    # -- Internal ---------------------------------------------------------

    def _ensure_running(self) -> CockroachDBContainer:
        if self._container is None:
            msg = "Container has not been started — call start() first"
            raise RuntimeError(msg)
        return self._container


# ---------------------------------------------------------------------------
# Pytest fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def crdb_fixture() -> Generator[CockroachDBFixture, None, None]:
    """Pytest session-scoped fixture that provides a CockroachDB container.

    Yields:
        A started ``CockroachDBFixture`` instance.  The container is
        automatically stopped when the test session ends.

    Example::

        def test_something(crdb_fixture: CockroachDBFixture) -> None:
            rows = crdb_fixture.execute_sql("SELECT 1")
            assert rows[0][0] == 1
    """
    with CockroachDBFixture() as fixture:
        yield fixture
