"""CockroachDB Python Library — base package.

Provides decorators, types, configuration, and exception hierarchy
for building CockroachDB-aware Python applications.
"""

from __future__ import annotations

import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)

from cockroachdb.decorators import (
    changefeed_handler,
    crdb_region,
    crdb_retry,
    follower_read,
    global_table,
    regional_by_row,
    semantic_search,
    vector_search,
)
from cockroachdb.exceptions import (
    CircuitBreakerOpenError,
    CockroachDBError,
    CockroachDBRetryExhausted,
    RegionValidationError,
)
from cockroachdb.types import (
    DistanceMetric,
    IsolationLevel,
    RetryPolicy,
    TransactionOutcome,
)

__version__ = "0.1.0"

__all__ = [
    "CircuitBreakerOpenError",
    # Exceptions
    "CockroachDBError",
    "CockroachDBRetryExhausted",
    "DistanceMetric",
    "IsolationLevel",
    "RegionValidationError",
    # Types
    "RetryPolicy",
    "TransactionOutcome",
    # Meta
    "__version__",
    "changefeed_handler",
    "crdb_region",
    # Decorators
    "crdb_retry",
    "follower_read",
    "global_table",
    "regional_by_row",
    "semantic_search",
    "vector_search",
]
