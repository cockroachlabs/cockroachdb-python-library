"""Fixtures for integration tests against live CockroachDB clusters.

The fixtures detect whether a CockroachDB instance is already running on
localhost:26257. If so, they reuse it (no docker-compose lifecycle). If not,
they start and stop the cluster via docker-compose.

Run a specific cluster tier::

    # 1-node (default — fast)
    docker-compose -f docker/docker-compose.1node.yml up -d
    pytest tests/integration/ -v

    # 3-node (distributed)
    docker-compose -f docker/docker-compose.3node.yml up -d
    pytest tests/integration/ -k 3node -v
"""

from __future__ import annotations

import os
import subprocess
import time

import pytest

DOCKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docker")
CRDB_URL = "cockroachdb+psycopg://root@localhost:26257/defaultdb?sslmode=disable"


def _is_crdb_running() -> bool:
    """Check if CockroachDB is already reachable on localhost:26257."""
    try:
        import psycopg

        conn = psycopg.connect(
            "host=localhost port=26257 user=root dbname=defaultdb sslmode=disable",
            autocommit=True,
        )
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


def _compose_up(compose_file: str, timeout: int = 60) -> None:
    """Start a CockroachDB cluster via docker-compose."""
    path = os.path.join(DOCKER_DIR, compose_file)
    subprocess.run(
        ["docker-compose", "-f", path, "up", "-d"],
        check=True,
        capture_output=True,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_crdb_running():
            return
        time.sleep(2)
    raise TimeoutError(f"CockroachDB did not become ready within {timeout}s")


def _compose_down(compose_file: str) -> None:
    """Stop and clean up a CockroachDB cluster."""
    path = os.path.join(DOCKER_DIR, compose_file)
    subprocess.run(
        ["docker-compose", "-f", path, "down", "-v"],
        capture_output=True,
    )


@pytest.fixture(scope="module")
def crdb_1node():
    already_running = _is_crdb_running()
    if not already_running:
        _compose_up("docker-compose.1node.yml")
    yield CRDB_URL
    if not already_running:
        _compose_down("docker-compose.1node.yml")


@pytest.fixture(scope="module")
def crdb_3node():
    already_running = _is_crdb_running()
    if not already_running:
        _compose_up("docker-compose.3node.yml", timeout=90)
    yield CRDB_URL
    if not already_running:
        _compose_down("docker-compose.3node.yml")
