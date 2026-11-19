"""Throwaway insecure CockroachDB via testcontainers.

The published `cockroachdb-testing` fixture and the `testcontainers` cockroachdb
module both boot CockroachDB in SECURE mode, which requires a client certificate
this example does not ship (and psycopg3 cannot parse the module's
`cockroachdb+psycopg2://` URL). So we run the same CockroachDB image in
`--insecure` mode via the generic testcontainers API and hand back a plain
`postgresql://` DSN — identical to how the library's own examples connect
(e.g. `postgresql://root@localhost:26257/defaultdb`).
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator

import psycopg

IMAGE = "cockroachdb/cockroach:v24.3.0"


@contextlib.contextmanager
def insecure_crdb(image: str = IMAGE) -> Iterator[str]:
    """Start an insecure single-node CockroachDB; yield a psycopg DSN.

    ``image`` defaults to the pinned fundamentals image; the semantic-search IT
    overrides it with a VECTOR-capable image (v25.2+).
    """
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    container = (
        DockerContainer(image)
        .with_command("start-single-node --insecure")
        .with_exposed_ports(26257)
    )
    container.start()
    try:
        wait_for_logs(container, "CockroachDB node starting", timeout=90)
        host = container.get_container_host_ip()
        port = container.get_exposed_port(26257)
        dsn = f"postgresql://root@{host}:{port}/defaultdb?sslmode=disable"
        _wait_ready(dsn)
        yield dsn
    finally:
        container.stop()


def _wait_ready(dsn: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            time.sleep(1)
    msg = "CockroachDB did not become ready in time"
    raise RuntimeError(msg)
