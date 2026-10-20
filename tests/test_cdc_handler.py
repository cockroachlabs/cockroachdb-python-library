"""Tests for cockroachdb.cdc.handler — handler registry and dispatch."""

from __future__ import annotations

import json

import pytest

from cockroachdb.cdc.handler import ChangefeedHandlerRegistry


def _make_handler(table="orders", operations=None, endpoint="/webhooks/orders"):
    """Create a fake handler function with __crdb_changefeed__ metadata."""
    operations = operations or ["insert"]

    def handler(event):
        return {"handled": event.table}

    handler.__crdb_changefeed__ = {
        "table": table,
        "operations": operations,
        "endpoint": endpoint,
    }
    return handler


def _make_async_handler(table="orders", operations=None, endpoint="/webhooks/orders"):
    """Create a fake async handler with __crdb_changefeed__ metadata."""
    operations = operations or ["insert"]

    async def handler(event):
        return {"handled": event.table}

    handler.__crdb_changefeed__ = {
        "table": table,
        "operations": operations,
        "endpoint": endpoint,
    }
    return handler


class TestChangefeedHandlerRegistryRegister:
    """Tests for ChangefeedHandlerRegistry.register()."""

    def test_registers_handler(self):
        registry = ChangefeedHandlerRegistry()
        handler = _make_handler()
        registry.register(handler)

        handlers = registry.get_handlers()
        assert "/webhooks/orders" in handlers
        assert handlers["/webhooks/orders"]["table"] == "orders"

    def test_raises_on_missing_metadata(self):
        registry = ChangefeedHandlerRegistry()

        def plain_fn(event):
            pass

        with pytest.raises(ValueError, match="not decorated"):
            registry.register(plain_fn)

    def test_raises_on_duplicate_endpoint(self):
        registry = ChangefeedHandlerRegistry()
        handler1 = _make_handler(endpoint="/webhooks/x")
        handler2 = _make_handler(table="other", endpoint="/webhooks/x")

        registry.register(handler1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(handler2)

    def test_returns_same_function(self):
        registry = ChangefeedHandlerRegistry()
        handler = _make_handler()
        result = registry.register(handler)
        assert result is handler


class TestChangefeedHandlerRegistryDispatch:
    """Tests for ChangefeedHandlerRegistry.dispatch()."""

    @pytest.mark.asyncio
    async def test_dispatches_matching_event(self):
        registry = ChangefeedHandlerRegistry()
        handler = _make_handler(operations=["insert"])
        registry.register(handler)

        payload = json.dumps(
            {
                "payload": [
                    {
                        "after": {"id": 1, "total": 50},
                        "before": None,
                        "key": [1],
                        "topic": "orders",
                        "updated": "1716300000.0000000000",
                    }
                ],
                "length": 1,
                "resolved": None,
            }
        )

        results = await registry.dispatch("/webhooks/orders", payload)
        assert len(results) == 1
        assert results[0]["handled"] == "orders"

    @pytest.mark.asyncio
    async def test_skips_non_matching_operation(self):
        registry = ChangefeedHandlerRegistry()
        handler = _make_handler(operations=["delete"])
        registry.register(handler)

        # This is an insert event, handler only cares about delete
        payload = json.dumps(
            {
                "payload": [
                    {
                        "after": {"id": 1},
                        "before": None,
                        "key": [1],
                        "topic": "orders",
                        "updated": "1716300000.0000000000",
                    }
                ],
                "length": 1,
                "resolved": None,
            }
        )

        results = await registry.dispatch("/webhooks/orders", payload)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_raises_key_error_for_unregistered_endpoint(self):
        registry = ChangefeedHandlerRegistry()

        with pytest.raises(KeyError, match="No handler"):
            await registry.dispatch("/webhooks/unknown", '{"payload": []}')

    @pytest.mark.asyncio
    async def test_dispatches_to_async_handler(self):
        registry = ChangefeedHandlerRegistry()
        handler = _make_async_handler(operations=["insert"])
        registry.register(handler)

        payload = json.dumps(
            {
                "payload": [
                    {
                        "after": {"id": 1},
                        "before": None,
                        "key": [1],
                        "topic": "orders",
                        "updated": "1716300000.0000000000",
                    }
                ],
                "length": 1,
                "resolved": None,
            }
        )

        results = await registry.dispatch("/webhooks/orders", payload)
        assert len(results) == 1


class TestGetHandlers:
    """Tests for get_handlers metadata listing."""

    def test_empty_registry(self):
        registry = ChangefeedHandlerRegistry()
        assert registry.get_handlers() == {}

    def test_lists_registered_handlers(self):
        registry = ChangefeedHandlerRegistry()
        registry.register(_make_handler(table="t1", endpoint="/e1"))
        registry.register(_make_handler(table="t2", endpoint="/e2"))

        handlers = registry.get_handlers()
        assert len(handlers) == 2
        assert handlers["/e1"]["table"] == "t1"
        assert handlers["/e2"]["table"] == "t2"
