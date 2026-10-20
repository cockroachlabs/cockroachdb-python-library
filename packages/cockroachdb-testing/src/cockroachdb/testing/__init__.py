"""CockroachDB Python Library — testing utilities.

Provides test fixtures, retry simulators, concurrency runners,
and factory helpers for testing CockroachDB-aware applications.
"""

from __future__ import annotations

from cockroachdb.testing.concurrency import ConcurrencyResult, ConcurrencyRunner
from cockroachdb.testing.factories import (
    ChangefeedEventFactory,
    VectorSearchResultFactory,
)
from cockroachdb.testing.fixtures import CockroachDBFixture, crdb_fixture
from cockroachdb.testing.retry_simulator import FakeSerializationError, RetrySimulator

__version__ = "0.1.0"

__all__ = [
    # Factories
    "ChangefeedEventFactory",
    # Fixtures
    "CockroachDBFixture",
    "ConcurrencyResult",
    # Concurrency
    "ConcurrencyRunner",
    "FakeSerializationError",
    # Retry simulation
    "RetrySimulator",
    "VectorSearchResultFactory",
    # Meta
    "__version__",
    "crdb_fixture",
]
