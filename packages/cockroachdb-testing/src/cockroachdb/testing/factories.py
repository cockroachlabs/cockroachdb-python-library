"""Test data factories for CockroachDB domain objects.

Provides ``build(**overrides)`` class methods that produce realistic
test instances of core CockroachDB data types with sensible defaults.
All fields can be overridden for specific test scenarios.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from cockroachdb.types import CDCOperation, DistanceMetric, VectorSearchResult

# ---------------------------------------------------------------------------
# Changefeed event (self-contained — the CDC package is not yet available)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangefeedEvent:
    """Lightweight changefeed event for testing.

    Mirrors the shape expected by ``@changefeed_handler`` decorated functions.
    When the ``cockroachdb-cdc`` package ships its own ``ChangefeedEvent``,
    test code can use ``ChangefeedEventFactory`` to build either type.
    """

    table: str
    key: list[Any]
    operation: CDCOperation
    timestamp: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChangefeedEventFactory:
    """Factory for building ``ChangefeedEvent`` test instances.

    Example::

        event = ChangefeedEventFactory.build(
            table="orders",
            operation=CDCOperation.INSERT,
            after={"id": 1, "total": 99.99},
        )
    """

    _defaults: ClassVar[dict[str, Any]] = {
        "table": "test_table",
        "key": None,  # generated per-call
        "operation": CDCOperation.INSERT,
        "timestamp": None,  # generated per-call
        "before": None,
        "after": None,
        "metadata": None,  # generated per-call
    }

    @classmethod
    def build(cls, **overrides: Any) -> ChangefeedEvent:
        """Create a ``ChangefeedEvent`` with defaults merged with *overrides*.

        Args:
            **overrides: Field values that replace the defaults.

        Returns:
            A new ``ChangefeedEvent`` instance.
        """
        values = {**cls._defaults, **overrides}

        # Generate dynamic defaults for fields that vary per instance.
        if values["key"] is None:
            values["key"] = [str(uuid.uuid4())]
        if values["timestamp"] is None:
            values["timestamp"] = f"{time.time_ns()}"
        if values["after"] is None and values["operation"] != CDCOperation.DELETE:
            values["after"] = {"id": values["key"][0], "value": "test"}
        if values["metadata"] is None:
            values["metadata"] = {}

        return ChangefeedEvent(**values)


# ---------------------------------------------------------------------------
# Vector search result
# ---------------------------------------------------------------------------


class VectorSearchResultFactory:
    """Factory for building ``VectorSearchResult`` test instances.

    Example::

        result = VectorSearchResultFactory.build(
            distance=0.15,
            document={"text": "CockroachDB is a distributed SQL database"},
        )
    """

    _defaults: ClassVar[dict[str, Any]] = {
        "id": None,  # generated per-call
        "document": None,  # generated per-call
        "distance": 0.25,
        "similarity": None,  # computed from distance
    }

    @classmethod
    def build(
        cls,
        *,
        metric: DistanceMetric = DistanceMetric.COSINE,
        **overrides: Any,
    ) -> VectorSearchResult:
        """Create a ``VectorSearchResult`` with defaults merged with *overrides*.

        Args:
            metric: The distance metric used to derive ``similarity`` when it
                is not explicitly provided.
            **overrides: Field values that replace the defaults.

        Returns:
            A new ``VectorSearchResult`` instance.
        """
        values = {**cls._defaults, **overrides}

        if values["id"] is None:
            values["id"] = str(uuid.uuid4())
        if values["document"] is None:
            values["document"] = {"text": "sample document", "source": "factory"}

        distance = values["distance"]
        if values["similarity"] is None:
            values["similarity"] = metric.to_similarity(distance)

        return VectorSearchResult(
            id=values["id"],
            document=values["document"],
            distance=values["distance"],
            similarity=values["similarity"],
        )
