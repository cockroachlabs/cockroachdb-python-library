"""Fast unit test for CDC — no Docker, no changefeed.

CDC processing is pure logic: classify the event from before/after presence, and
project the ``after`` image onto an ``Idea``. The library ships a real parser and
registry, so we exercise two paths: ``ChangefeedPayload.parse`` directly on a
wrapped webhook envelope, and the full ``ChangefeedHandlerRegistry.dispatch``
decode-and-dispatch to the decorated handler (mirrors the Java CDC unit test).
"""

from __future__ import annotations

import asyncio

from cdc_handler import IdeaChangefeedHandler
from cockroachdb.cdc import (
    ChangefeedHandlerRegistry,
    ChangefeedPayload,
    InMemoryCDCMetrics,
)
from cockroachdb.types import CDCOperation


# tag::cdc-unit-test[]
def test_parse_envelope_classifies_insert_and_delete() -> None:
    envelope = (
        '{"payload":['
        '{"after":{"id":1,"text":"Dark mode","votes":7},"key":[1],'
        '"topic":"ideas","updated":"1700000000.0"},'
        '{"after":null,"before":{"id":1,"text":"Dark mode","votes":7},"key":[1],'
        '"topic":"ideas","updated":"1700000001.0"}'
        '],"length":2}'
    )
    events = ChangefeedPayload.parse(envelope).events
    assert [e.operation for e in events] == [CDCOperation.INSERT, CDCOperation.DELETE]


def test_registry_dispatches_webhook_to_handler() -> None:
    handler = IdeaChangefeedHandler()
    metrics = InMemoryCDCMetrics()
    registry = ChangefeedHandlerRegistry(metrics=metrics)
    registry.register(handler.on_change)

    envelope = (
        '{"payload":['
        '{"after":{"id":12,"text":"Full-text search","votes":12},"key":[12],'
        '"topic":"ideas","updated":"1700000002.0"}'
        '],"length":1}'
    )
    results = asyncio.run(registry.dispatch("/webhooks/ideas", envelope))

    assert len(results) == 1
    assert len(handler.handled) == 1
    seen = handler.handled[0]
    assert seen.id == 12
    assert seen.text == "Full-text search"
    assert seen.votes == 12
    assert handler.deletes == 0
    assert metrics.total_events == 1
# end::cdc-unit-test[]
