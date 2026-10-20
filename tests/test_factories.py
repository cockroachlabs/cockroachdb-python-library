"""Tests for cockroachdb.testing.factories."""

from __future__ import annotations

import pytest

from cockroachdb.testing.factories import (
    ChangefeedEvent,
    ChangefeedEventFactory,
    VectorSearchResultFactory,
)
from cockroachdb.types import CDCOperation, DistanceMetric, VectorSearchResult


class TestChangefeedEventFactory:
    """Tests for ChangefeedEventFactory.build()."""

    def test_default_build(self) -> None:
        event = ChangefeedEventFactory.build()
        assert isinstance(event, ChangefeedEvent)
        assert event.table == "test_table"
        assert event.operation == CDCOperation.INSERT
        assert event.key is not None and len(event.key) == 1
        assert event.timestamp is not None
        assert event.after is not None
        assert event.metadata == {}

    def test_override_table(self) -> None:
        event = ChangefeedEventFactory.build(table="orders")
        assert event.table == "orders"

    def test_override_operation(self) -> None:
        event = ChangefeedEventFactory.build(operation=CDCOperation.UPDATE)
        assert event.operation == CDCOperation.UPDATE

    def test_delete_operation_no_after(self) -> None:
        event = ChangefeedEventFactory.build(operation=CDCOperation.DELETE)
        assert event.after is None

    def test_custom_after(self) -> None:
        event = ChangefeedEventFactory.build(after={"id": 1, "name": "test"})
        assert event.after == {"id": 1, "name": "test"}

    def test_custom_key(self) -> None:
        event = ChangefeedEventFactory.build(key=["abc-123"])
        assert event.key == ["abc-123"]

    def test_each_build_has_unique_key(self) -> None:
        e1 = ChangefeedEventFactory.build()
        e2 = ChangefeedEventFactory.build()
        assert e1.key != e2.key

    def test_frozen_dataclass(self) -> None:
        event = ChangefeedEventFactory.build()
        with pytest.raises(AttributeError):
            event.table = "nope"  # type: ignore[misc]


class TestVectorSearchResultFactory:
    """Tests for VectorSearchResultFactory.build()."""

    def test_default_build(self) -> None:
        result = VectorSearchResultFactory.build()
        assert isinstance(result, VectorSearchResult)
        assert result.id is not None
        assert result.document == {"text": "sample document", "source": "factory"}
        assert result.distance == 0.25
        # cosine: 1 - 0.25 = 0.75
        assert result.similarity == pytest.approx(0.75)

    def test_custom_distance(self) -> None:
        result = VectorSearchResultFactory.build(distance=0.1)
        assert result.distance == 0.1
        assert result.similarity == pytest.approx(0.9)

    def test_euclidean_metric(self) -> None:
        result = VectorSearchResultFactory.build(metric=DistanceMetric.EUCLIDEAN, distance=1.0)
        # 1 / (1 + 1) = 0.5
        assert result.similarity == pytest.approx(0.5)

    def test_inner_product_metric(self) -> None:
        result = VectorSearchResultFactory.build(metric=DistanceMetric.INNER_PRODUCT, distance=0.3)
        assert result.similarity == pytest.approx(-0.3)

    def test_custom_document(self) -> None:
        doc = {"text": "CockroachDB is great"}
        result = VectorSearchResultFactory.build(document=doc)
        assert result.document == doc

    def test_custom_id(self) -> None:
        result = VectorSearchResultFactory.build(id="my-id")
        assert result.id == "my-id"

    def test_explicit_similarity_overrides_computed(self) -> None:
        result = VectorSearchResultFactory.build(similarity=0.99)
        assert result.similarity == 0.99

    def test_each_build_has_unique_id(self) -> None:
        r1 = VectorSearchResultFactory.build()
        r2 = VectorSearchResultFactory.build()
        assert r1.id != r2.id
